#!/usr/bin/env python3
"""Oracle / fixture validation — catch the "wrong oracle / fixture" failure mode.

A fixture or gold artifact that is merely format-valid (a PDF, a URL-shaped string) is a
worthless oracle if it isn't *really* what the acceptance criteria require. This validates
a fixture against real criteria and QUARANTINEs anything that fails, so calibration never
runs on garbage.

Subcommands:
  url  URL  [--must-match REGEX ...] [--must-not-match REGEX ...] [--timeout 15]
       Fetch the URL. A dead/unreachable link or a missing required pattern → QUARANTINE.
       (This is the faculty-URL trap: "URL-shaped" is not "live and correct".)

  file PATH [--min-size BYTES] [--not-identical-to SRC] [--expect-type pdf|png|jpg|gzip|zip]
            [--must-match REGEX ...] [--must-not-match REGEX ...]
       Validate a file artifact. Empty/truncated, identical-to-source (an unapplied spike),
       wrong magic-byte type, or missing required content → QUARANTINE.

Output: JSON on stdout with per-check results. verdict: PASS | QUARANTINE.
Exit: 0 PASS, 1 QUARANTINE, 2 usage error.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

_MAGIC = {
    "pdf": b"%PDF",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "gzip": b"\x1f\x8b",
    "zip": b"PK\x03\x04",
}


def _result(checks):
    passed = all(c["passed"] for c in checks)
    out = {"verdict": "PASS" if passed else "QUARANTINE", "checks": checks}
    print(json.dumps(out, indent=2))
    return 0 if passed else 1


def _match_checks(text, must, must_not):
    checks = []
    for pat in must or []:
        ok = re.search(pat, text) is not None
        checks.append({"name": f"must-match /{pat}/", "passed": ok,
                       "detail": "found" if ok else "NOT found — fixture lacks required content"})
    for pat in must_not or []:
        ok = re.search(pat, text) is None
        checks.append({"name": f"must-not-match /{pat}/", "passed": ok,
                       "detail": "absent" if ok else "present — fixture contains forbidden content"})
    return checks


def cmd_url(args):
    checks = []
    body = ""
    try:
        req = urllib.request.Request(args.url, headers={"User-Agent": "proof-of-done/0.1"})
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            status = resp.status
            body = resp.read(2_000_000).decode("utf-8", "replace")
        checks.append({"name": "http-200", "passed": status == 200,
                       "detail": f"status {status}"})
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        checks.append({"name": "reachable", "passed": False,
                       "detail": f"unreachable/dead link: {exc}"})
        return _result(checks)
    checks.extend(_match_checks(body, args.must_match, args.must_not_match))
    return _result(checks)


def cmd_file(args):
    checks = []
    try:
        with open(args.path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return _result([{"name": "exists", "passed": False, "detail": str(exc)}])

    checks.append({"name": "non-empty", "passed": len(data) > 0,
                   "detail": f"{len(data)} bytes"})
    if args.min_size is not None:
        checks.append({"name": f"min-size>={args.min_size}", "passed": len(data) >= args.min_size,
                       "detail": f"{len(data)} bytes"})
    if args.expect_type:
        magic = _MAGIC.get(args.expect_type, b"")
        ok = data.startswith(magic)
        checks.append({"name": f"magic-type={args.expect_type}", "passed": ok,
                       "detail": "magic bytes match" if ok else "WRONG type — not really a "
                                 f"{args.expect_type}"})
    if args.not_identical_to:
        try:
            with open(args.not_identical_to, "rb") as fh:
                src = fh.read()
            same = hashlib.sha256(data).hexdigest() == hashlib.sha256(src).hexdigest()
            checks.append({"name": "differs-from-source", "passed": not same,
                           "detail": "identical to source — spike/mutation was never applied"
                                     if same else "hash differs from source"})
        except OSError as exc:
            checks.append({"name": "differs-from-source", "passed": False,
                           "detail": f"could not read source: {exc}"})
    if args.must_match or args.must_not_match:
        text = data.decode("utf-8", "replace")
        checks.extend(_match_checks(text, args.must_match, args.must_not_match))
    return _result(checks)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    pu = sub.add_parser("url")
    pu.add_argument("url")
    pu.add_argument("--must-match", action="append")
    pu.add_argument("--must-not-match", action="append")
    pu.add_argument("--timeout", type=int, default=15)
    pu.set_defaults(func=cmd_url)

    pf = sub.add_parser("file")
    pf.add_argument("path")
    pf.add_argument("--min-size", type=int)
    pf.add_argument("--not-identical-to")
    pf.add_argument("--expect-type", choices=list(_MAGIC))
    pf.add_argument("--must-match", action="append")
    pf.add_argument("--must-not-match", action="append")
    pf.set_defaults(func=cmd_file)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
