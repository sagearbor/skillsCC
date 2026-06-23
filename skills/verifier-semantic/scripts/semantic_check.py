#!/usr/bin/env python3
"""Semantic content verifier — the "is it REALLY what was asked?" surface.

Format-valid is not correct. A scraped URL can be live and URL-shaped yet the wrong page; a
"clinical-trial protocol" can be a PDF yet not a Phase-III protocol with the required sections.
A single regex is a vacuous oracle for these — it answers "is this string-shaped like X", a
different question. This checker demands MULTIPLE independent criteria so passing means the
content genuinely matches intent, not just its shape.

Source is a local file or a URL (fetched live, so a dead/wrong link fails). Criteria come from a
JSON spec or CLI flags.

Spec format (JSON):
    {
      "source": {"type": "url", "url": "https://..."},   // or {"type": "file", "path": "..."}
      "criteria": {
        "min_words": 200,
        "require_all": ["Phase III", "Inclusion Criteria"],   // every pattern must match
        "require_any": ["randomized", "double-blind"],         // at least one must match
        "forbid": ["Lorem ipsum", "404 Not Found"],            // none may match
        "sections": ["Methods", "Results"],                    // each must appear as a heading-ish line
        "date_after": "2020-01-01"                             // some date in the text >= this
      }
    }

CLI flags mirror the criteria: --min-words, --require, --require-any, --forbid, --section,
--date-after (repeatable where it makes sense).

Output: JSON with per-criterion results. verdict PASS (content genuinely matches) or FAIL.
Exit 0 PASS, 1 FAIL, 2 usage/load error.
"""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request

DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "%m/%d/%Y"),
    (re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})\b"), "%B %d, %Y"),
]


def fetch(source):
    if source["type"] == "file":
        with open(source["path"], encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if source["type"] == "url":
        req = urllib.request.Request(source["url"], headers={"User-Agent": "proof-of-done/0.1"})
        with urllib.request.urlopen(req, timeout=source.get("timeout", 15)) as resp:
            if resp.status != 200:
                raise ValueError(f"status {resp.status}")
            return resp.read(4_000_000).decode("utf-8", "replace")
    raise ValueError(f"unknown source type: {source['type']}")


def extract_dates(text):
    found = []
    for rx, fmt in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                found.append(dt.datetime.strptime(m.group(0), fmt).date())
            except ValueError:
                pass
    return found


def evaluate(text, criteria):
    checks = []
    words = len(text.split())

    if "min_words" in criteria:
        checks.append({"name": f"min_words>={criteria['min_words']}",
                       "passed": words >= criteria["min_words"], "detail": f"{words} words"})

    for pat in criteria.get("require_all", []):
        ok = re.search(pat, text, re.IGNORECASE) is not None
        checks.append({"name": f"require_all /{pat}/", "passed": ok,
                       "detail": "found" if ok else "MISSING required content"})

    if criteria.get("require_any"):
        any_pats = criteria["require_any"]
        hit = next((p for p in any_pats if re.search(p, text, re.IGNORECASE)), None)
        checks.append({"name": f"require_any {any_pats}", "passed": hit is not None,
                       "detail": f"matched /{hit}/" if hit else "none of the alternatives matched"})

    for pat in criteria.get("forbid", []):
        ok = re.search(pat, text, re.IGNORECASE) is None
        checks.append({"name": f"forbid /{pat}/", "passed": ok,
                       "detail": "absent" if ok else "FORBIDDEN content present"})

    for sec in criteria.get("sections", []):
        # heading-ish: the section title on a line largely by itself (markdown/heading/caps).
        rx = re.compile(rf"^\s*#*\s*{re.escape(sec)}\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
        ok = rx.search(text) is not None
        checks.append({"name": f"section '{sec}'", "passed": ok,
                       "detail": "present as a heading" if ok else "no heading-like line found"})

    if "date_after" in criteria:
        cutoff = dt.datetime.strptime(criteria["date_after"], "%Y-%m-%d").date()
        dates = extract_dates(text)
        recent = [d for d in dates if d >= cutoff]
        checks.append({"name": f"date_after {criteria['date_after']}", "passed": bool(recent),
                       "detail": f"{len(recent)} date(s) >= cutoff (of {len(dates)} found)"})

    return checks


def build_criteria(args):
    c = {}
    if args.min_words is not None:
        c["min_words"] = args.min_words
    if args.require:
        c["require_all"] = args.require
    if args.require_any:
        c["require_any"] = args.require_any
    if args.forbid:
        c["forbid"] = args.forbid
    if args.section:
        c["sections"] = args.section
    if args.date_after:
        c["date_after"] = args.date_after
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--file")
    ap.add_argument("--url")
    ap.add_argument("--min-words", type=int)
    ap.add_argument("--require", action="append")
    ap.add_argument("--require-any", action="append")
    ap.add_argument("--forbid", action="append")
    ap.add_argument("--section", action="append")
    ap.add_argument("--date-after")
    args = ap.parse_args()

    if args.spec:
        spec = json.loads(open(args.spec).read())
        source, criteria = spec["source"], spec.get("criteria", {})
    else:
        if args.file:
            source = {"type": "file", "path": args.file}
        elif args.url:
            source = {"type": "url", "url": args.url}
        else:
            print(json.dumps({"verdict": "FAIL", "reason": "give --spec, --file, or --url"}))
            return 2
        criteria = build_criteria(args)

    if not criteria:
        print(json.dumps({"verdict": "FAIL", "reason": "no criteria given — a check with no "
                          "criteria is a vacuous oracle"}))
        return 2

    try:
        text = fetch(source)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(json.dumps({"verdict": "FAIL", "reason": f"could not fetch source: {exc}"}, indent=2))
        return 1

    checks = evaluate(text, criteria)
    ok = all(c["passed"] for c in checks) and bool(checks)
    print(json.dumps({"verdict": "PASS" if ok else "FAIL",
                      "criteria_count": len(checks), "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
