// Self-tests for mutate_ts.js (run with: node --test tests/test_mutate_ts.mjs)
import { test } from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SCRIPT = join(ROOT, "skills", "anti-fakery", "scripts", "mutate_ts.js");

function run(dir, testCmd, file) {
  try {
    const out = execFileSync("node", [SCRIPT, "--test-cmd", testCmd, file], { cwd: dir, encoding: "utf8" });
    return JSON.parse(out);
  } catch (e) {
    // non-zero exit (WEAK/INCONCLUSIVE) still prints JSON to stdout
    return JSON.parse(e.stdout);
  }
}

const CALC = `function f(a, b) {
  return a + b;
}
function bothPos(a, b) {
  return a > 0 && b > 0;
}
function tag() {
  return "a+b is not math";
}
module.exports = { f, bothPos, tag };
`;

function setup() {
  const dir = mkdtempSync(join(tmpdir(), "pod-ts-"));
  writeFileSync(join(dir, "c.js"), CALC);
  return dir;
}

test("flags vacuous suite as WEAK", () => {
  const dir = setup();
  writeFileSync(join(dir, "v.test.js"),
    `const{test}=require("node:test");const{f,bothPos,tag}=require("./c.js");test("r",()=>{f(1,2);bothPos(1,1);tag();});`);
  const r = run(dir, "node --test v.test.js", "c.js");
  assert.strictEqual(r.verdict, "WEAK", JSON.stringify(r));
  rmSync(dir, { recursive: true, force: true });
});

test("passes strong suite and leaves string literals unmutated", () => {
  const dir = setup();
  writeFileSync(join(dir, "s.test.js"),
    `const{test}=require("node:test");const a=require("node:assert");const{f,bothPos,tag}=require("./c.js");`
    + `test("f",()=>a.strictEqual(f(1,2),3));`
    + `test("b",()=>{a.strictEqual(bothPos(1,1),true);a.strictEqual(bothPos(1,-1),false);});`
    + `test("t",()=>a.strictEqual(tag(),"a+b is not math"));`);
  const r = run(dir, "node --test s.test.js", "c.js");
  assert.strictEqual(r.verdict, "PASS", JSON.stringify(r));
  // source restored
  assert.ok(readFileSync(join(dir, "c.js"), "utf8").includes('return "a+b is not math"'));
  rmSync(dir, { recursive: true, force: true });
});
