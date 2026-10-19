from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
from datetime import date, timedelta
import importlib.util
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

import yaml

spec = importlib.util.spec_from_file_location(
    "blocklists", Path(__file__).resolve().parents[1] / "scripts" / "blocklists.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def record(domain="tenant.example.com"):
    return {"domain": domain, "relationship": "dedicated-hostname",
            "verified_on": date.today().isoformat(),
            "sources": [{"url": "https://example.com/legal",
                         "evidence": "Synthetic evidence for tests only."}]}


class BlocklistsTests(unittest.TestCase):
    def load(self, records):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.yaml"
            path.write_text(yaml.safe_dump(records), encoding="utf-8")
            return app.load_records(path)

    def test_records_are_sorted_and_evidence_retained(self):
        records = self.load([record("z.example.com"), record("a.example.com")])
        self.assertEqual([r["domain"] for r in records], ["a.example.com", "z.example.com"])
        self.assertEqual(records[0]["sources"], record()["sources"])

    def test_rejects_invalid_names(self):
        for domain in ["*.example.com", "Example.com", "example.com/path",
                       "127.0.0.1", "com", "example.com.", "-bad.example", "a..com"]:
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                self.load([record(domain)])

    def test_rejects_unverified_or_incomplete_records(self):
        for key, value in [("sources", []), ("relationship", "affiliate"),
                           ("verified_on", "2099-01-01"), ("status", "candidate")]:
            entry = record()
            entry[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load([entry])
        for source in [{"url": "file:///private", "evidence": "Claim"},
                       {"url": "https://example.com", "evidence": ""}]:
            entry = record()
            entry["sources"] = [source]
            with self.assertRaises(ValueError):
                self.load([entry])

    def test_rejects_discovery_provenance_notes(self):
        entry = record()
        entry["notes"] = "Discovery provenance: found in a regional search."
        with self.assertRaises(ValueError):
            self.load([entry])

    def test_rejects_duplicate_domains_and_yaml_keys(self):
        with self.assertRaises(ValueError):
            self.load([record(), record()])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.yaml"
            path.write_text("- domain: a.example\n  domain: b.example\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                app.load_records(path)

    def test_exports_preserve_shared_service_boundary(self):
        output = app.exports(self.load([record()]))
        self.assertEqual(output["domains.txt"], "tenant.example.com\n")
        self.assertEqual(output["pihole.txt"], output["adguard.txt"])
        rules = [line for line in output["pihole.txt"].splitlines() if not line.startswith("!")]
        self.assertEqual(rules, ["||tenant.example.com^"])
        self.assertNotIn("||example.com^", output["pihole.txt"])

    def test_empty_list_has_no_blocking_rules(self):
        output = app.exports(self.load([]))
        self.assertEqual(output["domains.txt"], "")
        self.assertNotIn("||", output["adguard.txt"])

    def test_check_detects_stale_and_unexpected_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data" / "headout.yaml").write_text("[]\n", encoding="utf-8")
            with patch.object(app, "ROOT", root), patch("sys.argv", ["script", "build"]):
                self.assertEqual(app.main(), 0)
            with patch.object(app, "ROOT", root), patch("sys.argv", ["script", "check"]):
                self.assertEqual(app.main(), 0)
                (root / "lists" / "headout" / "domains.txt").write_text("bad.example\n")
                self.assertEqual(app.main(), 1)
                (root / "lists" / "headout" / "domains.txt").write_text("")
                (root / "lists" / "headout" / "old.txt").write_text("")
                self.assertEqual(app.main(), 1)

    @patch.object(app, "build_opener")
    @patch.object(app, "dns_addresses")
    def test_review_flags_uncertainty_without_mutating_data(self, dns, fetch):
        entry = record()
        entry["verified_on"] = (date.today() - timedelta(days=91)).isoformat()
        original = deepcopy(entry)
        dns.side_effect = socket.gaierror("unavailable")
        fetch.return_value.open.side_effect = OSError("unavailable")
        findings = app.review([entry])
        self.assertEqual(len(findings), 3)
        self.assertEqual(entry, original)

    @patch.object(app, "build_opener")
    @patch.object(app, "dns_addresses")
    def test_review_flags_redirects(self, dns, fetch):
        response = MagicMock()
        response.geturl.return_value = "https://example.com/replacement"
        fetch.return_value.open.return_value.__enter__.return_value = response
        self.assertIn("redirected", app.review([record()])[0])
        response.geturl.return_value = "https://example.com/legal"
        self.assertEqual(app.review([record()]), [])

    @patch.object(app, "build_opener")
    @patch.object(app, "dns_addresses")
    def test_review_emits_findings_before_later_failure(self, dns, fetch):
        emitted = []
        dns.side_effect = [OSError("inconclusive"), RuntimeError("interrupted")]
        fetch.return_value.open.side_effect = OSError("unavailable")
        with self.assertRaises(RuntimeError):
            app.review([record("a.example.com"), record("b.example.com")], emit=emitted.append)
        self.assertEqual(len(emitted), 2)
        self.assertTrue(all(line.startswith("a.example.com:") for line in emitted))


class SelectionTests(unittest.TestCase):
    def test_coverage_respects_label_and_shared_service_boundaries(self):
        records = [record("tenant.example.com"), record("whole.example")]
        result = app.select_records({"test": records}, ["x.tenant.example.com", "example.com",
                                    "nottenant.example.com", "whole.example"], 0, 5, True)
        self.assertEqual(result["coverage"][0]["covered_by"], ["tenant.example.com"])
        self.assertEqual(result["coverage"][1]["covered_by"], [])
        self.assertEqual(result["coverage"][1]["listed_descendants"], ["tenant.example.com"])
        self.assertEqual(result["coverage"][2]["covered_by"], [])
        self.assertEqual(result["coverage"][3]["covered_by"], ["whole.example"])

    def test_pagination_does_not_skip_or_duplicate_records(self):
        records = [record(f"host{i}.example") for i in range(12)]
        gathered, offset = [], 0
        while offset is not None:
            packet = app.select_records({"test": records}, [], offset, 5)
            gathered.extend(packet["records"])
            offset = packet["next_offset"]
        self.assertEqual([r["domain"] for r in gathered], [r["domain"] for r in records])

    def test_review_rejects_unknown_exact_record(self):
        with self.assertRaisesRegex(ValueError, "No exact record"):
            app.select_records({"test": [record()]}, ["missing.example"], 0, 5)

    def test_cli_packet_default_limit_and_dataset_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            path = root / "data" / "test.yaml"
            path.write_text(yaml.safe_dump([record(f"host{i}.example") for i in range(8)]))
            output = io.StringIO()
            with patch.object(app, "ROOT", root), patch("sys.argv", ["script", "inspect"]), redirect_stdout(output):
                self.assertEqual(app.main(), 0)
            packet = json.loads(output.getvalue())
            self.assertEqual(len(packet["records"]), 5)
            self.assertEqual(packet["next_offset"], 5)
            self.assertEqual(packet["matching_records"], 8)
            self.assertEqual(packet["dataset_sha256"]["test"], app.hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertFalse((root / "lists").exists())

    def test_cli_rejects_invalid_selection_and_partial_build(self):
        for args in [("inspect", "--limit", "0"), ("review", "--offset", "-1"),
                     ("build", "--list", "test"), ("check", "--domain", "a.example"),
                     ("resolve",), ("resolve", "--domain", "a.example", "--limit", "1"),
                     ("add",), ("add", "--list", "test", "--domain", "a.example"), ("inspect", "--replace"),
                     ("candidate", "--domain", "a.example", "--expect", "Subject"),
                     ("candidate", "--domain", "a.example", "--path", "legal", "--expect", "Subject"),
                     ("resolve", "--domain", "a.example", "--path", "/legal")]:
            with self.subTest(args=args), patch("sys.argv", ["script", *args]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    app.main()
                self.assertEqual(error.exception.code, 2)

    @patch.object(app, "dns_addresses")
    def test_cli_resolve_reports_receipts_without_touching_data(self, dns):
        dns.side_effect = [["192.0.2.1"], OSError("no addresses returned by Cloudflare and Google"),
                           OSError("public DNS checks inconclusive")]
        output = io.StringIO()
        with patch("sys.argv", ["script", "resolve", "--domain", "a.example", "--domain", "b.example",
                                "--domain", "c.example", "--domain", "a.example"]), redirect_stdout(output):
            self.assertEqual(app.main(), 1)
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[0], "a.example: resolved 192.0.2.1")
        self.assertTrue(lines[1].startswith("b.example: unresolved"))
        self.assertTrue(lines[2].startswith("c.example: inconclusive"))
        self.assertEqual(dns.call_count, 3)

    @patch.object(app, "build_opener")
    @patch.object(app, "dns_addresses")
    def test_cli_candidate_reports_filter_results(self, dns, fetch):
        def page(url, body):
            manager = MagicMock()
            manager.__enter__.return_value = MagicMock(status=200, **{
                "geturl.return_value": url, "read.return_value": body})
            return manager
        dns.side_effect = [["192.0.2.1"]] * 4 + [OSError("no addresses returned by Cloudflare and Google")]
        fetch.return_value.open.side_effect = [
            page("https://www.a.example/legal", b"<html><script>var subject = 1;</script><h1>Terms</h1>"
                 b"<p>Operated by <b>Subject</b>\n Ltd.</p><p>Registered office.</p><p>" + b"x" * 300 + b"</p></html>"),
            HTTPError("https://b.example/legal", 404, "Not Found", {}, io.BytesIO(b"<p>No such name here.</p>")),
            page("https://other.example/legal", b"<p>Subject Ltd runs this site.</p>"),
            OSError("unavailable")]
        output = io.StringIO()
        with patch("sys.argv", ["script", "candidate", "--path", "/legal", "--expect", "subject",
                                "--domain", "a.example", "--domain", "b.example", "--domain", "c.example",
                                "--domain", "d.example", "--domain", "e.example"]), redirect_stdout(output):
            self.assertEqual(app.main(), 1)
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[0], "a.example: hit https://a.example/legal final https://www.a.example/legal "
                                   "status 200 subject named")
        self.assertEqual(lines[1:4], ["  Terms", "  Operated by Subject Ltd.", "  Registered office."])
        self.assertEqual(lines[4], "b.example: miss https://b.example/legal final https://b.example/legal "
                                   "status 404 subject not named")
        self.assertTrue(lines[5].startswith("c.example: redirected https://c.example/legal final "
                                            "https://other.example/legal"))
        self.assertEqual(lines[6], "  Subject Ltd runs this site.")
        self.assertTrue(lines[7].startswith("d.example: unavailable https://d.example/legal"))
        self.assertTrue(lines[8].startswith("e.example: unresolved"))
        self.assertEqual(lines[9], "Candidate checks are filter results, not ownership decisions.")
        self.assertEqual(len(lines), 10)
        first = fetch.return_value.open.call_args_list[0]
        self.assertEqual((first.args[0].full_url, first.kwargs), ("https://a.example/legal", {"timeout": 15}))
        self.assertEqual(dns.call_count, 5)

    @patch.object(app, "build_opener")
    @patch.object(app, "dns_addresses", return_value=["192.0.2.1"])
    def test_cli_candidate_exits_zero_only_for_hits_on_own_hostname(self, dns, fetch):
        response = MagicMock(status=200, **{"geturl.return_value": "https://a.example/legal",
                                            "read.return_value": b"<p>" + b"Subject " * 60 + b"</p>"})
        fetch.return_value.open.return_value.__enter__.return_value = response
        output = io.StringIO()
        with patch("sys.argv", ["script", "candidate", "--path", "/legal", "--expect", "Subject",
                                "--domain", "a.example", "--domain", "a.example"]), redirect_stdout(output):
            self.assertEqual(app.main(), 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(lines[1]), 2 + 200)
        self.assertEqual(fetch.return_value.open.call_count, 1)

    @patch.object(app, "build_opener")
    @patch.object(app, "dns_addresses", return_value=["192.0.2.1"])
    def test_cli_candidate_reports_challenges_as_unavailable(self, dns, fetch):
        def page(url, status, body):
            manager = MagicMock()
            manager.__enter__.return_value = MagicMock(status=status, **{
                "geturl.return_value": url, "read.return_value": body})
            return manager
        fetch.return_value.open.side_effect = [
            page("https://a.example/legal", 202, b""),
            HTTPError("https://b.example/legal", 429, "Too Many Requests", {}, io.BytesIO(b"<p>Slow down.</p>")),
            page("https://c.example/legal", 202, b"<p>Subject Ltd.</p>")]
        output = io.StringIO()
        with patch("sys.argv", ["script", "candidate", "--path", "/legal", "--expect", "Subject",
                                "--domain", "a.example", "--domain", "b.example", "--domain", "c.example"]), redirect_stdout(output):
            self.assertEqual(app.main(), 1)
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[0], "a.example: unavailable https://a.example/legal (challenge status 202)")
        self.assertEqual(lines[1], "b.example: unavailable https://b.example/legal (challenge status 429)")
        self.assertEqual(lines[2], "c.example: hit https://c.example/legal final https://c.example/legal "
                                   "status 202 subject named")

    def test_add_inserts_sorted_and_leaves_other_records_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.yaml"
            path.write_text("# header\n" + yaml.safe_dump([record("b.example"), record("d.example")]), newline="\n")
            before = path.read_text()
            packet = {"domain": "c.example", "relationship": "owned",
                      "sources": [{"url": "https://c.example/legal", "evidence": "States ownership."}]}
            self.assertEqual(app.add_records(path, packet), 1)
            after = path.read_text()
            self.assertTrue(after.startswith("# header\n"))
            for block in before.split("- domain: ")[1:]:
                self.assertIn("- domain: " + block, after)
            records = app.load_records(path)
            self.assertEqual([r["domain"] for r in records], ["b.example", "c.example", "d.example"])
            self.assertEqual(str(records[1]["verified_on"]), date.today().isoformat())
            self.assertIn("verified_on: '" + date.today().isoformat() + "'", after)
            self.assertIn("    - url: https://c.example/legal", after)
            for bad in [packet, {**packet, "domain": "e.example", "extra": 1},
                        {**packet, "domain": "e.example", "relationship": "partner"},
                        {**packet, "domain": "e.example", "verified_on": "2999-01-01"}, [], "text"]:
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    app.add_records(path, bad)
                self.assertEqual(path.read_text(), after)
            replaced = {**packet, "verified_on": "2026-01-02", "notes": "Boundary note."}
            self.assertEqual(app.add_records(path, [replaced], replace=True), 1)
            self.assertEqual(app.load_records(path)[1]["notes"], "Boundary note.")
            self.assertEqual(len(app.load_records(path)), 3)

    def test_cli_add_reads_packets_from_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data" / "test.yaml").write_text(yaml.safe_dump([record("a.example")]))
            packet = json.dumps({"domain": "b.example", "relationship": "operated",
                                 "sources": [{"url": "https://b.example/legal", "evidence": "Names the entity."}]})
            with patch.object(app, "ROOT", root), patch("sys.argv", ["script", "add", "--list", "test"]), \
                    patch("sys.stdin", io.StringIO(packet)), redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(), 0)
            self.assertEqual([r["domain"] for r in app.load_records(root / "data" / "test.yaml")],
                             ["a.example", "b.example"])
            with patch.object(app, "ROOT", root), patch("sys.argv", ["script", "add", "--list", "test"]), \
                    patch("sys.stdin", io.StringIO(packet)), redirect_stderr(io.StringIO()):
                self.assertEqual(app.main(), 1)
            self.assertFalse((root / "lists").exists())

    @patch.object(app, "review", return_value=[])
    def test_cli_review_only_checks_selected_records(self, review):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data" / "test.yaml").write_text(yaml.safe_dump([record("a.example"), record("b.example")]))
            with patch.object(app, "ROOT", root), patch("sys.argv", ["script", "review", "--list", "test", "--offset", "1", "--limit", "1"]), redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(), 0)
            self.assertEqual([r["domain"] for r in review.call_args.args[0]], ["b.example"])


