---
name: verifier-browser
description: This skill should be used when verifying a change to a user-facing UI — components, pages, forms, flows, styling, client-side behavior. It drives the REAL browser by intent (via the Playwright MCP), captures a screenshot/DOM snapshot, and judges what actually rendered, because "it builds" and unit-passing components routinely break at the seams a human would see.
version: 0.1.0
---

# Verifier — browser / UI

## Overview

The most common false PASS on a UI change: the build is clean, component units pass, nobody
looked at the pixels — and the click-through flow is broken at a seam. This verifier reaches the
real surface: it drives the actual browser the way a user would, then asserts on what rendered.

## When to use

Routed here by `surface-router` when the diff touches anything rendered or interactive: UI
components, templates, CSS, client-side handlers, forms, navigation.

## How to reach the surface (Playwright MCP)

Use the Playwright MCP tools to drive the live app, then capture evidence:

1. `browser_navigate` to the page under test (start the dev server first if needed).
2. Drive **by intent**, not by brittle selectors where possible: `browser_snapshot` to get the
   accessibility tree, then `browser_click` / `browser_type` / `browser_fill_form` /
   `browser_select_option` on the elements that match the user's goal.
3. `browser_wait_for` the expected text/state so you assert on the settled UI, not a race.
4. Capture evidence: `browser_take_screenshot` AND a `browser_snapshot`; state in your verdict
   what the screenshot shows and why it satisfies the requirement.
5. Check `browser_console_messages` for errors the page logged but still "rendered through".

## Evidence that counts

- A screenshot or DOM snapshot of the **real flow** plus an explicit judgment of what it shows.
  Not "the component renders" — show the end state after the user's action.
- For multi-step flows, assert state at **each** step, not just the final screen.
- For appearance/timing bugs, assert the element appears within N ms (pair with
  `verifier-latency`), and watch for flicker.
- Negative UI states matter: error toasts, empty states, disabled controls.

## Honesty (read this)

- If the app/dev-server isn't running, or the Playwright MCP isn't connected (it is unavailable
  in some headless/cron contexts), you **cannot** reach this surface — report
  `BLOCKED — browser surface unreachable: <no server / MCP not connected>`. Do **not** PASS a UI
  change you never rendered.
- A passing component unit test is not browser evidence; it doesn't exercise the real DOM, CSS,
  or the seam between components.
- "Looks right in the code" is not evidence. Drive it or block.
