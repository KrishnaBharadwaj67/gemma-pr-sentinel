"""
DiffShield — Static Regex + AST Security Scanner
Instant deterministic analysis engine that catches common vulnerabilities
without requiring any AI model. Acts as the resilient fallback layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core.git_parser import DiffFile, DiffLine


@dataclass
class StaticFinding:
    """A single finding from the static scanner."""
    file: str
    line: int
    severity: str          # CRITICAL, WARNING, NITPICK
    category: str          # SECURITY, LOGIC, PERFORMANCE, STYLE
    source: str            # always "Static Guard"
    title: str
    description: str
    suggested_fix: str
    rule_id: str


# ── Pattern Registry ────────────────────────────────────────────────────────

_PATTERNS: list[dict] = [
    # ── Hardcoded secrets / API keys ──
    {
        "id": "SEC-001",
        "name": "Hardcoded AWS Access Key",
        "pattern": re.compile(r"""(?:AKIA[0-9A-Z]{16})"""),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "AWS Access Key ID found hardcoded in source code. This exposes your AWS account to unauthorized access.",
        "fix": "Use environment variables: os.environ.get('AWS_ACCESS_KEY_ID')",
    },
    {
        "id": "SEC-002",
        "name": "Hardcoded Secret Key / Token",
        "pattern": re.compile(
            r"""(?:(?:secret|api|access|auth|jwt|stripe)[_\-]?(?:key|token|secret|pass)\s*[=:]\s*[\"'][A-Za-z0-9_\-/+=]{8,}[\"'])""",
            re.IGNORECASE,
        ),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "Secret key or token hardcoded directly in source code. Credentials must be loaded from secure storage.",
        "fix": "Load from environment: os.environ['SECRET_KEY'] or use a secrets manager.",
    },
    {
        "id": "SEC-003",
        "name": "Hardcoded Password in Source",
        "pattern": re.compile(
            r"""(?:password|passwd|pwd)\s*[=:]\s*[\"'][^\"']{4,}[\"']""",
            re.IGNORECASE,
        ),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "Password literal found in source code. Passwords must never be committed to version control.",
        "fix": "Use environment variables or a secrets manager to supply passwords at runtime.",
    },
    {
        "id": "SEC-004",
        "name": "Stripe Secret Key Exposed",
        "pattern": re.compile(r"""sk_(?:live|test)_[0-9a-zA-Z]{20,}"""),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "Stripe secret key detected in source code. This allows unauthorized API access against your Stripe account.",
        "fix": "Store the key in an environment variable: os.environ.get('STRIPE_SECRET_KEY')",
    },
    # ── SQL Injection ──
    {
        "id": "SEC-010",
        "name": "SQL Injection via String Concatenation",
        "pattern": re.compile(
            r"""(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+.{0,60}(?:\+\s*\w+|\bformat\s*\(|%\s*\(|f[\"'].*\{)""",
            re.IGNORECASE,
        ),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "SQL query built via string concatenation/interpolation. An attacker can inject arbitrary SQL commands.",
        "fix": "Use parameterized queries: cursor.execute('SELECT * FROM t WHERE col = ?', (value,))",
    },
    # ── Dangerous code execution ──
    {
        "id": "SEC-020",
        "name": "Use of eval() — Arbitrary Code Execution",
        "pattern": re.compile(r"""\beval\s*\("""),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "eval() executes arbitrary code and is a major security risk, especially with user-controlled input.",
        "fix": "Use ast.literal_eval() for safe parsing, or a dedicated parser for the expected data format.",
    },
    {
        "id": "SEC-021",
        "name": "Use of exec() — Arbitrary Code Execution",
        "pattern": re.compile(r"""\bexec\s*\("""),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "exec() runs arbitrary Python code. Avoid using it, especially with dynamic or user-provided input.",
        "fix": "Refactor to use safe alternatives; avoid dynamic code execution entirely.",
    },
    {
        "id": "SEC-022",
        "name": "subprocess with shell=True",
        "pattern": re.compile(r"""subprocess\.\w+\s*\([^)]*shell\s*=\s*True""", re.DOTALL),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "Running subprocess with shell=True enables shell injection attacks if any argument is user-controlled.",
        "fix": "Use subprocess.run(['cmd', 'arg1'], shell=False) with a list of arguments.",
    },
    {
        "id": "SEC-023",
        "name": "innerHTML Assignment — XSS Risk",
        "pattern": re.compile(r"""\.innerHTML\s*[\+]?="""),
        "severity": "WARNING",
        "category": "SECURITY",
        "description": "Direct innerHTML assignment with potentially unsanitized data can lead to Cross-Site Scripting (XSS).",
        "fix": "Use textContent for text, or sanitize HTML with DOMPurify before assigning to innerHTML.",
    },
    {
        "id": "SEC-024",
        "name": "JWT with Algorithm 'none'",
        "pattern": re.compile(r"""algorithms\s*=\s*\[\s*[\"']none[\"']\s*\]""", re.IGNORECASE),
        "severity": "CRITICAL",
        "category": "SECURITY",
        "description": "JWT decoded with algorithm 'none' disables signature verification entirely, allowing token forgery.",
        "fix": 'Use a secure algorithm: jwt.decode(token, secret, algorithms=["HS256"])',
    },
    # ── Logic / Quality ──
    {
        "id": "LOG-001",
        "name": "TODO / FIXME / HACK Marker",
        "pattern": re.compile(r"""(?:#|//|/\*)\s*(?:TODO|FIXME|HACK|XXX|BUG)\b""", re.IGNORECASE),
        "severity": "NITPICK",
        "category": "STYLE",
        "description": "Unresolved TODO/FIXME comment found. These should be addressed before merging to the main branch.",
        "fix": "Resolve the TODO item or convert it into a tracked issue/ticket.",
    },
    {
        "id": "LOG-002",
        "name": "Broad Exception Catch",
        "pattern": re.compile(r"""except\s+(?:Exception|BaseException)\s*:"""),
        "severity": "WARNING",
        "category": "LOGIC",
        "description": "Catching broad Exception/BaseException can mask real errors. Catch specific exception types.",
        "fix": "Catch specific exceptions: except (ValueError, KeyError) as e:",
    },
    {
        "id": "LOG-003",
        "name": "Swallowed Exception (empty except/catch)",
        "pattern": re.compile(r"""(?:except\s*:|catch\s*\([^)]*\)\s*\{\s*(?:console\.log|pass|\/\/))"""),
        "severity": "WARNING",
        "category": "LOGIC",
        "description": "Exception is caught but effectively swallowed with only a log or pass. Errors should be properly handled.",
        "fix": "Add proper error handling: re-raise, return an error response, or notify the user.",
    },
    # ── Performance ──
    {
        "id": "PERF-001",
        "name": "Potential O(n²) Nested Loop",
        "pattern": re.compile(
            r"""for\s+\w+\s+in\s+range\s*\(.*\)\s*:[\s\S]{0,200}?for\s+\w+\s+in\s+range\s*\("""
        ),
        "severity": "WARNING",
        "category": "PERFORMANCE",
        "description": "Nested loop detected over the same or related collection — potential O(n²) time complexity.",
        "fix": "Consider using a set/dict for O(1) lookups, or refactor the algorithm to O(n log n).",
    },
    {
        "id": "PERF-002",
        "name": "Potential O(n²) Nested Iteration (JS)",
        "pattern": re.compile(
            r"""for\s*\(\s*let\s+\w+\s*=\s*0[^)]*\)\s*\{[\s\S]{0,300}?for\s*\(\s*let\s+\w+\s*=\s*0"""
        ),
        "severity": "WARNING",
        "category": "PERFORMANCE",
        "description": "Nested for-loop over the same collection detected — O(n²) complexity will degrade with large datasets.",
        "fix": "Use a Map or Set for O(1) lookups, or restructure to avoid the inner loop.",
    },
    # ── Memory / Resource leaks ──
    {
        "id": "LOG-010",
        "name": "setInterval Without Cleanup Reference",
        "pattern": re.compile(r"""setInterval\s*\("""),
        "severity": "WARNING",
        "category": "LOGIC",
        "description": "setInterval without proper cleanup can cause memory leaks. Ensure the interval is cleared in component teardown.",
        "fix": "Store the interval ID and call clearInterval() in a cleanup/destroy method.",
    },
]


