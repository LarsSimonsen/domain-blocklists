# Maintenance rules

- Keep this project small: one YAML dataset per list, one Python script, generated exports, one workflow. Avoid frameworks and extra dependencies without a concrete need.
- The root README covers the broader project; Headout is only the initial list.
- Follow the inclusion criteria in README.md. Require direct public evidence and a verification date. Automated verification is sufficient when a retrieved live page explicitly states that the exact website or hostname is owned by the list subject, or identifies the list subject as the website's legal entity. Legal-entity evidence does not need to repeat the exact hostname or explicitly state ownership. Never infer ownership from shared infrastructure, design, images, affiliate links, redirects, or search snippets.
- Commit only verified records. Suggestions may appear in public issues without a template, but unverified research and candidates must not enter tracked datasets, notes, or exports.
- Keep discovery provenance in the research handoff or pull request, not in dataset `notes`. Use `notes` only for a material blocking-boundary clarification that cannot be inferred from the domain and relationship.
- For exhaustive discovery, keep a resumable candidate ledger outside the repository, cover independent official-site, search, localization, link, certificate/DNS, and naming-pattern lanes, and retry unresolved access failures. Do not claim completeness from a fixed candidate limit or a small number of dry searches.
- For every blocklist-related DNS lookup, explicitly query Cloudflare's standard resolvers (`1.1.1.1` and `1.0.0.1`) or `https://cloudflare-dns.com/dns-query`; do not rely on DHCP-provided DNS. Use a Cloudflare-configured client for agent-controlled web retrieval when available. If a hosted search or browser tool does not expose resolver selection, run a direct Cloudflare lookup for each candidate hostname before browsing, record the limitation, and never claim that the tool-managed browsing lookup used Cloudflare.
- Treat a failure from one Cloudflare endpoint as inconclusive. Retry the other resolver and relevant A, AAAA, and CNAME records before classifying a hostname as unresolved.
- Separate discovery from verification and use an independent verifier where practical. Explicit ownership statements and legal-entity evidence meeting the criteria above qualify for automatic approval without human confirmation. Record the retrieval date and use `owned` for explicit ownership, `operated` for legal-entity evidence alone, or `dedicated-hostname` for a verified dedicated hostname on a shared service. Other evidence requires human review.
- Block listed names and descendants. On shared services use the verified dedicated hostname; never broaden it to the provider's parent domain.
- Use factual, restrained language throughout public content. Inclusion makes no allegation of misconduct.
- Edit data/*.yaml, then run `python scripts/blocklists.py build`. Never hand-edit lists/.
- Run `python scripts/blocklists.py check` and `python -m unittest discover -s tests` before proposing a change.
- Submit changes through a pull request for maintainer review. Do not merge or enable automatic publishing without authorization.
- Monthly review only flags uncertainty. When evidence is inconclusive, propose temporary removal pending reverification; never silently change verification dates.
- Original contributions use CC0 1.0 Universal. Do not copy third-party source pages into the repository.
