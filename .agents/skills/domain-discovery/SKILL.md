---
name: domain-discovery
description: Find candidate domains for a blocklist subject and hand them to domain-update as evidence packets. Use when asked to find more domains or run an exhaustive pass; never for editing records.
---

# Domain discovery

Discovery produces candidates and evidence packets. It never edits `data/*.yaml`; the [domain-update skill](../domain-update/SKILL.md) applies them in small batches after an independent verification pass.

## Modes

- **Exhaustive** is the default when asked to find more domains. It ends only when every lane below has completed, the candidate queue is empty, and a repeated full cycle produces no new evidence-backed candidates. That is saturation, not completeness; say so in the report.
- **Bounded** runs only when the user explicitly asks for a limited pass. Report what was covered and what was not. Never claim completeness from a fixed candidate limit or a few dry searches.

## Ledger

Keep a resumable candidate ledger outside the repository. One row per hostname: discovery lane and source, status (`queued`, `retrieving`, `evidence`, `rejected`, `retry`), attempts, redirect chain, evidence URL and final URL, retrieval date, and the reason for rejection or retry. On resume, load only the summary and the current queue. Nothing from the ledger enters tracked files, dataset `notes`, or exports; provenance goes in the research handoff or pull request.

## Lanes

Run each lane independently and record which ones are done:

1. Official site: the subject's own destination, attraction, and partner directories, sitemaps, and localized links.
2. Search: exact legal-identifier and naming-pattern searches.
3. Localization: language and country variants of known names.
4. Links: outbound and inbound links from already verified records.
5. Certificate and DNS: certificate transparency, CNAME, and shared-infrastructure signals.
6. Naming patterns: variants derived from the verified set.

Lanes 5 and 6 produce leads only. Shared infrastructure, design, images, affiliate links, redirects, and search snippets never establish ownership.

Before retrieving a candidate, check whether it is already covered and whether it resolves:

```sh
python scripts/blocklists.py inspect --list headout --domain candidate.example.com
python scripts/blocklists.py resolve --domain candidate.example.com
```

`covered_by` means the name is already blocked. Treat `inconclusive` DNS results as retry items, not rejections.

## Evidence packets

For each candidate with a live page that states ownership or names the subject as the legal entity, record the hostname, requested and final URLs, retrieval date, the statement in context, and the proposed relationship (`owned`, `operated`, or `dedicated-hostname` with the exact hostname boundary). Keep redirect-only, supplier, affiliate, and ambiguous-scope cases in the ledger as rejected or retry. Hand the packets to domain-update in batches of about five.
