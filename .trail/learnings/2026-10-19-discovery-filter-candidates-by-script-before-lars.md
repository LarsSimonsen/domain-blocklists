---
title: "Discovery: filter candidates by script before any model reads a page"
author: Lars
date: 2026-10-19
branch: claude/skill-review-discovery-resolve
cost: { minutes: 6, tokens: 15236 }
touches:
  - ".agents/skills/domain-discovery/SKILL.md"
  - AGENTS.md
  - ".agents/skills/domain-update/SKILL.md"
  - README.md
  - scripts/blocklists.py
  - tests/test_blocklists.py
  - data/headout.yaml
---

## Decided
- Aggregating data/headout.yaml showed 580 of 581 evidence URLs are /company-details on the record's own hostname, 563 of 580 are second-level .com, and about five in six names end in -tickets or -tours. That makes one candidate cost one DNS preflight plus one page fetch.
- The domain-discovery skill therefore ranks lanes by yield per cost (subject sitemap slugs times observed suffixes, variant expansion, CT wildcard, SAN bundles, outbound links, targeted legal-string search) and tells the model to read only pages that already name the subject.
- Fetching the evidence page during discovery is now justified by that uniform shape. This supersedes the earlier note that ruled out a fetch subcommand as overlapping browser tools; a scripted candidate check (resolve, fetch the evidence path, report final URL and whether the subject is named) is the next concrete step, not yet built.

## Tried and ruled out
- Reverse-IP and shared-nameserver services: paid or rate limited, weaker than CT and SAN signals.
- Broad TLD sweeps: 97 percent of records are .com.

## Watch out
- A keyword hit on the evidence page is a filter result, not an ownership decision; the criteria still require reading the statement in context.
- Keep the skill's Headout numbers dated; they describe the set as of 2026-10.
