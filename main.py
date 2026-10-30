"""
DiffShield — FastAPI Server
Main entry point: API endpoints, Git repo inspector, static file mounting.
"""

from __future__ import annotations

import os
import logging
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from core.git_parser import parse_unified_diff, get_file_list_summary, read_git_repo_diff
from core.reviewer import run_review
from core.ollama_client import check_ollama_health

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("diffshield")

# ── App ──
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="DiffShield",
    description="Air-Gapped PR Intelligence — Local, Private Pull Request Reviewer",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ── Request / Response models ──

class ReviewRequest(BaseModel):
    diff_text: str
    model: str = "gemma3:4b"
    repo_path: Optional[str] = None


class ReviewResponse(BaseModel):
    review: dict
    engine: str
    telemetry: dict
    fallback_reason: Optional[str] = None
    files: list[dict] = []


# ── Routes ──

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main SPA dashboard."""
    index_path = BASE_DIR / "templates" / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.post("/api/review", response_model=ReviewResponse)
async def api_review(req: ReviewRequest):
    """
    Main review endpoint.
    Accepts a diff, runs static + AI analysis, returns structured findings.
    """
    diff_text = req.diff_text

    # If a repo path is provided and no diff text, read from the Git repo
    if not diff_text.strip() and req.repo_path:
        try:
            diff_text = read_git_repo_diff(req.repo_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    if not diff_text.strip():
        raise HTTPException(status_code=400, detail="No diff content provided.")

    # Parse the unified diff
    files = parse_unified_diff(diff_text)
    if not files:
        raise HTTPException(
            status_code=400,
            detail="Could not parse any files from the provided diff. Ensure it's a valid unified diff format.",
        )

    # Run the review pipeline
    result = await run_review(files=files, model=req.model, repo_path=req.repo_path)

    # Add file list summary
    result["files"] = get_file_list_summary(files)

    return result


@app.get("/api/sample-diff")
async def api_sample_diff():
    """Return the contents of the bundled sample_diff.patch."""
    patch_path = BASE_DIR / "sample_diff.patch"
    if not patch_path.exists():
        raise HTTPException(status_code=404, detail="sample_diff.patch not found")
    return {"diff_text": patch_path.read_text(encoding="utf-8")}


@app.get("/api/health")
async def api_health():
    """Check Ollama connectivity and return available models."""
    health = await check_ollama_health()
    return health


# ── Main ──

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
