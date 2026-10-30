"""
DiffShield — Async Ollama Client with Model Switcher & Latency Telemetry
Connects to a local Ollama instance for air-gapped AI code review.
"""

from __future__ import annotations

import json
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger("diffshield.ollama")

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:4b"
GENERATE_TIMEOUT = 120.0  # seconds
HEALTH_TIMEOUT = 5.0


async def check_ollama_health() -> dict:
    """Ping the Ollama server and return available models."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return {
                    "status": "online",
                    "models": models,
                    "url": OLLAMA_BASE_URL,
                }
            return {"status": "error", "models": [], "detail": f"HTTP {resp.status_code}"}
    except (httpx.ConnectError, httpx.TimeoutException, Exception) as e:
        return {"status": "offline", "models": [], "detail": str(e)}


async def generate_review(
    diff_text: str,
    static_hints: list[dict],
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Send the diff + static hints to Ollama for deep semantic code review.
    Returns a dict with: success, response (parsed JSON), telemetry.
    """
    system_prompt = """You are DiffShield, an expert principal-level code reviewer specializing in security, correctness, performance, and code quality. You are reviewing a code diff (pull request).

INSTRUCTIONS:
1. Analyze every changed line for: security vulnerabilities, logic errors, race conditions, null/undefined risks, unhandled exceptions, performance bottlenecks (especially O(n²) or worse), memory leaks, and style issues.
2. Consider the static analysis hints provided — confirm, enhance, or add new findings the static scanner may have missed.
3. Focus on SEMANTIC understanding: what the code DOES, not just pattern matching.
4. Provide actionable, specific fixes with corrected code.

You MUST respond with ONLY a valid JSON object matching this exact schema (no markdown, no explanation outside JSON):
{
  "summary": "A 2-3 sentence executive summary of the overall PR quality and risk",
  "risk_score": <integer 0-100 where 0=perfect and 100=catastrophic>,
  "verdict": "<one of: APPROVED | CHANGES_REQUESTED | BLOCKED_CRITICAL_RISK>",
  "issues": [
    {
      "file": "<filename>",
      "line": <line_number>,
      "severity": "<CRITICAL | WARNING | NITPICK>",
      "category": "<SECURITY | LOGIC | PERFORMANCE | STYLE>",
      "source": "Gemma Local AI",
      "title": "<short title>",
      "description": "<detailed explanation of the issue>",
      "suggested_fix": "<corrected code or actionable fix>"
    }
  ]
}"""

    user_prompt = f"""## Code Diff to Review

{diff_text}

## Static Analysis Pre-Scan Results (for reference)

{json.dumps(static_hints, indent=2) if static_hints else "No static findings."}

Analyze this diff thoroughly and respond with ONLY a valid JSON object following the schema from your instructions."""

    telemetry = {
        "model": model,
        "start_time": time.time(),
        "end_time": None,
        "latency_ms": None,
        "tokens_generated": 0,
        "status": "pending",
    }

    try:
        async with httpx.AsyncClient(timeout=GENERATE_TIMEOUT) as client:
            payload = {
                "model": model,
                "prompt": user_prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_predict": 4096,
                },
            }

            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=GENERATE_TIMEOUT,
            )

            telemetry["end_time"] = time.time()
            telemetry["latency_ms"] = round(
                (telemetry["end_time"] - telemetry["start_time"]) * 1000
            )

            if resp.status_code != 200:
                telemetry["status"] = "error"
                return {
                    "success": False,
                    "response": None,
                    "telemetry": telemetry,
                    "error": f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}",
                }

            data = resp.json()
            raw_response = data.get("response", "")
            telemetry["tokens_generated"] = data.get("eval_count", len(raw_response.split()))
            telemetry["status"] = "success"

            # Parse the JSON from the response
            parsed = _extract_json(raw_response)
            if parsed:
                return {
                    "success": True,
                    "response": parsed,
                    "telemetry": telemetry,
                    "error": None,
                }
            else:
                telemetry["status"] = "parse_error"
                return {
                    "success": False,
                    "response": None,
                    "telemetry": telemetry,
                    "error": "Failed to parse JSON from Ollama response",
                    "raw": raw_response[:2000],
                }

    except httpx.TimeoutException:
        telemetry["end_time"] = time.time()
        telemetry["latency_ms"] = round(
            (telemetry["end_time"] - telemetry["start_time"]) * 1000
        )
        telemetry["status"] = "timeout"
        return {
            "success": False,
            "response": None,
            "telemetry": telemetry,
            "error": "Ollama request timed out",
        }
    except httpx.ConnectError:
        telemetry["end_time"] = time.time()
        telemetry["latency_ms"] = round(
            (telemetry["end_time"] - telemetry["start_time"]) * 1000
        )
        telemetry["status"] = "connection_failed"
        return {
            "success": False,
            "response": None,
            "telemetry": telemetry,
            "error": "Cannot connect to Ollama — is it running on localhost:11434?",
        }
    except Exception as e:
        telemetry["end_time"] = time.time()
        telemetry["latency_ms"] = round(
            (telemetry["end_time"] - telemetry["start_time"]) * 1000
        )
        telemetry["status"] = "error"
        logger.exception("Ollama generate failed")
        return {
            "success": False,
            "response": None,
            "telemetry": telemetry,
            "error": str(e),
        }


def _extract_json(text: str) -> Optional[dict]:
    """
    Robustly extract a JSON object from the LLM's response text.
    Handles markdown code fences, leading/trailing text, etc.
    """
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    if "```json" in text:
        text = text.split("```json", 1)[1]
        text = text.split("```", 1)[0]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("{"):
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue

    # Find the outermost { ... } block
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None
