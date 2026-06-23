#!/usr/bin/env node
/**
 * Assertion-strength check for JS/TS via mini mutation testing.
 *
 * A test that stays green when you break the code it covers is a vacuous oracle. This
 * applies one small textual mutation to the source at a time, reruns the tests, and a
 * mutation the tests DON'T catch (suite still green) is a "survivor".
 *
 * This is a heuristic (no AST — it mutates source text, so it skips // and * comment
 * lines but can still touch operators inside strings). The Python checker is the precise
 * one; treat a WEAK verdict here as a strong signal and a PASS as supportive evidence.
 *
 * Usage:
 *   node mutate_ts.js --test-cmd "npx vitest run" [--threshold 0.25] [--max-mutants 40]
 *                     [--timeout 120] FILE [FILE ...]
 *
 * Output: JSON on stdout. verdict: PASS | WEAK | INCONCLUSIVE.
 * Exit: 0 PASS, 1 WEAK, 2 INCONCLUSIVE.
 */
const fs = require("fs");
const { spawnSync } = require("child_process");

function parseArgs(argv) {
  const opts = { threshold: 0.25, maxMutants: 40, timeout: 120, testCmd: null, files: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--test-cmd") opts.testCmd = argv[++i];
    else if (a === "--threshold") opts.threshold = parseFloat(argv[++i]);
    else if (a === "--max-mutants") opts.maxMutants = parseInt(argv[++i], 10);
    else if (a === "--timeout") opts.timeout = parseInt(argv[++i], 10);
    else opts.files.push(a);
  }
  return opts;
}

// Each rule: a global regex over a single line, and a function producing the replacement.
// Lookarounds keep multi-char operators (===, !==, **, ++, +=, =>) from being half-matched.
const RULES = [
  { name: "eqeqeq", re: /===/g, repl: () => "!==" },
  { name: "noteqeq", re: /!==/g, repl: () => "===" },
  { name: "eqeq", re: /(?<![=!<>])==(?!=)/g, repl: () => "!=" },
  { name: "noteq", re: /(?<![=!<>])!=(?!=)/g, repl: () => "==" },
  { name: "gte", re: /(?<![<>=!])>=(?!=)/g, repl: () => "<" },
  { name: "lte", re: /(?<![<>=!])<=(?!=)/g, repl: () => ">" },
  { name: "and", re: /&&/g, repl: () => "||" },
  { name: "or", re: /\|\|/g, repl: () => "&&" },
  { name: "bool-true", re: /\btrue\b/g, repl: () => "false" },
  { name: "bool-false", re: /\bfalse\b/g, repl: () => "true" },
  // Arithmetic, spaced and unspaced. Unspaced forms require an operand on each side so
  // they never match ++, --, +=, **, =>, // or /* .
  { name: "plus", re: / \+ /g, repl: () => " - " },
  { name: "minus", re: / - /g, repl: () => " + " },
  { name: "plus-tight", re: /(?<=[\w)\]])\+(?=[\w(])/g, repl: () => "-" },
  { name: "minus-tight", re: /(?<=[\w)\]])-(?=[\w(])/g, repl: () => "+" },
  { name: "times-tight", re: /(?<=[\w)\]])\*(?=[\w(])/g, repl: () => "+" },
  { name: "int", re: /\b\d+\b/g, repl: (m) => String(parseInt(m, 10) + 1) },
];

function isCommentLine(line) {
  const t = line.trim();
  return t.startsWith("//") || t.startsWith("*") || t.startsWith("/*");
}

/** Rough guard: is column `col` inside a string/template literal on this line? Counts
 *  unescaped quotes before col; an odd count means we're inside one. Avoids mutating
 *  operators that live in string content. */
function inString(line, col) {
  let q = 0;
  for (let i = 0; i < col; i++) {
    const c = line[i];
    if ((c === '"' || c === "'" || c === "`") && line[i - 1] !== "\\") q++;
  }
  return q % 2 === 1;
}

