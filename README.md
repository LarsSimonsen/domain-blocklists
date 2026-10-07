# Domain Blocklists

Community-maintained domain blocklists for people who want greater control over which businesses and services they access.

Each list has a defined purpose, documented inclusion criteria, and supporting evidence. Users can choose individual lists according to their own preferences.

## Lists

| List | Scope | Status |
| --- | --- | --- |
| [Headout](data/headout.yaml) | Domains with documented evidence of Headout ownership or operation, including dedicated hostnames on shared services | Verified expanded set: 578 entries |

Additional lists may be added over time, each with its own scope and inclusion criteria.

## Use

The exports contain 578 verified entries and block the listed names and their descendants. Subscribe using the appropriate URL:

| Product or format | Subscription / download |
| --- | --- |
| Pi-hole (FTL 5.22 or newer with compatible Core) | [pihole.txt](https://raw.githubusercontent.com/LarsSimonsen/domain-blocklists/main/lists/headout/pihole.txt) |
| AdGuard Home | [adguard.txt](https://raw.githubusercontent.com/LarsSimonsen/domain-blocklists/main/lists/headout/adguard.txt) |
| Plain domains | [domains.txt](https://raw.githubusercontent.com/LarsSimonsen/domain-blocklists/main/lists/headout/domains.txt) |

Add the Pi-hole URL as a subscribed blocking list, then update Gravity. In AdGuard Home, add the AdGuard URL under DNS blocklists.

Both product exports use `||domain.example^` rules to block the listed name and its descendants. They currently contain the same rules. The plain export contains one domain per line; it does not itself specify subdomain blocking. On shared services, only the verified dedicated hostname and its descendants are covered, never the shared parent.

Format references: [Pi-hole domain matching](https://pi-hole.net/blog/2023/03/22/pi-hole-ftl-v5-22-web-v5-19-and-core-v5-16-1-released/) and [AdGuard DNS filtering syntax](https://adguard-dns.io/kb/general/dns-filtering-syntax/).

## Headout inclusion criteria

This optional list is for people who prefer to avoid Headout-operated websites and book directly with venues or through other providers of their choice.

- Require direct public evidence of ownership or operation, such as a legal notice or an official Headout source. Record the source URL, a short factual explanation, and the date the evidence was verified. An agent may verify a record without human confirmation when a retrieved live page explicitly states that the exact website or hostname is owned by Headout, or identifies Headout as the website's legal entity. Legal-entity evidence is sufficient for automatic approval without repeating the exact hostname or explicitly stating ownership. Use `owned` for explicit ownership, `operated` for legal-entity evidence alone, or `dedicated-hostname` for a verified dedicated hostname on a shared service. Other evidence requires human review.
- Independent affiliates, partners, and venues do not qualify merely because they sell through Headout. Shared hosting, similar design, or Headout images alone are investigation leads, not sufficient evidence.
- A dedicated hostname on a shared service qualifies only with direct evidence of its operation by Headout. Review the blocking boundary carefully.
- Keep unverified candidates out of committed datasets and exports. Public issues may contain unverified suggestions; an issue is not a verified finding.
- If evidence disappears or becomes inconclusive, temporarily remove the entry through a reviewed pull request until reverified. Explain the removal in the change history.

## Contribute and maintain

Use [public issues](https://github.com/LarsSimonsen/domain-blocklists/issues) for suggestions and corrections; no template is required. Supporting sources are helpful. Keep repository text, issues, and commit messages factual and relevant to the list criteria. Never include private local filesystem paths in pull requests, issues, reviews, comments, commit messages, or other public text. Refer to tracked files with repository-relative paths and describe external or temporary artifacts generically, without usernames, home directories, drive letters, workspace roots, or temporary-directory paths.

Discovery work should combine independent sources: official destination and attraction directories, sitemaps and localized links, exact legal-identifier searches, naming-pattern searches, and infrastructure signals such as certificates and DNS. Infrastructure and pattern matches are leads only. Long searches should maintain a resumable candidate ledger outside the repository, including the discovery source, status, attempts, redirects, evidence URL, and reason for rejection or retry. An exhaustive pass ends only after every planned discovery lane has completed, the candidate queue is empty, and repeated full cycles produce no new evidence-backed candidates. This indicates search saturation, not guaranteed completeness; recurring monitoring is needed because domains and public evidence change.

All blocklist-related DNS lookups must explicitly use a primary approved public resolver: Cloudflare at `1.1.1.1` or `1.0.0.1`, Cloudflare's DNS-over-HTTPS endpoint at `https://cloudflare-dns.com/dns-query`, or Google Public DNS at `8.8.8.8` or `8.8.4.4`, instead of DNS supplied through DHCP. Optional independent checks may use Quad9's unfiltered service at `9.9.9.10` or `149.112.112.10`, its DNS-over-HTTPS endpoint at `https://dns10.quad9.net/dns-query`, AdGuard DNS's unfiltered service at `94.140.14.140` or `94.140.14.141`, or its DNS-over-HTTPS endpoint at `https://unfiltered.adguard-dns.com/dns-query`. Agent-controlled web retrieval should use a client configured for an approved unfiltered public resolver when available. Hosted search and browser tools may manage DNS internally; when they do not expose resolver selection, perform a direct lookup through a primary approved resolver for each candidate hostname before browsing and disclose that the browsing tool's resolver could not be controlled. Treat a failure from one resolver as inconclusive: retry the other address from the same provider, inspect relevant A, AAAA, and CNAME records, and require agreeing results from at least two independent unfiltered providers, including Cloudflare or Google, before treating the hostname as unresolved. Never use a negative response from a filtering or user-configured resolver as evidence that a hostname is unresolved.

Keep discovery and verification separate where practical. Discovery produces evidence packets for independent review. Explicit ownership statements and legal-entity evidence meeting the inclusion criteria above qualify for automatic approval without human confirmation. The live page must identify Headout as the legal entity for the website being verified; an incidental company mention is insufficient. Search snippets, redirects, branding, infrastructure, and shared templates alone do not qualify. Pull requests still require maintainer review before merging.

`data/headout.yaml` is the source of truth. All committed records are verified; there is no candidate status. Each record has `domain`, `relationship` (`owned`, `operated`, or `dedicated-hostname`), `verified_on` (YYYY-MM-DD), and a nonempty `sources` list containing `url` and `evidence`. Optional `notes` are reserved for material blocking-boundary clarifications. Keep discovery provenance in the research handoff or pull request. Write explanations in your own words; linked third-party material remains subject to its own terms.

Illustrative schema only (the reserved example domain below is not a list entry):

```yaml
- domain: tickets.example.com
  relationship: operated
  verified_on: '2026-09-04'
  sources:
    - url: https://tickets.example.com/legal
      evidence: Explain which direct statement identifies the operator.
```

Use Python 3.12 or newer:

```sh
python -m pip install -r requirements.txt
python scripts/blocklists.py build
python scripts/blocklists.py check
python -m unittest discover -s tests
```

Commit the YAML changes and regenerated exports together in a pull request. The maintainer reviews and merges changes before they reach the `main` subscription URLs. Automated checks validate structure and export consistency; they cannot establish ownership or verify the truth of evidence. Configure a repository branch rule requiring pull requests and the `validate` check to enforce this workflow; the workflow file alone does not enforce review.

One GitHub Actions workflow also runs monthly and on manual request. `python scripts/blocklists.py review` checks DNS address resolution, source availability/redirects, and verification dates older than 90 days. Findings appear in the run summary and fail the review job so GitHub can notify subscribers according to their notification settings. It never edits records or publishes changes. A successful response does not prove that a page still supports inclusion; the page content must be reverified under the rules above. DNS failures and HTTP blocks can be temporary. Scheduled runs begin after the workflow is merged into the default branch.

## Meaning of inclusion

Inclusion means that a domain meets the stated criteria of a particular list. It does not, by itself, imply malicious, fraudulent, or unlawful activity.

This is an independent project. References to businesses and services identify the subjects of individual lists and do not imply affiliation or endorsement.

## Reuse

Original repository data, documentation, and code are dedicated under [CC0 1.0 Universal](LICENSE). You may reuse and redistribute them without attribution. This dedication does not cover third-party material linked as evidence or third-party trademarks. No warranty is provided.