def scan_diff_files(files: list[DiffFile]) -> list[StaticFinding]:
    """Run all static patterns against added/modified lines in the diff."""
    findings: list[StaticFinding] = []

    for diff_file in files:
        # Build a full-text view of added lines for multi-line patterns
        added_lines: list[tuple[int, str]] = []
        for hunk in diff_file.hunks:
            for line in hunk.lines:
                if line.kind == "add" and line.number_new is not None:
                    added_lines.append((line.number_new, line.content))

        # Full added-text block (for multi-line regex matching)
        full_added_text = "\n".join(content for _, content in added_lines)

        for rule in _PATTERNS:
            # First try line-by-line for precise line attribution
            matched_lines: set[int] = set()

            for line_num, content in added_lines:
                if rule["pattern"].search(content):
                    if line_num not in matched_lines:
                        matched_lines.add(line_num)
                        findings.append(StaticFinding(
                            file=diff_file.new_path,
                            line=line_num,
                            severity=rule["severity"],
                            category=rule["category"],
                            source="Static Guard",
                            title=rule["name"],
                            description=rule["description"],
                            suggested_fix=rule["fix"],
                            rule_id=rule["id"],
                        ))

            # If no line-level match, try the full block (for multi-line patterns)
            if not matched_lines and rule["pattern"].search(full_added_text):
                # Attribute to the first added line
                first_line = added_lines[0][0] if added_lines else 1
                findings.append(StaticFinding(
                    file=diff_file.new_path,
                    line=first_line,
                    severity=rule["severity"],
                    category=rule["category"],
                    source="Static Guard",
                    title=rule["name"],
                    description=rule["description"],
                    suggested_fix=rule["fix"],
                    rule_id=rule["id"],
                ))

    # Deduplicate: same rule + same file + same line
    seen: set[tuple[str, str, int]] = set()
    deduped: list[StaticFinding] = []
    for f in findings:
        key = (f.rule_id, f.file, f.line)
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    return deduped


def scan_to_dicts(files: list[DiffFile]) -> list[dict]:
    """Convenience: return findings as plain dicts for JSON serialization."""
    findings = scan_diff_files(files)
    return [
        {
            "file": f.file,
            "line": f.line,
            "severity": f.severity,
            "category": f.category,
            "source": f.source,
            "title": f.title,
            "description": f.description,
            "suggested_fix": f.suggested_fix,
        }
        for f in findings
    ]
