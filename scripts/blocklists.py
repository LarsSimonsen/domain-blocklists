"""Validate verified YAML records, generate exports, or flag entries for review."""

import argparse
from datetime import date
import ipaddress
from pathlib import Path
import re
import socket
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys rather than silently discard evidence."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError(f"Invalid or duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def valid_domain(value):
    if not isinstance(value, str) or len(value) > 253:
        return False
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        pass
    labels = value.split(".")
    return (len(labels) > 1 and not labels[-1].isdigit()
            and all(LABEL.fullmatch(label) for label in labels))


def load_records(path):
    records = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected a YAML list (use [] when empty)")
    seen = set()
    required = {"domain", "relationship", "verified_on", "sources"}
    for entry in records:
        if not isinstance(entry, dict) or not required <= entry.keys():
            raise ValueError(f"{path}: missing required record fields")
        if entry.keys() - required - {"notes"}:
            raise ValueError(f"{path}: unknown record fields")
        domain = entry["domain"]
        if not valid_domain(domain) or domain in seen:
            raise ValueError(f"{path}: invalid or duplicate domain {domain!r}")
        seen.add(domain)
        if entry["relationship"] not in ("owned", "operated", "dedicated-hostname"):
            raise ValueError(f"{domain}: invalid relationship")
        raw_date = str(entry["verified_on"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            raise ValueError(f"{domain}: verified_on must be YYYY-MM-DD")
        verified = date.fromisoformat(raw_date)
        if verified > date.today():
            raise ValueError(f"{domain}: verification date is in the future")
        if "notes" in entry:
            notes = entry["notes"]
            if not isinstance(notes, str) or not notes.strip():
                raise ValueError(f"{domain}: notes must be nonempty text")
            if notes.casefold().startswith("discovery provenance:"):
                raise ValueError(
                    f"{domain}: keep discovery provenance outside the dataset")
        sources = entry["sources"]
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{domain}: at least one source is required")
        for source in sources:
            if not isinstance(source, dict) or set(source) != {"url", "evidence"}:
                raise ValueError(f"{domain}: sources require url and evidence")
            if not all(isinstance(v, str) and v.strip() for v in source.values()):
                raise ValueError(f"{domain}: source fields must be nonempty text")
            url = urlsplit(source["url"])
            if (url.scheme not in ("http", "https") or not valid_domain(url.hostname)
                    or url.username or url.password or any(c.isspace() for c in source["url"])):
                raise ValueError(f"{domain}: invalid public source URL")
    return sorted(records, key=lambda entry: entry["domain"])


def exports(records):
    domains = [entry["domain"] for entry in records]
    plain = "".join(f"{domain}\n" for domain in domains)
    rules = "! Generated from verified records; do not edit.\n"
    rules += f"! Entries: {len(domains)}; includes descendants of each listed name.\n"
    rules += "".join(f"||{domain}^\n" for domain in domains)
    return {"domains.txt": plain, "pihole.txt": rules, "adguard.txt": rules}


def review(records):
    """Network signals are review prompts, never ownership determinations."""
    findings = []
    checked_sources = {}
    for entry in records:
        domain = entry["domain"]
        age = (date.today() - date.fromisoformat(str(entry["verified_on"]))).days
        if age > 90:
            findings.append(f"{domain}: verification is {age} days old")
        try:
            socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        except OSError:
            findings.append(f"{domain}: DNS address lookup failed; check manually")
        for source in entry["sources"]:
            url = source["url"]
            if url not in checked_sources:
                try:
                    request = Request(url, headers={"User-Agent": "domain-blocklists-review/1.0"})
                    with urlopen(request, timeout=15) as response:
                        checked_sources[url] = (
                            "source redirected; confirm evidence manually"
                            if response.geturl() != url else None)
                except (OSError, ValueError):
                    checked_sources[url] = "source unavailable; check manually"
            if checked_sources[url]:
                findings.append(f"{domain}: {checked_sources[url]} ({url})")
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check", "review"))
    args = parser.parse_args()
    try:
        paths = sorted((ROOT / "data").glob("*.yaml"))
        if not paths:
            raise ValueError("No datasets found")
        datasets = {path.stem: load_records(path) for path in paths}
        expected = {}
        findings = []
        for name, records in datasets.items():
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
                raise ValueError(f"Invalid dataset filename: {name}")
            if args.command == "review":
                findings.extend(review(records))
            else:
                for filename, content in exports(records).items():
                    expected[ROOT / "lists" / name / filename] = content.encode("utf-8")
        if args.command == "build":
            for path, content in expected.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        elif args.command == "check":
            for path, content in expected.items():
                if not path.is_file() or path.read_bytes() != content:
                    findings.append(f"Stale or missing export: {path.relative_to(ROOT)}")
            for path in (ROOT / "lists").rglob("*.txt"):
                if path not in expected:
                    findings.append(f"Unexpected export: {path.relative_to(ROOT)}")
        for finding in findings:
            print(f"- {finding}")
        total = sum(map(len, datasets.values()))
        print(f"{args.command}: {len(datasets)} list(s), {total} verified record(s), {len(findings)} finding(s)")
        if args.command == "review":
            print("Availability checks do not verify ownership or continued evidential support.")
        return 1 if findings else 0
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
