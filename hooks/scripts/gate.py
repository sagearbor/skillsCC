#!/usr/bin/env python3
"""proof-of-done Stop gate.

Blocks the agent from finishing until a verification verdict exists for the CURRENT work.
The verdict is tied to a "work signature" (a hash of the current git diff), so a stale PASS
from an earlier task cannot wave through code that changed afterwards — the gate re-fires every
time the diff grows. This is what stops a big build from accumulating unverified "done"s.

Reads the Stop-hook event JSON on stdin. Prints a decision JSON on stdout and exits 0.
  - block  -> the agent must run verification (the surface-router skill / /prove) which writes
              .proof-of-done/verdict.json via record_verdict.py, then try to stop again.
  - allow  -> a valid, current verdict exists (PASS / SKIP / BLOCKED), or there is nothing to
              verify (empty working tree).
"""
import hashlib
import json
import os
import subprocess
import sys

VALID_VERDICTS = {"PASS", "SKIP", "BLOCKED"}


def _git(project, *args):
    try:
        proc = subprocess.run(["git", "-C", project, *args],
                              capture_output=True, timeout=30)
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired):
        return 1, b"", b"git unavailable"


def work_signature(project):
    """Return (signature, has_changes, git_available).

    signature hashes the porcelain status + full diff of tracked changes so it shifts whenever
    the working tree changes. Untracked files show up in status, which is enough to invalidate.
    """
    # Exclude proof-of-done's own state dir: the verdict file is untracked and would otherwise
    # change the signature the moment it is written, invalidating every verdict instantly.
    code, status, _ = _git(project, "status", "--porcelain=v1",
                           "--", ".", ":(exclude).proof-of-done/")
    if code != 0:
        return None, True, False  # not a git repo / git missing: assume work to verify
    if not status.strip():
        return None, False, True  # clean tree: nothing to verify
    _, diff, _ = _git(project, "diff", "HEAD", "--", ".", ":(exclude).proof-of-done/")
    digest = hashlib.sha256(status + b"\x00" + diff).hexdigest()
    return digest, True, True


def changed_files(project):
    code, status, _ = _git(project, "status", "--porcelain=v1",
                           "--", ".", ":(exclude).proof-of-done/")
    if code != 0:
        return []
    return [ln for ln in status.decode("utf-8", "replace").splitlines() if ln.strip()]


def _emit(decision, reason=None):
    out = {}
    if decision == "block":
        out = {"decision": "block", "reason": reason}
    elif reason:
        out = {"systemMessage": reason}
    print(json.dumps(out))
    sys.exit(0)


BLOCK_REASON = (
    "proof-of-done: you have not proven this work is done.\n"
    "Run verification before stopping:\n"
    "  1. Invoke the `surface-router` skill to classify which verification surfaces this diff "
    "exposes and what proof each requires.\n"
    "  2. Reach each surface with an INDEPENDENT verifier (dispatch the `refute-done` agent / "
    "the reused pr-test-analyzer + silent-failure-hunter agents) — do not self-certify.\n"
    "  3. Run the `anti-fakery` checks on any test you offer as evidence "
    "(mutate_python.py / mutate_ts.js must not report WEAK; validate_fixture.py must not "
    "QUARANTINE your fixtures).\n"
    "  4. Record the outcome: `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record_verdict.py "
    "<PASS|SKIP|BLOCKED> \"<one-line evidence>\"`\n"
    "If there is genuinely no runtime surface, record SKIP with the reason. If a surface cannot "
    "be reached, record BLOCKED with exactly where it stuck — never a false PASS."
)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        event = {}
    project = event.get("cwd") or os.getcwd()

    sig, has_changes, _ = work_signature(project)
    if not has_changes:
        _emit("allow")  # clean tree — nothing changed to verify

    # A multi-file change is a milestone: recommend the deeper /prove pass over per-file checks.
    nfiles = len(changed_files(project))
    base = BLOCK_REASON
    if nfiles >= 3:
        base += (f"\n\nThis change spans {nfiles} files — run /prove to verify the integrated "
                 "milestone across every exposed surface, not just the last edit.")

    verdict_path = os.path.join(project, ".proof-of-done", "verdict.json")
    try:
        with open(verdict_path) as fh:
            record = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        _emit("block", base)

    verdict = record.get("verdict")
    recorded_sig = record.get("work_signature")
    if verdict not in VALID_VERDICTS:
        _emit("block", base + f"\n(found verdict={verdict!r}, which is not valid)")
    if sig is not None and recorded_sig != sig:
        _emit("block", base +
              "\n(a verdict exists but it was recorded for a different diff — the code changed "
              "since it was verified, so re-verify the current work)")
    _emit("allow", f"proof-of-done: {verdict} verdict on file for the current diff.")


if __name__ == "__main__":
    main()
