# Maintenance rules

- Keep this project small: one YAML dataset per list, one Python script, generated exports, one workflow. Avoid frameworks and extra dependencies without a concrete need.
- The root README covers the broader project; Headout is only the initial list.
- Follow the inclusion criteria in README.md. Require direct public evidence and a human verification date. Never infer ownership from shared infrastructure, design, images, or affiliate links alone.
- Commit only verified records. Suggestions may appear in public issues without a template, but unverified research and candidates must not enter tracked datasets, notes, or exports.
- Keep discovery provenance in the research handoff or pull request, not in dataset `notes`. Use `notes` only for a material blocking-boundary clarification that cannot be inferred from the domain and relationship.
- Block listed names and descendants. On shared services use the verified dedicated hostname; never broaden it to the provider's parent domain.
- Use factual, restrained language throughout public content. Inclusion makes no allegation of misconduct.
- Edit data/*.yaml, then run `python scripts/blocklists.py build`. Never hand-edit lists/.
- Run `python scripts/blocklists.py check` and `python -m unittest discover -s tests` before proposing a change.
- Submit changes through a pull request for maintainer review. Do not merge or enable automatic publishing without authorization.
- Monthly review only flags uncertainty. When evidence is inconclusive, propose temporary removal pending reverification; never silently change verification dates.
- Original contributions use CC0 1.0 Universal. Do not copy third-party source pages into the repository.