/** Return candidate mutations [{line, col, len, replacement, op}] for a source string. */
function candidates(src) {
  const out = [];
  const lines = src.split("\n");
  lines.forEach((line, li) => {
    if (isCommentLine(line)) return;
    for (const rule of RULES) {
      rule.re.lastIndex = 0;
      let m;
      while ((m = rule.re.exec(line)) !== null) {
        if (inString(line, m.index)) continue;
        out.push({
          line: li,
          col: m.index,
          len: m[0].length,
          replacement: rule.repl(m[0]),
          op: rule.name,
        });
      }
    }
  });
  // Drop overlapping candidates on the same line (keep earliest) for clean single-mutations.
  out.sort((a, b) => a.line - b.line || a.col - b.col);
  const kept = [];
  let lastLine = -1, lastEnd = -1;
  for (const c of out) {
    if (c.line === lastLine && c.col < lastEnd) continue;
    kept.push(c);
    lastLine = c.line;
    lastEnd = c.col + c.len;
  }
  return kept;
}

function applyMutation(src, c) {
  const lines = src.split("\n");
  const line = lines[c.line];
  lines[c.line] = line.slice(0, c.col) + c.replacement + line.slice(c.col + c.len);
  return lines.join("\n");
}

function cleanEnv() {
  // Strip vars that make a nested `node --test` report to a parent runner and exit 0 even
  // on failure (NODE_TEST_CONTEXT), or inject flags (NODE_OPTIONS). Without this, running
  // this checker from inside a test runner / CI yields false PASS — the very failure it hunts.
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  delete env.NODE_OPTIONS;
  return env;
}

function runTests(cmd, timeoutSec) {
  // Split on whitespace; no shell, so metacharacters aren't interpreted.
  const parts = cmd.match(/\S+/g) || [];
  const res = spawnSync(parts[0], parts.slice(1), {
    timeout: timeoutSec * 1000,
    encoding: "utf8",
    env: cleanEnv(),
  });
  if (res.error && res.error.code === "ETIMEDOUT") return { green: false, err: "timeout" };
  if (res.error) return { green: false, err: String(res.error.message) };
  return { green: res.status === 0, err: null };
}

function emit(obj, code) {
  process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
  process.exit(code);
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.testCmd || opts.files.length === 0) {
    emit({ verdict: "INCONCLUSIVE", reason: "usage: --test-cmd CMD FILE [FILE ...]" }, 2);
  }

  const base = runTests(opts.testCmd, opts.timeout);
  if (!base.green) {
    emit({ verdict: "INCONCLUSIVE",
           reason: `baseline test run was not green (${base.err || "tests failed"})` }, 2);
  }

  const originals = {};
  let plan = [];
  for (const f of opts.files) {
    const src = fs.readFileSync(f, "utf8");
    originals[f] = src;
    for (const c of candidates(src)) plan.push({ file: f, c });
  }
  if (plan.length === 0) {
    emit({ verdict: "INCONCLUSIVE", reason: "no mutable sites found in target files" }, 2);
  }
  if (plan.length > opts.maxMutants) {
    const step = plan.length / opts.maxMutants;
    plan = Array.from({ length: opts.maxMutants }, (_, i) => plan[Math.floor(i * step)]);
  }

  const survivors = [];
  let killed = 0, errored = 0;
  try {
    for (const { file, c } of plan) {
      fs.writeFileSync(file, applyMutation(originals[file], c));
      const r = runTests(opts.testCmd, opts.timeout);
      fs.writeFileSync(file, originals[file]); // restore immediately
      if (r.err === "timeout") errored++;
      else if (r.green) survivors.push({ file, line: c.line + 1, op: c.op });
      else killed++;
    }
  } finally {
    for (const f of opts.files) fs.writeFileSync(f, originals[f]); // belt-and-suspenders
  }

  const evaluated = killed + survivors.length;
  const survivalRate = evaluated ? survivors.length / evaluated : 1.0;
  const verdict = survivalRate < opts.threshold ? "PASS" : "WEAK";
  emit({
    verdict,
    baseline: "green",
    mutants_evaluated: evaluated,
    killed,
    survived: survivors.length,
    errored_timeout: errored,
    survival_rate: Math.round(survivalRate * 1000) / 1000,
    threshold: opts.threshold,
    survivors,
    interpretation: verdict === "PASS"
      ? "Tests catch most injected defects."
      : "Tests miss real behavior changes — likely vacuous or weak assertions.",
  }, verdict === "PASS" ? 0 : 1);
}

main();
