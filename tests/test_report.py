"""Tests for markdown report rendering (pure, no DB)."""

from app.services.report import render_json, render_markdown


def make_report_data() -> dict:
    return {
        "investigation": {
            "name": "Acme probe",
            "status": "open",
            "created_at": "2026-09-01T10:00:00Z",
            "description": "Looking into acme.example",
        },
        "generated_at": "2026-09-26T12:00:00Z",
        "stats": {
            "target_count": 1,
            "finding_count": 1,
            "evidence_count": 1,
            "relation_count": 1,
            "source_count": 1,
            "by_confidence": {"CONFIRMED": 1},
            "by_finding_type": {"email": 1},
            "by_relation_type": {"RESOLVES_TO": 1},
        },
        "targets": [
            {
                "type": "domain",
                "value": "acme.example",
                "role": "primary",
                "findings": [
                    {
                        "value": "info@acme.example",
                        "type": "email",
                        "source": "dns",
                        "observed_at": "2026-09-02T08:00:00Z",
                        "confidence": "CONFIRMED",
                        "confidence_reason": "MX record match",
                        "evidence": [
                            {
                                "evidence_type": "dns_record",
                                "value": "MX acme.example",
                                "source": "dns",
                            }
                        ],
                    }
                ],
            }
        ],
        "relations": [
            {
                "relation_type": "RESOLVES_TO",
                "confidence": "LIKELY",
                "reason": "DNS resolution links domain to IP",
            }
        ],
        "timeline": [
            {
                "timestamp": "2026-09-02T08:00:00Z",
                "event_type": "finding",
                "description": "email discovered",
            }
        ],
        "sources": ["dns"],
    }


def test_markdown_contains_all_sections():
    md = render_markdown(make_report_data())
    for section in [
        "# Investigation: Acme probe",
        "## Summary",
        "## Targets & Findings",
        "### DOMAIN: `acme.example`",
        "## Relations",
        "## Timeline",
        "## Sources",
    ]:
        assert section in md, f"missing section: {section}"


def test_markdown_includes_stats_table_and_finding_details():
    md = render_markdown(make_report_data())
    assert "| Targets | 1 |" in md
    assert "- CONFIRMED: 1" in md
    assert "- **Type:** email" in md
    assert "- **Reason:** MX record match" in md
    assert "`MX acme.example`" in md


def test_markdown_truncates_long_relation_reason():
    data = make_report_data()
    data["relations"][0]["reason"] = "x" * 200
    md = render_markdown(data)
    assert "x" * 80 + "…" in md
    assert "x" * 81 not in md


def test_markdown_empty_relations_placeholder():
    data = make_report_data()
    data["relations"] = []
    data["stats"]["by_relation_type"] = {}
    md = render_markdown(data)
    assert "*No relations found. Run correlation first.*" in md


def test_render_json_returns_data_as_is():
    data = make_report_data()
    assert render_json(data) is data


def test_render_markdown_is_str():
    assert isinstance(render_markdown(make_report_data()), str)