class PublicDNSTests(unittest.TestCase):
    def setUp(self):
        app.dns_addresses.cache_clear()

    @patch.object(app.http.client, "HTTPSConnection")
    def test_retries_primary_then_uses_independent_provider(self, connection):
        import json
        reply = MagicMock(status=200)
        reply.read.return_value = json.dumps({"Status": 0, "Answer": [
            {"type": 1, "data": "192.0.2.1"}]}).encode()
        primary = MagicMock()
        primary.request.side_effect = OSError("unavailable")
        secondary = MagicMock()
        secondary.getresponse.return_value = reply
        connection.side_effect = [primary, primary, secondary, secondary, secondary]
        self.assertEqual(app.dns_addresses("test.example"), ["192.0.2.1"])
        self.assertEqual([call.args[0] for call in connection.call_args_list],
                         ["cloudflare-dns.com"] * 2 + ["dns.google"] * 3)

    @patch.object(app.http.client, "HTTPSConnection")
    def test_negative_requires_both_addresses_of_both_providers(self, connection):
        reply = MagicMock(status=200)
        reply.read.return_value = b'{"Status": 3}'
        connection.return_value.getresponse.return_value = reply
        with self.assertRaisesRegex(OSError, "Cloudflare and Google"):
            app.dns_addresses("missing.example")
        self.assertEqual(connection.call_count, 12)

    @patch.object(app.http.client, "HTTPSConnection")
    def test_single_provider_negative_and_other_failure_is_inconclusive(self, connection):
        reply = MagicMock(status=200)
        reply.read.return_value = b'{"Status": 3}'
        primary = MagicMock()
        primary.getresponse.return_value = reply
        secondary = MagicMock()
        secondary.request.side_effect = OSError("unavailable")
        connection.side_effect = [primary] * 6 + [secondary] * 2
        with self.assertRaisesRegex(OSError, "inconclusive"):
            app.dns_addresses("test.example")

    @patch.object(app.http.client, "HTTPSConnection")
    def test_alias_only_and_malformed_answers_are_inconclusive(self, connection):
        for payload in [{"Status": 0, "Answer": [{"type": 5, "data": "target.example"}]},
                        [], {"Status": 0, "Answer": [None]}, {"Status": 2}]:
            with self.subTest(payload=payload):
                reply = MagicMock(status=200)
                reply.read.return_value = json.dumps(payload).encode()
                connection.return_value.getresponse.return_value = reply
                with self.assertRaisesRegex(OSError, "inconclusive"):
                    app.dns_addresses("alias.example")

    @patch.object(app.socket, "create_connection")
    @patch.object(app.http.client, "HTTPSConnection")
    def test_doh_connects_to_public_ip_with_original_tls_host(self, connection, connect):
        reply = MagicMock(status=200)
        reply.read.return_value = b'{"Status": 3}'
        def make_connection(host, **kwargs):
            instance = MagicMock()
            instance.request.side_effect = lambda *args, **kw: instance._create_connection((host, 443), 10)
            instance.getresponse.return_value = reply
            return instance
        connection.side_effect = make_connection
        with self.assertRaises(OSError):
            app.dns_addresses("missing.example")
        endpoints = [call.args[0] for call in connect.call_args_list]
        self.assertEqual(endpoints, [(ip, 443) for ip in ("1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4") for _ in range(3)])

    @patch.object(app.socket, "create_connection")
    @patch.object(app, "dns_addresses", return_value=["192.0.2.1", "2001:db8::1"])
    def test_web_connection_retries_addresses_and_keeps_tls_hostname(self, dns, connect):
        connect.side_effect = [OSError("unreachable"), MagicMock()]
        connection = app.public_connection(app.http.client.HTTPSConnection, "legal.example", timeout=15)
        self.assertEqual(connection.host, "legal.example")
        connection._create_connection(("legal.example", 443), 15)
        dns.assert_called_once_with("legal.example")
        self.assertEqual([call.args[0] for call in connect.call_args_list],
                         [("192.0.2.1", 443), ("2001:db8::1", 443)])


if __name__ == "__main__":
    unittest.main()
