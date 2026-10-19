---
name: domain-discovery
description: Find candidate domains for a blocklist subject and hand them to domain-update as evidence packets. Use when asked to find more domains or run an exhaustive pass; never for editing records.
---

# Domain discovery

Discovery produces candidates and evidence packets. It never edits `data/*.yaml`; the [domain-update skill](../domain-update/SKILL.md) applies them in small batches after an independent verification pass.

The cheap way to find more domains is to generate many plausible names from the shape of the verified set, filter them with the script before a model reads anything, and spend model attention only on pages that passed the filter.

## Modes

- **Exhaustive** is the default when asked to find more domains. It ends only when every lane below has completed, the candidate queue is empty, and a repeated full cycle produces no new evidence-backed candidates. That is saturation, not completeness; say so in the report.
- **Bounded** runs only when the user explicitly asks for a limited pass. Report what was covered and what was not. Never claim completeness from a fixed candidate limit or a few dry searches.

## Ledger

Keep a resumable candidate ledger outside the repository. One row per hostname: discovery lane and source, status (`queued`, `resolved`, `retrieving`, `evidence`, `rejected`, `retry`), attempts, redirect chain, evidence URL and final URL, retrieval date, and the reason for rejection or retry. On resume, load only the summary and the current queue. Nothing from the ledger enters tracked files, dataset `notes`, or exports; provenance goes in the research handoff or pull request.

## Learn the shape of the verified set

Before generating candidates, aggregate the existing records with a short script rather than reading them: label count, TLD distribution, recurring tokens in the second-level label, and the path of the evidence page. These numbers decide which lanes are worth running and what the per-candidate check costs.

For Headout, as of 2026-10: nearly all records are second-level `.com` names, about five in six end in `-tickets` or `-tours`, and every record is verified from `/company-details` on the record's own hostname. So one candidate costs one DNS preflight and one page fetch, and name generation is the lane with the best yield.

## Lanes, best yield per cost first

Run each lane independently and record in the ledger which ones are done.

1. **Subject's own destination list.** Fetch the subject's public sitemap or destination directory once and take the city and attraction slugs. Combine each slug with the suffixes observed in the verified set (for Headout: `-tickets`, `-tours`, `-ticket`, `-tour`, `-cruises`) and the dominant TLD. High precision, one fetch to generate thousands of names.
2. **Variant expansion of existing records.** For each verified `x-tickets.com`, queue `x-tours.com`, `xtickets.com`, `x-ticket.com`, and the handful of country TLDs already present in the set. A few thousand DNS lookups and almost no page fetches.
3. **Certificate transparency wildcard search.** Query a CT search service for `%-tickets.com` and `%-tours.com` once each. Most results are unrelated; the filter below makes that cheap. Leads only.
4. **Certificate SAN bundles.** When a known record sits behind a CDN that bundles customer names into one certificate, one TLS handshake per known record lists sibling hostnames. Leads only.
5. **Outbound links from known sites.** One home-page fetch per verified record, extracting external links whose hostname matches the naming pattern. A one-time, resumable pass.
6. **Targeted search.** Search for the exact legal-entity string that appears on the evidence page together with the evidence path name. Far more specific than brand-name searches.
7. **Localization.** Language and country variants of known names, only where the set already shows country TLDs.

Lanes 3 to 5 are infrastructure signals. Shared infrastructure, design, images, affiliate links, redirects, and search snippets never establish ownership; they only queue a hostname for the check below.

Not worth it at this scale: reverse-IP and shared-nameserver services (paid or rate limited, weaker signal than lanes 3 and 4) and broad TLD sweeps beyond the TLDs already observed.

## Filter before reading

Run the cheap checks on the whole queue before any model reads a page:

```sh
python scripts/blocklists.py inspect --list headout --domain candidate.example.com
python scripts/blocklists.py resolve --domain candidate.example.com --domain other.example.com
```

- `covered_by` non-empty: already blocked, mark `rejected`.
- `unresolved`: both Cloudflare and Google agree, mark `rejected`.
- `inconclusive`: mark `retry`, never rejected.
- `resolved`: fetch the evidence path observed in the verified set (for Headout `/company-details`) with a client that uses the approved resolvers, recording requested and final URLs. A page that does not name the subject is `rejected`; a redirect to another hostname verifies nothing for the original name.

Only pages that name the subject go into a model's context, and then only the legal statement with enough surrounding text to judge scope. A keyword hit is a filter result, not a decision.

## Evidence packets

For each candidate whose live page states ownership or names the subject as the legal entity, record the hostname, requested and final URLs, retrieval date, the statement in context, and the proposed relationship (`owned`, `operated`, or `dedicated-hostname` with the exact hostname boundary). Keep redirect-only, supplier, affiliate, and ambiguous-scope cases in the ledger as `rejected` or `retry`. Hand the packets to domain-update in batches of about five.
