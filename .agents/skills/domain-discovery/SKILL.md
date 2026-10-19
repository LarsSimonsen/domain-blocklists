---
name: domain-discovery
description: Find candidate domains for a blocklist subject and hand them to domain-update as evidence packets. Use when asked to find more domains or run an exhaustive pass; never for editing records.
---

# Domain discovery

Discovery produces candidates and evidence packets. It never edits `data/*.yaml`; the [domain-update skill](../domain-update/SKILL.md) applies packets in batches of five after a separate verification pass.

Generate many plausible names from the shape of the verified set, filter them with the script, and spend model attention only on pages that passed the filter.

## Roles

- **Driver** generates names, runs the filter, and keeps the ledger. Any model with reliable tool calling; name generation can even be a plain script.
- **Reader** judges hits and writes packets. Use at least a mid tier; README's "Model tiers" section has the recommendations.
- An exhaustive pass that must decide when to stop needs the strongest available model as driver.

## Modes

- **Exhaustive** is the default when asked to find more domains. It ends only when every lane has completed, the queue is empty, and one more full cycle produced no new hit. That is saturation, not completeness; say so in the report.
- **Bounded** runs only when the user explicitly asks for a limited pass. Report what was covered and what was not. Never claim completeness from a fixed candidate limit or a few dry searches.

## Ledger

Keep a CSV ledger outside the repository with exactly these columns, one row per hostname:

```
hostname,lane,source,status,attempts,requested_url,final_url,http_status,retrieved_on,reason
```

`status` is one of `queued`, `retry`, `rejected`, `hit`, `packet`, `handed-off`. On resume, load only the row counts per status and the `queued` and `retry` rows. Nothing from the ledger enters tracked files, dataset `notes`, or exports; provenance goes in the research handoff or pull request.

## Steps

1. **Learn the shape.** Aggregate the verified set with a short script instead of reading it: label count, TLD distribution, recurring tokens in the second-level label, and the evidence path. For Headout as of 2026-10: nearly all records are second-level `.com` names, about five in six end in `-tickets` or `-tours`, and every record is verified from `/company-details` on its own hostname. One candidate therefore costs one DNS preflight and one page fetch.
2. **Generate names, one lane at a time,** and append them to the ledger as `queued` with the lane name. Mark each lane done when its queue is exhausted.

   | Lane | How | Cost | Precision |
   | --- | --- | --- | --- |
   | Subject's destination list | Fetch the subject's public sitemap once; combine each city or attraction slug with the observed suffixes (`-tickets`, `-tours`, `-ticket`, `-tour`, `-cruises`) and the dominant TLD | One fetch | High |
   | Variant expansion | For each verified `x-tickets.com` queue `x-tours.com`, `xtickets.com`, `x-ticket.com`, and the country TLDs already in the set | DNS only | Medium |
   | Certificate transparency | One wildcard query each for `%-tickets.com` and `%-tours.com` on a CT search service | One query | Low |
   | Certificate bundles | One TLS handshake per verified record; sibling names in a shared certificate | One handshake each | Low |
   | Outbound links | One home-page fetch per verified record; external links matching the naming pattern | One fetch each | Medium |
   | Targeted search | The exact legal-entity string from the evidence page plus the evidence path name | A few searches | Medium |
   | Localization | Language and country variants, only where the set already shows country TLDs | DNS only | Low |

   Infrastructure lanes give leads only. Shared infrastructure, design, images, affiliate links, redirects, and search snippets never establish ownership. Not worth it: reverse-IP or shared-nameserver services and TLD sweeps beyond the observed TLDs.
3. **Filter the queue** in batches of any size, before any model reads a page:

   ```sh
   python scripts/blocklists.py inspect --list headout --domain a.example.com --domain b.example.com
   python scripts/blocklists.py candidate --domain a.example.com --domain b.example.com --path /company-details --expect "Headout"
   ```

   Set the ledger status from the output:
   - `covered_by` non-empty in the inspect packet: `rejected`, already blocked.
   - `unresolved`: `rejected`, both Cloudflare and Google agree.
   - `inconclusive` or `unavailable`: `retry`, never rejected.
     An empty HTTP 202 or a 429 is a rate-limit or bot challenge and reports `unavailable`; pause the batch before retrying.
   - `miss`: `rejected`, the page does not name the subject.
   - `redirected`: the final hostname is outside the requested name and its descendants. `rejected`, or `retry` with the target queued as its own candidate. A redirect within the name, such as to `www`, stays a `hit` or `miss`.
   - `hit`: `hit`, queued for reading.
4. **Read hits.** For each `hit`, open the final URL, read the legal statement in context, and answer exactly one of `owned`, `operated`, `dedicated-hostname`, or `reject`, using the definitions in the domain-update skill. A keyword hit is a filter result, not a decision. When unsure, answer `reject` and record why.
5. **Write packets** for non-reject answers in the record schema from the domain-update skill, with `verified_on` set to today, and set the row to `packet`.
6. **Hand off** packets in batches of five to the domain-update skill, set the rows to `handed-off`, and checkpoint the ledger.
7. **Retry and saturation.** Rerun step 3 on the `retry` rows after the retry rules in AGENTS.md. In exhaustive mode, repeat steps 2 to 6 once more after every lane is done; stop when that cycle yields no `hit`.

## Report

Rows per status, lanes completed, hits handed off, the retry queue, and whether saturation was reached. Say that the ledger exists outside the repository without quoting its path.
