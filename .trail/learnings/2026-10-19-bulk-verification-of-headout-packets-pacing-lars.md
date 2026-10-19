---
title: "Bulk verification of Headout packets: pacing and reading the legal block"
author: Lars
date: 2026-10-19
branch: claude/frosty-sammet-fa7112
cost: { minutes: 13, tokens: 88818 }
touches:
  - README.md
  - data/headout.yaml
  - lists/headout/adguard.txt
  - lists/headout/domains.txt
  - lists/headout/pihole.txt
---

## Decided
- Verified 98 discovery packets with a scratch driver outside the repo: inspect per batch, then `candidate` one domain at a time with ~1.5 s spacing (backoff retry on empty 202 or unavailable), then a separate paced fetch of the final URL to read the legal block. About 1 minute per 5-domain batch; run it in the background.
- Evidence text was rewritten to what the verifier actually read (legal entity + New York correspondence address) instead of reusing the discovery packet's wording, which listed fields not checked on every template.
## Tried and ruled out
- Anchoring the read on the first "company details" line: two page templates exist, and on one the first match is a footer nav link, so the extract shows only the copyright footer. Anchor on the exact line "Legal entity name" instead; it is followed by "Headout Inc." on both templates.
## Watch out
- `trail check` flags README count changes (learning that quotes "580") and "evidence page" in records (fetch-subcommand learning); both are keyword false positives for dataset additions; say so in the PR.
- Final URL host is www.<domain>; `candidate` treats that as a hit, not a redirect.
