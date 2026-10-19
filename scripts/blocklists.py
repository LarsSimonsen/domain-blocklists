"""Inspect verified records, validate YAML, add records, generate exports, preflight DNS, filter candidates, or flag review needs."""

import argparse
from datetime import date
from functools import lru_cache
import hashlib
import ipaddress
import http.client
import json
from pathlib import Path
import re
import socket
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPHandler, HTTPSHandler, ProxyHandler, Request, build_opener

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
    return validate_records(yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader), str(path))


def validate_records(records, label):
    if not isinstance(records, list):
        raise ValueError(f"{label}: expected a YAML list (use [] when empty)")
    seen = set()
    required = {"domain", "relationship", "verified_on", "sources"}
    for entry in records:
        if not isinstance(entry, dict) or not required <= entry.keys():
            raise ValueError(f"{label}: missing required record fields")
        if entry.keys() - required - {"notes"}:
            raise ValueError(f"{label}: unknown record fields")
        domain = entry["domain"]
        if not valid_domain(domain) or domain in seen:
            raise ValueError(f"{label}: invalid or duplicate domain {domain!r}")
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


DNS_PROVIDERS = (
    ("cloudflare-dns.com", "/dns-query", ("1.1.1.1", "1.0.0.1")),
    ("dns.google", "/resolve", ("8.8.8.8", "8.8.4.4")),
)


@lru_cache(maxsize=4096)
def dns_addresses(domain):
    """Use pinned public DoH endpoints; distinguish negatives from failures."""
    negatives = 0
    for host, path, endpoints in DNS_PROVIDERS:
        for endpoint in endpoints:
            addresses = []
            statuses = []
            has_alias = False
            try:
                for kind in ("A", "AAAA", "CNAME"):
                    connection = http.client.HTTPSConnection(host, timeout=10)
                    # Preserve TLS hostname verification while bypassing system DNS.
                    connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
                        (endpoint, 443), timeout, source_address)
                    try:
                        connection.request("GET", path + "?" + urlencode({"name": domain, "type": kind}),
                                           headers={"Accept": "application/dns-json"})
                        response = connection.getresponse()
                        if response.status != 200:
                            raise OSError("DNS service unavailable")
                        result = json.loads(response.read())
                    finally:
                        connection.close()
                    if not isinstance(result, dict) or not isinstance(result.get("Answer", []), list):
                        raise ValueError("Malformed DNS response")
                    statuses.append(result["Status"])
                    for answer in result.get("Answer", []):
                        if not isinstance(answer, dict):
                            raise ValueError("Malformed DNS answer")
                        has_alias = has_alias or answer["type"] == 5
                        if answer["type"] in (1, 28):
                            addresses.append(str(ipaddress.ip_address(answer["data"])))
                if addresses and all(status == 0 for status in statuses):
                    return list(dict.fromkeys(addresses))
                if not addresses and not has_alias and (statuses == [0, 0, 0] or statuses == [3, 3, 3]):
                    negatives += 1
                    # Retry the provider's second address before accepting a negative.
                    if endpoint == endpoints[-1]:
                        break
                else:
                    raise OSError("DNS response inconclusive")
            except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
                continue
    if negatives == 4:
        raise OSError("no addresses returned by Cloudflare and Google")
    raise OSError("public DNS checks inconclusive")


def public_connection(connection_type, host, **kwargs):
    connection = connection_type(host, **kwargs)
    def connect(address, timeout, source_address=None):
        last_error = None
        for ip in dns_addresses(address[0]):
            try:
                return socket.create_connection((ip, address[1]), timeout, source_address)
            except OSError as error:
                last_error = error
        raise last_error or OSError("No reachable address")
    connection._create_connection = connect
    return connection


class PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(lambda host, **kwargs: public_connection(
            http.client.HTTPSConnection, host, **kwargs), request,
            context=self._context)


