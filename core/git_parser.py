"""
DiffShield — Unified Diff Parser & Line-Number Mapper
Parses unified diff format into structured file/hunk/line objects.
Also reads diffs from local Git repositories.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiffLine:
    """A single line in a diff hunk."""
    number_old: Optional[int]  # line number in the old file (None for additions)
    number_new: Optional[int]  # line number in the new file (None for deletions)
    kind: str  # "add", "delete", "context"
    content: str  # the raw line text (without leading +/-/ )


@dataclass
class DiffHunk:
    """A contiguous hunk inside a file diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str  # the @@ ... @@ line itself
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class DiffFile:
    """All hunks for a single file in the diff."""
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    language: str = ""

    def __post_init__(self):
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascript", ".tsx": "typescript", ".java": "java",
            ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
            ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
            ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
            ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
            ".json": "json", ".html": "html", ".css": "css",
            ".sql": "sql", ".md": "markdown", ".xml": "xml",
        }
        _, ext = os.path.splitext(self.new_path or self.old_path)
        self.language = ext_map.get(ext.lower(), "plaintext")


HUNK_HEADER_RE = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$"
)


def parse_unified_diff(diff_text: str) -> list[DiffFile]:
    """Parse a unified diff string into a list of DiffFile objects."""
    files: list[DiffFile] = []
    current_file: Optional[DiffFile] = None
    current_hunk: Optional[DiffHunk] = None
    old_line = 0
    new_line = 0

    lines = diff_text.replace("\r\n", "\n").split("\n")

    for raw_line in lines:
        # Detect file header: diff --git a/path b/path
        if raw_line.startswith("diff --git"):
            parts = raw_line.split(" b/", 1)
            a_part = raw_line.split(" a/", 1)
            old_p = a_part[1].split(" b/")[0] if len(a_part) > 1 else ""
            new_p = parts[1] if len(parts) > 1 else old_p
            current_file = DiffFile(old_path=old_p, new_path=new_p)
            files.append(current_file)
            current_hunk = None
            continue

        # --- and +++ lines refine paths
        if raw_line.startswith("--- a/") and current_file:
            current_file.old_path = raw_line[6:]
            continue
        if raw_line.startswith("+++ b/") and current_file:
            current_file.new_path = raw_line[6:]
            continue
        if raw_line.startswith("--- ") or raw_line.startswith("+++ "):
            continue

        # index line, mode lines, etc.
        if raw_line.startswith("index ") or raw_line.startswith("new file") or raw_line.startswith("deleted file"):
            continue
        if raw_line.startswith("old mode") or raw_line.startswith("new mode"):
            continue
        if raw_line.startswith("similarity index") or raw_line.startswith("rename"):
            continue
        if raw_line.startswith("Binary files"):
            continue

        # Hunk header
        m = HUNK_HEADER_RE.match(raw_line)
        if m and current_file:
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) else 1
            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header=raw_line,
            )
            current_file.hunks.append(current_hunk)
            old_line = old_start
            new_line = new_start
            continue

        # Diff content lines
        if current_hunk is not None:
            if raw_line.startswith("+"):
                dl = DiffLine(
                    number_old=None,
                    number_new=new_line,
                    kind="add",
                    content=raw_line[1:],
                )
                current_hunk.lines.append(dl)
                new_line += 1
                if current_file:
                    current_file.additions += 1
            elif raw_line.startswith("-"):
                dl = DiffLine(
                    number_old=old_line,
                    number_new=None,
                    kind="delete",
                    content=raw_line[1:],
                )
                current_hunk.lines.append(dl)
                old_line += 1
                if current_file:
                    current_file.deletions += 1
            elif raw_line.startswith(" ") or raw_line == "":
                content = raw_line[1:] if raw_line.startswith(" ") else ""
                dl = DiffLine(
                    number_old=old_line,
                    number_new=new_line,
                    kind="context",
                    content=content,
                )
                current_hunk.lines.append(dl)
                old_line += 1
                new_line += 1
            elif raw_line.startswith("\\"):
                # "\ No newline at end of file"
                continue

    return files


def diff_files_to_text_block(files: list[DiffFile]) -> str:
    """Rebuild a compact textual representation for sending to the LLM."""
    parts: list[str] = []
    for f in files:
        parts.append(f"=== FILE: {f.new_path} ({f.language}) ===")
        for hunk in f.hunks:
            parts.append(hunk.header)
            for line in hunk.lines:
                prefix = {"add": "+", "delete": "-", "context": " "}[line.kind]
                parts.append(f"{prefix}{line.content}")
        parts.append("")
    return "\n".join(parts)


def read_git_repo_diff(repo_path: str, base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> str:
    """Read the diff between two refs in a local Git repository."""
    if not os.path.isdir(repo_path):
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        raise ValueError(f"Not a Git repository: {repo_path}")

    try:
        result = subprocess.run(
            ["git", "diff", base_ref, head_ref],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=30,
        )
        if result.returncode != 0:
            # Fallback: try staged changes
            result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
        if result.returncode != 0:
            # Last fallback: unstaged changes
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
        return result.stdout
    except FileNotFoundError:
        raise RuntimeError("Git is not installed or not in PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Git diff timed out")


def get_file_list_summary(files: list[DiffFile]) -> list[dict]:
    """Return a lightweight summary for the file tree UI."""
    return [
        {
            "path": f.new_path,
            "language": f.language,
            "additions": f.additions,
            "deletions": f.deletions,
            "hunk_count": len(f.hunks),
        }
        for f in files
    ]
