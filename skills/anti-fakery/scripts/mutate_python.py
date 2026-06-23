#!/usr/bin/env python3
"""Assertion-strength check for Python via mini mutation testing.

A test that stays green when you break the code it covers is a vacuous oracle — the
"tests pass but test nothing" failure mode. This script proves a test suite can actually
fail: it applies one small mutation to the source at a time, reruns the tests, and a
mutation that the tests DON'T catch (suite still green) is a "survivor".

Usage:
    mutate_python.py --test-cmd "pytest -q" [--threshold 0.25] [--max-mutants 40]
                     [--timeout 120] FILE [FILE ...]

Output: JSON on stdout. verdict is one of:
    PASS          baseline green and survival rate below threshold
    WEAK          baseline green but survival rate >= threshold (tests miss real changes)
    INCONCLUSIVE  baseline not green, or no mutable sites found
Exit code: 0 PASS, 1 WEAK, 2 INCONCLUSIVE (also on usage error).
"""
import argparse
import ast
import json
import os
import shlex
import signal
import subprocess
import sys


def _restore(originals, backups=()):
    """Rewrite every source from its in-memory original and drop backup files."""
    for path, src in originals.items():
        try:
            with open(path, "w") as fh:
                fh.write(src)
        except OSError:
            pass
    for bak in backups:
        try:
            os.remove(bak)
        except OSError:
            pass


class _Collector(ast.NodeVisitor):
    """Find mutable nodes and tag each with a stable index."""

    def __init__(self):
        self.sites = []  # (node, kind)

    def visit_Compare(self, node):
        if len(node.ops) == 1:
            self.sites.append((node, "compare"))
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            self.sites.append((node, "binop"))
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            self.sites.append((node, "bool"))
        elif isinstance(node.value, int) and not isinstance(node.value, bool):
            self.sites.append((node, "int"))
        self.generic_visit(node)

    def visit_Return(self, node):
        if node.value is not None and not _is_none(node.value):
            self.sites.append((node, "return"))
        self.generic_visit(node)


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


_CMP_FLIP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE, ast.GtE: ast.Lt,
    ast.Gt: ast.LtE, ast.LtE: ast.Gt,
}
_BIN_FLIP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add}


def _describe(node, kind):
    line = getattr(node, "lineno", "?")
    return {"line": line, "op": kind}


def _mutate(tree, target_index):
    """Apply exactly one mutation to a fresh tree; return (mutated_tree, desc) or None."""
    collector = _Collector()
    collector.visit(tree)
    if target_index >= len(collector.sites):
        return None
    node, kind = collector.sites[target_index]
    desc = _describe(node, kind)
    if kind == "compare":
        new = _CMP_FLIP.get(type(node.ops[0]))
        if new is None:
            return None
        node.ops[0] = new()
    elif kind == "binop":
        new = _BIN_FLIP.get(type(node.op))
        node.op = new()
    elif kind == "bool":
        node.value = not node.value
    elif kind == "int":
        node.value = node.value + 1
    elif kind == "return":
        node.value = ast.Constant(value=None)
    ast.fix_missing_locations(tree)
    return tree, desc


def _site_count(source):
    collector = _Collector()
    collector.visit(ast.parse(source))
    return len(collector.sites)


def _run(cmd, timeout):
    try:
        proc = subprocess.run(shlex.split(cmd), capture_output=True, timeout=timeout)
        return proc.returncode == 0, None
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except (OSError, ValueError) as exc:
        return False, f"could not launch test-cmd: {exc}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-cmd", required=True)
    ap.add_argument("--threshold", type=float, default=0.25)
    ap.add_argument("--max-mutants", type=int, default=40)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    baseline_ok, err = _run(args.test_cmd, args.timeout)
    if not baseline_ok:
        print(json.dumps({
            "verdict": "INCONCLUSIVE",
            "reason": f"baseline test run was not green ({err or 'tests failed'}); "
                      "cannot measure mutation kills against a red suite",
        }, indent=2))
        return 2

    originals = {}
    plan = []  # (file, site_index)
    for path in args.files:
        with open(path) as fh:
            src = fh.read()
        originals[path] = src
        try:
            n = _site_count(src)
        except SyntaxError as exc:
            print(json.dumps({"verdict": "INCONCLUSIVE",
                              "reason": f"{path}: syntax error: {exc}"}, indent=2))
            return 2
        plan.extend((path, i) for i in range(n))

    if not plan:
        print(json.dumps({"verdict": "INCONCLUSIVE",
                          "reason": "no mutable sites found in target files"}, indent=2))
        return 2

    # Even sampling across the plan so big files don't crowd out small ones.
    if len(plan) > args.max_mutants:
        step = len(plan) / args.max_mutants
        plan = [plan[int(i * step)] for i in range(args.max_mutants)]

    # Write on-disk backups (the only protection against an uncatchable SIGKILL) and install
    # handlers so a timeout/Ctrl-C restores sources instead of leaving a mutant on disk.
    backups = []
    for path, src in originals.items():
        bak = path + ".pod-bak"
        with open(bak, "w") as fh:
            fh.write(src)
        backups.append(bak)

    def _on_signal(signum, frame):
        _restore(originals, backups)
        sys.exit(2)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    survivors, killed, errored = [], 0, 0
    try:
        for path, idx in plan:
            tree = ast.parse(originals[path])
            mutated = _mutate(tree, idx)
            if mutated is None:
                continue
            tree, desc = mutated
            try:
                new_src = ast.unparse(tree)
            except Exception:
                continue
            with open(path, "w") as fh:
                fh.write(new_src)
            still_green, run_err = _run(args.test_cmd, args.timeout)
            with open(path, "w") as fh:  # restore immediately
                fh.write(originals[path])
            if run_err == "timeout":
                errored += 1
            elif still_green:
                desc["file"] = path
                survivors.append(desc)
            else:
                killed += 1
    finally:
        _restore(originals, backups)  # belt-and-suspenders restore + backup cleanup

    evaluated = killed + len(survivors)
    survival_rate = (len(survivors) / evaluated) if evaluated else 1.0
    verdict = "PASS" if survival_rate < args.threshold else "WEAK"
    print(json.dumps({
        "verdict": verdict,
        "baseline": "green",
        "mutants_evaluated": evaluated,
        "killed": killed,
        "survived": len(survivors),
        "errored_timeout": errored,
        "survival_rate": round(survival_rate, 3),
        "threshold": args.threshold,
        "survivors": survivors,
        "interpretation": ("Tests catch most injected defects."
                           if verdict == "PASS" else
                           "Tests miss real behavior changes — likely vacuous or weak "
                           "assertions. Each survivor is a defect the suite would not catch."),
    }, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