class PublicHTTPHandler(HTTPHandler):
    def http_open(self, request):
        return self.do_open(lambda host, **kwargs: public_connection(
            http.client.HTTPConnection, host, **kwargs), request)


def review(records, emit=None):
    """Network signals are review prompts, never ownership determinations."""
    findings = []
    checked_sources = {}
    opener = build_opener(ProxyHandler({}), PublicHTTPHandler(), PublicHTTPSHandler())
    for entry in records:
        previous_count = len(findings)
        domain = entry["domain"]
        age = (date.today() - date.fromisoformat(str(entry["verified_on"]))).days
        if age > 90:
            findings.append(f"{domain}: verification is {age} days old")
        try:
            dns_addresses(domain)
        except OSError as error:
            findings.append(f"{domain}: {error}; check manually")
        for source in entry["sources"]:
            url = source["url"]
            if url not in checked_sources:
                try:
                    request = Request(url, headers={"User-Agent": "domain-blocklists-review/1.0"})
                    with opener.open(request, timeout=15) as response:
                        checked_sources[url] = (
                            "source redirected; confirm evidence manually"
                            if response.geturl() != url else None)
                except (OSError, ValueError, http.client.HTTPException):
                    checked_sources[url] = "source unavailable; check manually"
            if checked_sources[url]:
                findings.append(f"{domain}: {checked_sources[url]} ({url})")
        if emit:
            for finding in findings[previous_count:]:
                emit(finding)
    return findings


