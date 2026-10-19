---
title: "Candidate subcommand: the bulk discovery filter"
author: Lars
date: 2026-10-19
branch: claude/elated-napier-6f2c5b
cost: { minutes: 9, tokens: 127728 }
touches:
  - ".agents/skills/domain-discovery/SKILL.md"
  - README.md
  - scripts/blocklists.py
  - tests/test_blocklists.py
---

## Decided
- `python scripts/blocklists.py candidate --domain <name> [--domain ...] --path /company-details --expect "Headout"` is the bulk discovery filter. Per hostname: the resolve receipt (same states as resolve), one HTTPS fetch of the path through the approved-resolver opener, one line with state (hit, miss, redirected, unavailable, unresolved, inconclusive), requested and final URL, HTTP status, subject named or not, then up to three tag-stripped context lines capped at 200 characters. Exit 0 only when every name is a hit; the closing line says hits are filter results, not ownership decisions.
- A final hostname inside the requested name (www.x.com for x.com) is not a redirect: descendants are blocked, and verified records redirect that way (abudhabi-tickets.com answers on www with a trailing slash).
- HTTP error responses are read as pages, so a 404 is a miss; unavailable means the fetch itself failed.
- This supersedes the earlier ruling against a fetch subcommand; the uniform evidence path made the scripted check the concrete need.

## Tried and ruled out
- Replacing every tag with a newline: inline tags split "Operated by <b>Subject</b> Ltd." into three context lines. Block tags break lines, inline tags and source newlines do not, script and style blocks are dropped.
- Reporting 4xx as unavailable: hides the page text and turns a plain miss into a retry case.

## Watch out
- In Git Bash on Windows, `--path /company-details` is rewritten to a Windows path unless MSYS_NO_PATHCONV=1 is set, and the command then rejects it. PowerShell is unaffected.
- `with response as page` matters: urllib's HTTPError doubles as the response object, and the tests mock `__enter__`.
