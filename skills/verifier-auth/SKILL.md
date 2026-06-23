---
name: verifier-auth
description: This skill should be used when verifying a change to authentication, authorization, sessions, tokens, 2FA, secrets/.env provisioning, or multi-tenant data access. It demands NEGATIVE testing (the wrong principal must be denied), not just the happy-path login, because the denial direction is the one that's usually skipped and the one that leaks data.
version: 0.1.0
---

# Verifier — identity & access

## Overview

Auth verification is mostly **negative** testing: the right principal must pass *and* the wrong
one must be denied. The happy-path login working tells you almost nothing — the dangerous bugs
live in the denial direction, token expiry, missing secrets falling back to a wrong default, and
cross-tenant leakage. A 200 is not "authenticated"; a working admin path is not "RBAC enforced".

## When to use

Routed here by `surface-router` when the diff touches login, sessions, tokens, roles/permissions,
guards/middleware, 2FA, `.env`/secret handling, or any multi-tenant data path.

## What to prove (both directions)

| Concern | Positive | Negative (do NOT skip) |
|---|---|---|
| Authentication | real login reaches authenticated state | bad credentials are rejected; no backdoor flag |
| Authorization / RBAC | the allowed role can act | a wrong-role user is **blocked** (assert the 403/redirect, not just that admin works) |
| Session / token | valid token works | exercise **expiry + refresh**; a request past expiry is rejected, refresh re-grants |
| Multi-factor / 2FA | a real TOTP passes the gate | the gate actually gates — no test bypass flag short-circuits it |
| Secret / env provisioning | required secret is present **and used** | missing secret fails **loud**, never silently falls back to a wrong default |
| Tenancy isolation | tenant A sees A's data | tenant B **cannot** see A's data (cross-tenant negative probe) |
| Negative security | — | injection / XSS / path-traversal probes at each new entry point |

## How to reach the surface

- Drive the real login through the app (use `verifier-browser` / Playwright MCP for UI auth, or
  hit the auth endpoints directly for API auth) and assert authenticated state, not the response
  code alone.
- For RBAC/tenancy, run the action as the **wrong** principal and assert it is denied.
- For tokens, manipulate time/expiry (expired token fixture) and assert rejection + refresh.
- For secrets, unset a required var in a sandbox and assert the app fails loud (not a silent
  wrong default).

## Honesty (read this)

- Auth often needs real credentials, a test account, a TOTP secret, or a sandbox. If you don't
  have them, report `BLOCKED — auth surface unreachable: <missing creds / no sandbox>`. Never
  PASS auth you only exercised on the happy path.
- Drive **destructive or account-mutating** auth flows only against a safe test account, never
  production identities.
- A single hardcoded happy-path login is the textbook false PASS — if you didn't test the denial
  direction, you didn't verify auth.
