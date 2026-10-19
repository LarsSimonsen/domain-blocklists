---
title: "Candidate: rate-limit and bot challenges are unavailable"
author: Lars
date: 2026-10-19
branch: claude/kind-haslett-a46830
cost: { minutes: 1, tokens: 29723 }
touches:
  - ".agents/skills/domain-discovery/SKILL.md"
  - scripts/blocklists.py
  - tests/test_blocklists.py
---

## Decided
`candidate` reports HTTP 429, and HTTP 202 with an empty body, as `unavailable (challenge status N)` so the discovery skill retries instead of rejecting. Headout's WAF answers request bursts with an empty 202 for about an hour, even on verified records.
## Tried and ruled out
Treating all 4xx as unavailable (the earlier rule still stands): 404 and other error pages keep their text and stay `miss`. A 202 with a body is still read as a page.
## Watch out
After a burst of challenges, pause the batch before retrying; immediate retries keep the WAF engaged.