class RecordDumper(yaml.SafeDumper):
    """Indent nested sequences the way the datasets are written."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def add_records(path, packets, replace=False):
    """Insert verified records without rewriting or reordering the other records."""
    if isinstance(packets, dict):
        packets = [packets]
    if not isinstance(packets, list) or not packets:
        raise ValueError("add expects one record or a nonempty list of records on stdin")
    head, *blocks = re.split(r"(?m)^(?=- domain: )", path.read_text(encoding="utf-8"))
    blocks = [block if block.endswith("\n") else block + "\n" for block in blocks]
    names = [block.split("\n", 1)[0][len("- domain: "):].strip() for block in blocks]
    for packet in packets:
        if not isinstance(packet, dict) or not isinstance(packet.get("domain"), str):
            raise ValueError("each record must be an object with a domain")
        record = {"domain": packet["domain"], "relationship": packet.get("relationship"),
                  "verified_on": str(packet.get("verified_on") or date.today().isoformat()),
                  "sources": packet.get("sources")}
        if "notes" in packet:
            record["notes"] = packet["notes"]
        if packet.keys() - record.keys():
            raise ValueError(f"{record['domain']}: unknown record fields")
        rendered = yaml.dump([record], Dumper=RecordDumper, sort_keys=False,
                             allow_unicode=True, width=float("inf"))
        if record["domain"] in names:
            if not replace:
                raise ValueError(f"{record['domain']}: record exists; use --replace to reverify it")
            blocks[names.index(record["domain"])] = rendered
        else:
            # Keep the file's order; place the record before the first name that sorts after it.
            index = next((i for i, name in enumerate(names) if name > record["domain"]), len(names))
            blocks.insert(index, rendered)
            names.insert(index, record["domain"])
    text = head + "".join(blocks)
    validate_records(yaml.load(text, Loader=UniqueLoader), str(path))
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(packets)


def select_records(datasets, domains, offset, limit, include_related=False):
    """Select a stable, small work unit without loading all records into a prompt."""
    rows = [{"list": name, **entry} for name, records in datasets.items() for entry in records]
    coverage = []
    if domains:
        for domain in dict.fromkeys(domains):
            parents = [row["domain"] for row in rows
                       if domain == row["domain"] or domain.endswith("." + row["domain"])]
            descendants = [row["domain"] for row in rows if row["domain"].endswith("." + domain)]
            coverage.append({"domain": domain, "covered_by": sorted(set(parents)),
                             "listed_descendants": sorted(set(descendants))})
        if include_related:
            matched = {name for item in coverage
                       for name in item["covered_by"] + item["listed_descendants"]}
        else:
            matched = set(domains)
            missing = matched - {row["domain"] for row in rows}
            if missing:
                raise ValueError("No exact record for: " + ", ".join(sorted(missing)))
        rows = [row for row in rows if row["domain"] in matched]
    total = len(rows)
    selected = rows[offset:] if limit is None else rows[offset:offset + limit]
    next_offset = offset + len(selected)
    return {"matching_records": total, "offset": offset,
            "next_offset": next_offset if next_offset < total else None,
            "coverage": coverage, "records": selected}


def resolve_receipt(domain):
    """One receipt line per hostname; addresses are None unless it resolved."""
    try:
        addresses = dns_addresses(domain)
        return addresses, f"{domain}: resolved {' '.join(addresses)}"
    except OSError as error:
        state = "unresolved" if "Cloudflare and Google" in str(error) else "inconclusive"
        return None, f"{domain}: {state} ({error})"


def resolve(domains, emit=print):
    """Preflight hostnames through the approved resolvers; receipts, not ownership."""
    failures = 0
    for domain in dict.fromkeys(domains):
        addresses, receipt = resolve_receipt(domain)
        failures += addresses is None
        emit(receipt)
    return failures


def page_lines(body):
    """Crude tag stripping: block tags break lines, inline tags and source newlines do not."""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", "\n", " ".join(body.split()), flags=re.I)
    text = re.sub(r"</?(?:p|div|br|li|h[1-6]|t[rdh]|d[tdl]|[uo]l|table|title|section|article|"
                  r"header|footer|main|nav)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]*>", " ", text)
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def candidate(domains, path, expect, emit=print):
    """Discovery filter: resolve, fetch one evidence path, report whether the subject is named."""
    failures = 0
    needle = expect.casefold()
    opener = build_opener(ProxyHandler({}), PublicHTTPHandler(), PublicHTTPSHandler())
    for domain in dict.fromkeys(domains):
        addresses, receipt = resolve_receipt(domain)
        if addresses is None:
            failures += 1
            emit(receipt)
            continue
        url = f"https://{domain}{path}"
        try:
            request = Request(url, headers={"User-Agent": "domain-blocklists-candidate/1.0"})
            try:
                response = opener.open(request, timeout=15)
            except HTTPError as error:
                response = error  # An error page is still a retrieved page.
            with response as page:
                final, status = page.geturl(), page.status
                body = page.read(1 << 20).decode("utf-8", "replace")
        except (OSError, ValueError, http.client.HTTPException) as error:
            failures += 1
            emit(f"{domain}: unavailable {url} ({error})")
            continue
        if status == 429 or (status == 202 and not body.strip()):
            failures += 1  # A rate limit or bot challenge is a retry case, not a page.
            emit(f"{domain}: unavailable {url} (challenge status {status})")
            continue
        lines = page_lines(body)
        index = next((i for i, line in enumerate(lines) if needle in line.casefold()), None)
        host = urlsplit(final).hostname or ""
        if host != domain and not host.endswith("." + domain):
            state = "redirected"
        else:
            state = "hit" if index is not None else "miss"
        failures += state != "hit"
        emit(f"{domain}: {state} {url} final {final} status {status} "
             f"subject {'named' if index is not None else 'not named'}")
        if index is not None:
            for line in lines[max(index - 1, 0):index + 2]:
                emit(f"  {line[:200]}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check", "review", "inspect", "resolve", "candidate", "add"))
    parser.add_argument("--list", dest="list_name", help="Select one dataset (inspect/review only)")
    parser.add_argument("--domain", action="append", default=[], help="Select a hostname; repeatable")
    parser.add_argument("--offset", type=int, default=0, help="Skip records in sorted order")
    parser.add_argument("--limit", type=int, help="Maximum records; inspect defaults to 5")
    parser.add_argument("--path", help="Evidence path to fetch on each hostname (candidate only)")
    parser.add_argument("--expect", help="Subject string to look for, case-insensitive (candidate only)")
    parser.add_argument("--replace", action="store_true", help="Let add overwrite an existing record (add only)")
    args = parser.parse_args()
    if args.offset < 0 or (args.limit is not None and args.limit < 1):
        parser.error("offset must be nonnegative and limit must be positive")
    if args.command in ("build", "check") and (
            args.list_name or args.domain or args.offset or args.limit is not None):
        parser.error("build/check always cover all lists; selection requires inspect/review")
    if args.command == "resolve" and (
            not args.domain or args.list_name or args.offset or args.limit is not None):
        parser.error("resolve takes one or more --domain and no selection options")
    if args.command == "candidate" and (
            not args.domain or args.list_name or args.offset or args.limit is not None
            or not args.path or not args.path.startswith("/") or any(c.isspace() for c in args.path)
            or not args.expect or not args.expect.strip()):
        parser.error("candidate takes one or more --domain, --path starting with /, --expect, "
                     "and no selection options")
    if args.command != "candidate" and (args.path or args.expect):
        parser.error("--path and --expect apply to candidate only")
    if args.command == "add" and (
            not args.list_name or args.domain or args.offset or args.limit is not None):
        parser.error("add takes --list, optional --replace, and records as JSON on stdin")
    if args.replace and args.command != "add":
        parser.error("--replace applies to add only")
    try:
        if any(not valid_domain(domain) for domain in args.domain):
            raise ValueError("--domain requires a lowercase hostname, without a URL or wildcard")
        if args.command == "resolve":
            failures = resolve(args.domain)
            print("Resolver receipts do not verify ownership or continued evidential support.")
            return 1 if failures else 0
        if args.command == "candidate":
            failures = candidate(args.domain, args.path, args.expect)
            print("Candidate checks are filter results, not ownership decisions.")
            return 1 if failures else 0
        paths = sorted((ROOT / "data").glob("*.yaml"))
        if not paths:
            raise ValueError("No datasets found")
        datasets = {path.stem: load_records(path) for path in paths}
        if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in datasets):
            raise ValueError("Invalid dataset filename")
        if args.list_name:
            if args.list_name not in datasets:
                raise ValueError(f"Unknown list: {args.list_name}")
            datasets = {args.list_name: datasets[args.list_name]}
        if args.command == "add":
            path = ROOT / "data" / f"{args.list_name}.yaml"
            count = add_records(path, json.load(sys.stdin), args.replace)
            print(f"add: {count} record(s) written to {path.relative_to(ROOT).as_posix()}; run build, check, and tests")
            return 0
        if args.command in ("inspect", "review"):
            limit = 5 if args.command == "inspect" and args.limit is None else args.limit
            packet = select_records(datasets, args.domain, args.offset, limit,
                                    include_related=args.command == "inspect")
            if args.command == "inspect":
                packet["dataset_sha256"] = {path.stem: hashlib.sha256(path.read_bytes()).hexdigest()
                                            for path in paths if path.stem in datasets}
                print(json.dumps(packet, default=str, ensure_ascii=False, indent=2))
                return 0
            if not packet["records"] and packet["matching_records"]:
                raise ValueError("No records selected; offset is past the end")
            datasets = {name: [row for row in packet["records"] if row["list"] == name]
                        for name in datasets}
        expected = {}
        findings = []
        for name, records in datasets.items():
            if args.command == "review":
                findings.extend(review(records, emit=lambda finding: print(f"- {finding}", flush=True)))
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
            if args.command != "review":
                print(f"- {finding}")
        total = sum(map(len, datasets.values()))
        print(f"{args.command}: {len(datasets)} list(s), {total} verified record(s), {len(findings)} finding(s)")
        if args.command == "review":
            print(f"Selection: {total} of {packet['matching_records']} matching record(s); "
                  f"next offset: {packet['next_offset']}")
            print("Availability checks do not verify ownership or continued evidential support.")
        return 1 if findings else 0
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
