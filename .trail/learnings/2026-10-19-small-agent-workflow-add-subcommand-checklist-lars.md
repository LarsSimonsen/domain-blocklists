---
title: "Small-agent workflow: add subcommand, checklist skills, model tiers"
author: Lars
date: 2026-10-19
branch: claude/small-agent-workflow
cost: { minutes: 29, tokens: 107394 }
touches:
  - ".agents/skills/domain-discovery/SKILL.md"
  - ".agents/skills/domain-update/SKILL.md"
  - README.md
  - scripts/blocklists.py
  - tests/test_blocklists.py
  - data/headout.yaml
---

## Decided
- `python scripts/blocklists.py add --list <name> [--replace]` reads one record or a JSON list on stdin, fills verified_on with today when absent, renders the block with a SafeDumper subclass whose increase_indent keeps nested sequences indented like the file, and splices it in without touching other bytes. It validates the whole result with validate_records before writing, so a bad packet leaves the file unchanged.
- data/headout.yaml is NOT sorted on disk (45 adjacent pairs out of order); load_records sorts on load. add therefore keeps file order and inserts before the first name that sorts after the new one. Re-sorting the file rewrites 1600 lines.
- Both skills are numbered checklists with roles (driver, verifier, maintainer), a four-way decision question (owned, operated, dedicated-hostname, reject), a fixed JSON packet equal to the record schema, and a fixed CSV ledger with status values. README has a "Model tiers" table: Haiku-class or ~27B drives; Opus-class verifies every packet; Fable-class for unattended writes and exhaustive discovery; ~9B not for any writing role.

## Tried and ruled out
- Re-dumping the whole dataset with yaml.safe_dump: reformats and reorders the file.
- Per-field CLI flags for add: a stdin JSON packet is one interface shared by discovery, verification and apply.

## Watch out
- trail check matches learnings by keywords and flags phrases like "shared service" or "evidence page" as conflicts with unrelated rulings; read each hit before treating it as real.
- Long heredocs in the Bash tool on this machine fail to parse; write patch scripts to the scratchpad and run them with python -I.
