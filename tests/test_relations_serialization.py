"""Tests of the pure relations serialization enrichment.

The enrichment logic must live in a pure function (`build_relation_items`)
so that it can be unit-tested without a DB session. These tests use
`SimpleNamespace` stand-ins for the ORM objects; no sqlalchemy dep needed.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

# Make `app` importable from the repo root regardless of CWD.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_finding(fid, type_, value, target_id):
    return SimpleNamespace(
        id=fid,
        type=type_,
        value=value,
        target_id=target_id,
    )


def make_relation(
    rid,
    source_finding_id,
    target_finding_id,
    relation_type,
    confidence,
    reason,
):
    return SimpleNamespace(
        id=rid,
        source_finding_id=source_finding_id,
        target_finding_id=target_finding_id,
        relation_type=relation_type,
        confidence=confidence,
        reason=reason,
        created_at="2026-09-24T12:00:00Z",
    )


class BuildRelationItemsTest(unittest.TestCase):
    def setUp(self):
        from app.services.correlation import build_relation_items

        self.build = build_relation_items

        self.findings = {
            "f1": make_finding("f1", "dns_record", "example.com", "t1"),
            "f2": make_finding("f2", "ip_address", "1.2.3.4", "t2"),
        }

    def test_enriches_relation_with_finding_details(self):
        rel = make_relation(
            "r1",
            "f1",
            "f2",
            "RESOLVES_TO",
            "CONFIRMED",
            "dns A record points to IP",
        )
        items = self.build([rel], self.findings)
        self.assertEqual(len(items), 1)

        item = items[0]
        # Existing fields preserved.
        self.assertEqual(item["id"], "r1")
        self.assertEqual(item["source_finding_id"], "f1")
        self.assertEqual(item["target_finding_id"], "f2")
        self.assertEqual(item["relation_type"], "RESOLVES_TO")
        self.assertEqual(item["confidence"], "CONFIRMED")
        self.assertEqual(item["reason"], "dns A record points to IP")

        # Enriched source finding details.
        self.assertEqual(item["source_finding_type"], "dns_record")
        self.assertEqual(item["source_finding_value"], "example.com")
        self.assertEqual(item["source_finding_target_id"], "t1")
        # Enriched target finding details.
        self.assertEqual(item["target_finding_type"], "ip_address")
        self.assertEqual(item["target_finding_value"], "1.2.3.4")
        self.assertEqual(item["target_finding_target_id"], "t2")

    def test_returns_none_for_orphan_findings(self):
        # relation points to findings not present in the mapping
        rel = make_relation("r2", "unknown_s", "f2", "RESOLVES_TO", "LIKELY", "x")
        items = self.build([rel], self.findings)
        self.assertEqual(len(items), 1)
        item = items[0]

        self.assertEqual(item["source_finding_type"], None)
        self.assertEqual(item["source_finding_value"], None)
        self.assertEqual(item["source_finding_target_id"], None)
        # target side still enriched
        self.assertEqual(item["target_finding_type"], "ip_address")
        self.assertEqual(item["target_finding_value"], "1.2.3.4")

    def test_empty_inputs(self):
        self.assertEqual(self.build([], {}), [])
        self.assertEqual(self.build([], self.findings), [])


if __name__ == "__main__":
    unittest.main()
