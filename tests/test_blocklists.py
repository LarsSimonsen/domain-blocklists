from copy import deepcopy
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch, MagicMock

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

    @patch.object(app, "urlopen")
    @patch.object(app.socket, "getaddrinfo")
    def test_review_flags_uncertainty_without_mutating_data(self, dns, fetch):
        entry = record()
        entry["verified_on"] = (date.today() - timedelta(days=91)).isoformat()
        original = deepcopy(entry)
        dns.side_effect = socket.gaierror("unavailable")
        fetch.side_effect = OSError("unavailable")
        findings = app.review([entry])
        self.assertEqual(len(findings), 3)
        self.assertEqual(entry, original)

    @patch.object(app, "urlopen")
    @patch.object(app.socket, "getaddrinfo")
    def test_review_flags_redirects(self, dns, fetch):
        response = MagicMock()
        response.geturl.return_value = "https://example.com/replacement"
        fetch.return_value.__enter__.return_value = response
        self.assertIn("redirected", app.review([record()])[0])
        response.geturl.return_value = "https://example.com/legal"
        self.assertEqual(app.review([record()]), [])


if __name__ == "__main__":
    unittest.main()
