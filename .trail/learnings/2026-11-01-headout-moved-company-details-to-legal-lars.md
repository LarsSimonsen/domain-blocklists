---
title: Headout moved /company-details/ to /legal/
author: Lars
date: 2026-11-01
branch: claude/headout-legal-urls
touches:
  - scripts/blocklists.py
---

## Decided
- Nov 2026: Headout 308-redirects `/company-details/` to `/legal/` on the same host (locale prefix kept, e.g. `/fr/legal/`). The rollout is gradual: unmigrated sites still serve `/company-details/` and 404 on `/legal/`, so discovery and the skills keep `/company-details` until the rollout finishes.
- Redirected sources were repointed with `add --replace` and `verified_on` moved to the retrieval date, only after each `/legal/` page was read for "Legal entity name" followed by "Headout Inc." plus the New York address. Localized pages use translated labels (Nom de l'entité légale, Name der juristischen Person, Nombre de la entidad jurídica, Nome da pessoa jurídica); read those by hand.
- `review` now prints the final URL in redirect findings.
## Tried and ruled out
- Treating every redirect as a false alarm: 13 domains now redirect to a different Headout hostname, which verifies nothing for them. Propose removal pending reverification instead of editing them.
## Watch out
- On a machine behind the maintainer's own DNS blocker, plain curl cannot resolve listed domains; use the script's public-resolver opener (import scripts/blocklists.py) instead of working around the local resolver.
- Git Bash rewrites `--path /legal/` into a Windows path; set MSYS_NO_PATHCONV=1.
- `owned` records rest partly on maintainer confirmation; do not repoint them automatically.
