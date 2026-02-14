Below are two careful, explicit control documents you can drop into your repo as `claude.md` and `agents.md`.
They are written to **prevent destructive or bizarre behaviours** by coding agents (Claude, Codex, etc.) and by the runtime project agents. Follow them exactly.

I kept the language strict and unambiguous and included safe-code patterns (Python) for common operations so agents have exact, safe examples to copy instead of inventing risky shell commands.

---

````markdown
# claude.md
# RULES FOR LLM CODING AGENTS (CLAUDE / CODEX / SIMILAR)
#
# Purpose:
#   These are strict, non-negotiable operational rules to follow when generating,
#   editing, or proposing code for the Smart Doorbell multi-agent project.
#   They are intended to prevent destructive actions, accidental data loss,
#   or dangerous system operations while producing repository code.
#
# Placement:
#   Put this file at repository root and require any automation agent to load it
#   and to assert compliance before making or outputting any code changes.

─────────────────────────────────────────
SECTION A — ABSOLUTE PROHIBITIONS (MUST NEVER)
─────────────────────────────────────────

When operating on this repository or generating code you MUST NEVER:

1. Run, suggest, or output ANY `git` command.
   - Examples you CANNOT output or recommend: `git`, `git init`, `git clean`, `git clone`,
     `git pull`, `git push`, `git reset`, `git rebase`, `git checkout`, `git branch`, etc.
   - Rationale: repository state and history are managed by the human developer only.

2. Delete or remove files or directories on disk.
   - DO NOT produce code that performs deletion (e.g., `rm -rf`, `os.remove`, `shutil.rmtree`)
     unless the human has explicitly and separately given permission **in writing** to delete a
     specific, named file. (Even then, require a backup-first policy.)

3. Drop, truncate, or wipe any database.
   - NEVER output database code that runs `DROP TABLE`, `DELETE FROM <table>` without a
     WHERE clause that is safely parameterized and human-approved.
   - Do not suggest destructive migrations.

4. Execute or recommend arbitrary shell commands or system-level changes.
   - Forbidden examples: `sudo`, `apt-get`, `apt`, `yum`, `dnf`, `systemctl`, `mount`, `mkfs`,
     `chmod -R`, `chown`, `usermod`, `passwd`.
   - If a command must be used (rare), include a clear, human-actionable checklist and request
     explicit approval in writing.

5. Modify OS or system configuration files.
   - Never suggest editing `/etc/*`, boot config, kernel params, or low-level system files.

6. Install or recommend heavy or GPU-only packages without human approval.
   - Examples forbidden without approval: CUDA toolkits, GPU-only PyTorch builds, TensorRT, large
     language model weights > 500MB that require swap or exceed Pi resource limits.

7. Perform network scanning, port scanning, or credential brute-forcing.
   - No `nmap`, `masscan`, port sweeps, or other intrusive network actions.

8. Exfiltrate secrets or write code that attempts to communicate secrets to external systems.
   - No printing of environment variables, credentials, or secret files to logs or stdout.

9. Automatically open a remote shell on the user's machine or execute code remotely.
   - All execution should be local-by-human action only.

─────────────────────────────────────────
SECTION B — SAFE CODING PRACTICES (REQUIRED)
─────────────────────────────────────────

When generating code or changes you MUST:

1. Use non-destructive file operations only.
   - When creating a file: ensure it does **not** overwrite an existing file unless explicitly directed.
   - If modifying a file: make a targeted edit (insert/modify functions, append blocks) and preserve unrelated content.

2. Always include safe-file helpers (examples below) for writing to disk.
   - Use `os.path.exists()` checks and create backups before replacing any file content.

3. Use parameterized SQL and transactional patterns for DB writes.
   - For SQLite use `BEGIN IMMEDIATE` or Python `sqlite3` context managers and rollbacks on exceptions.

4. Pin dependency versions in `requirements.txt` and avoid recommending broad `pip install` commands.
   - Example: `fastapi==0.95.0`

5. Limit resource usage in generated code:
   - Default concurrency limits: semaphores or worker pools with max workers (Pi: 1–2 by default).
   - Use `asyncio.to_thread` for blocking CPU tasks rather than launching threads/processes without limits.

6. Provide human-readable tests (pytest) and a test plan; do not modify CI config without approval.

7. Provide explicit timeouts for blocking external calls (HTTP/LLM) and safe retries with exponential backoff.

─────────────────────────────────────────
SECTION C — SAFE HELPERS (COPY/PASTE-READY)
─────────────────────────────────────────

When you need to write files, use this exact safe helper in Python:

```python
import os
import shutil
from typing import Optional

def safe_write_file(path: str, content: str, backup: bool = True) -> None:
    """
    Safely write a file:
      - If file exists, create a backup with .bak timestamp suffix (unless backup=False).
      - Write to a temp file then atomically rename to avoid partial writes.
    """
    dirpath = os.path.dirname(path)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)

    if os.path.exists(path) and backup:
        bak = path + ".bak"
        # Do not delete previous backups; rotate if you must (human decision).
        shutil.copy2(path, bak)

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)  # atomic on POSIX
````

Safe DB write pattern for SQLite (use transactions and parameterized queries):

```python
import sqlite3
from contextlib import closing

def safe_db_execute(db_path: str, query: str, params: tuple = ()):
    # Use a short timeout and immediate transactions
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.execute(query, params)
            conn.commit()
            return cur
        except Exception:
            conn.rollback()
            raise
```

Safe subprocess invocation (no shell=True, sanitized args):

```python
import subprocess
def safe_run_process(args: list, timeout: int = 10):
    # args must be a list; do not construct command strings with user input
    # Example: ["espeak", "-v", "en", "Hello"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, shell=False)
    return result.returncode, result.stdout, result.stderr
```

─────────────────────────────────────────
SECTION D — LLM / PROMPT SAFETY (REQUIRED)
─────────────────────────────────────────

1. When generating code that calls external APIs (Groq, etc.):

   * Use small prompts and a clear system instruction file.
   * Sanitize all data inserted into prompts (strip binary, long transcripts).
   * Never instruct the LLM to produce or reveal secrets.

2. When code will call an LLM in production, include:

   * Request timeout (e.g., 6–10s)
   * Fallback canned responses for timeouts/errors
   * Logging of only metadata (no secrets)

─────────────────────────────────────────
SECTION E — HUMAN APPROVAL & AUDIT
─────────────────────────────────────────

1. Any operation that could lead to data loss, system changes, or external network actions must:

   * Be listed in a short plan.
   * Be submitted to a human reviewer.
   * Receive explicit written approval before code is executed.

2. All generated changes must be accompanied by:

   * Unit tests or test stubs.
   * A short plain-English summary of exactly what the code does and why.

─────────────────────────────────────────
SECTION F — WHAT TO DO WHEN UNSURE
─────────────────────────────────────────

If you (the agent) are not 100% sure an action is safe, STOP and request human guidance. Do not guess.

─────────────────────────────────────────
END OF CLAUDE RULES
─────────────────────────────────────────

