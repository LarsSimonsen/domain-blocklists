---
title: "Skill layout: domain-update, domain-discovery, and the resolve subcommand"
author: Lars
date: 2026-10-19
branch: codex/domain-update-skill-execution-reqs
cost: { minutes: 6, tokens: 71838 }
touches:
  - ".agents/skills/domain-update/SKILL.md"
  - AGENTS.md
  - README.md
  - scripts/blocklists.py
  - tests/test_blocklists.py
  - ".agents/skills/domain-discovery/SKILL.md"
  - requirements.txt
---

## Decided
- Two project skills under .agents/skills/: domain-update applies evidence packets in batches of about five; domain-discovery finds candidates and never edits data. domain-update stays one file because its phases are sequential.
- DNS preflight for candidates is `python scripts/blocklists.py resolve --domain <name>`, which wraps the existing dns_addresses (Cloudflare and Google DoH). It prints `resolved`, `unresolved` (both providers agree) or `inconclusive`, exits 1 on any failure, and never verifies ownership.
- README carries two hand-maintained record counts (Lists table and Use section); the skill tells updaters to change both.

## Tried and ruled out
- A `fetch` subcommand for evidence pages: overlaps browser tools, review already records redirects for existing sources. YAGNI.
- A scripted ledger: the ledger lives outside the repo by rule, so no format to automate.

## Watch out
- Python's Path.write_text on Windows writes CRLF; normalize to LF before committing or git warns on every file.
- PyYAML is not on the system Python by default; run `python -m pip install -r requirements.txt` before build/check/tests.
- The record count in README drifts easily: the commit adding walkingtoursdubrovnik.com left it at 579/578 against 580 records.
