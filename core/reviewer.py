"""
DiffShield — Hybrid Review Orchestrator
Combines the instant static scanner with deep Gemma AI review.
Provides seamless fallback if Ollama is unreachable.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from core.git_parser import DiffFile, diff_files_to_text_block
from core.static_scanner import scan_to_dicts
from core import ollama_client

logger = logging.getLogger("diffshield.reviewer")

STATIC_ONLY_MODEL = "static-heuristics-only"


def _build_static_only_response(
    static_issues: list[dict],
) -> dict:
    """Build a complete review response using only static analysis findings."""
    critical_count = sum(1 for i in static_issues if i["severity"] == "CRITICAL")
    warning_count = sum(1 for i in static_issues if i["severity"] == "WARNING")
    nitpick_count = sum(1 for i in static_issues if i["severity"] == "NITPICK")

    # Calculate risk score from static findings
    risk_score = min(100, critical_count * 20 + warning_count * 8 + nitpick_count * 2)

    if critical_count >= 3:
        verdict = "BLOCKED_CRITICAL_RISK"
    elif critical_count >= 1:
        verdict = "CHANGES_REQUESTED"
    elif warning_count >= 3:
        verdict = "CHANGES_REQUESTED"
    elif warning_count >= 1 or nitpick_count >= 2:
        verdict = "CHANGES_REQUESTED"
    else:
        verdict = "APPROVED"

    summary_parts = []
    if critical_count:
        summary_parts.append(f"{critical_count} critical security vulnerability{'s' if critical_count > 1 else ''}")
    if warning_count:
        summary_parts.append(f"{warning_count} warning{'s' if warning_count > 1 else ''}")
    if nitpick_count:
        summary_parts.append(f"{nitpick_count} code quality note{'s' if nitpick_count > 1 else ''}")

    if summary_parts:
        summary = (
            f"Static analysis detected {', '.join(summary_parts)}. "
            f"This PR requires immediate attention before merge."
        )
    else:
        summary = "Static analysis found no issues. Code appears clean."

    return {
        "summary": summary,
        "risk_score": risk_score,
        "verdict": verdict,
        "issues": static_issues,
    }


def _merge_issues(
    static_issues: list[dict],
    ai_issues: list[dict],
) -> list[dict]:
    """Merge static and AI issues, deduplicating by file+line+category."""
    merged = list(static_issues)
    seen = {(i["file"], i["line"], i["title"][:30]) for i in static_issues}

    for ai_issue in ai_issues:
        key = (ai_issue.get("file", ""), ai_issue.get("line", 0), ai_issue.get("title", "")[:30])
        if key not in seen:
            seen.add(key)
            merged.append(ai_issue)

    # Sort: CRITICAL first, then WARNING, then NITPICK
    severity_order = {"CRITICAL": 0, "WARNING": 1, "NITPICK": 2}
    merged.sort(key=lambda x: severity_order.get(x.get("severity", "NITPICK"), 3))
    return merged


async def run_review(
    files: list[DiffFile],
    model: str = "gemma3:4b",
    repo_path: Optional[str] = None,
) -> dict:
    """
    Main review pipeline:
    1. Run instant static scan
    2. Attempt deep AI review via Ollama
    3. Merge results or fallback to static-only
    """
    start = time.time()

    # ── Step 1: Static scan (always runs, instant) ──
    static_issues = scan_to_dicts(files)
    logger.info(f"Static scan found {len(static_issues)} issues")

    # ── Step 2: Check if user wants static-only mode ──
    if model.lower() == STATIC_ONLY_MODEL or model.lower() == "static heuristics only":
        response = _build_static_only_response(static_issues)
        elapsed = round((time.time() - start) * 1000)
        return {
            "review": response,
            "engine": "static_only",
            "telemetry": {
                "model": "Static Heuristics",
                "latency_ms": elapsed,
                "tokens_generated": 0,
                "status": "static_only",
            },
        }

    # ── Step 3: Attempt Ollama AI review ──
    diff_text_block = diff_files_to_text_block(files)
    ai_result = await ollama_client.generate_review(
        diff_text=diff_text_block,
        static_hints=static_issues,
        model=model,
    )

    telemetry = ai_result.get("telemetry", {})

    if ai_result["success"] and ai_result["response"]:
        # Merge static + AI findings
        ai_response = ai_result["response"]
        ai_issues = ai_response.get("issues", [])
        merged_issues = _merge_issues(static_issues, ai_issues)

        review = {
            "summary": ai_response.get("summary", "Review completed."),
            "risk_score": ai_response.get("risk_score", 50),
            "verdict": ai_response.get("verdict", "CHANGES_REQUESTED"),
            "issues": merged_issues,
        }

        elapsed = round((time.time() - start) * 1000)
        telemetry["total_ms"] = elapsed
        return {
            "review": review,
            "engine": "hybrid_ai",
            "telemetry": telemetry,
        }
    else:
        # ── Fallback: Ollama failed, use static-only ──
        logger.warning(
            f"Ollama unavailable ({ai_result.get('error', 'unknown')}). "
            f"Falling back to static analysis."
        )
        response = _build_static_only_response(static_issues)
        elapsed = round((time.time() - start) * 1000)
        telemetry["total_ms"] = elapsed
        telemetry["status"] = f"fallback ({telemetry.get('status', 'error')})"
        return {
            "review": response,
            "engine": "static_fallback",
            "fallback_reason": ai_result.get("error", "Ollama unreachable"),
            "telemetry": telemetry,
        }
