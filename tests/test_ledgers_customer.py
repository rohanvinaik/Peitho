"""INTEGRATION test for peitho.ledgers.export_customer — the customer domain ledger, the deepest orchestrator
(load master -> resolve identities -> build nodes -> mine RFM baselines -> segment -> pseudonymize).
The two file-reading leaves (load_clean_master, load_bills_by_customer) are stubbed; everything between runs
FOR REAL by feeding genuine `clean_record` output on synthetic raw customer-master dicts through the pipeline.

The load-bearing contract pinned here is the SEPARABLE-PII invariant: the always-on customers.json is
PSEUDONYMOUS + STRUCTURAL (node_id, reg-store prefixes, segment, RFM) and carries NO name / mobile / full
code; the re-identification crosswalk is written ONLY under emit_identity=True, to a separate file.
"""

import json

import peitho.customer as cust
import peitho.ledgers as led


def _records():
    # two people share a mobile (household, distinct names); a third is separate. real clean_record output.
    raw = [
        {
            "customerCode": "AH0000000001",
            "mobile": "5551234567",
            "name": "MR JOHN SMITH",
            "gender": "M",
            "created": "2024-01-15",
        },
        {
            "customerCode": "AH0000000002",
            "mobile": "5551234567",
            "name": "MRS JANE SMITH",
            "gender": "F",
            "created": "2024-02-20",
        },
        {
            "customerCode": "AC0000000009",
            "mobile": "5559998888",
            "name": "MIKE BROWN",
            "gender": "M",
            "created": "2025-06-01",
        },
    ]
    return [cust.clean_record(r) for r in raw]


def _bills():
    # each code has active, non-cancelled bills so the nodes are ACTIVE and baselines are real
    return {
        "AH0000000001": [{"date": "2026-07-01", "bill_no": "AH-26-1001", "amount": 4500, "cancelled": False}],
        "AH0000000002": [{"date": "2026-06-15", "bill_no": "AH-26-1002", "amount": 1200, "cancelled": False}],
        "AC0000000009": [{"date": "2026-01-10", "bill_no": "AC-26-2003", "amount": 8000, "cancelled": False}],
    }


def _stub(monkeypatch):
    monkeypatch.setattr(cust, "load_clean_master", lambda: _records())
    monkeypatch.setattr(cust, "load_bills_by_customer", lambda: _bills())


def test_export_customers_is_pseudonymous_structural(tmp_path, monkeypatch):
    _stub(monkeypatch)
    out = tmp_path / "customers.json"
    summary = led.export_customer(str(out), today="2026-08-15")
    written = json.loads(out.read_text())

    assert written["domain"] == "customer"  # the domain-ledger wrapper
    assert set(summary) == {"persons", "active", "households", "segments", "rfm_baselines"}
    assert summary["persons"] == len(written["nodes"]) >= 1
    node = written["nodes"][0]
    assert node["node_id"].startswith("c:")  # pseudonym, salted hash
    assert node["reg_stores"] and all(len(p) == 2 for p in node["reg_stores"])  # store PREFIXES only, no ordinal
    assert {"segment", "home_store", "gender", "created", "household_id", "merged", "rfm"} <= set(node)
    # SEPARABLE-PII: NOT one identifier in the structural file
    blob = out.read_text()
    for pii in ("JOHN", "JANE", "MIKE", "SMITH", "BROWN", "5551234567", "5559998888", "AH0000000001", "AC0000000009"):
        assert pii not in blob


def test_export_customers_identity_crosswalk_is_opt_in(tmp_path, monkeypatch):
    _stub(monkeypatch)
    struct = tmp_path / "customers.json"
    key = tmp_path / "identity.json"
    # default: no crosswalk written
    led.export_customer(str(struct), today="2026-08-15", identity_path=str(key))
    assert not key.exists()
    # opt-in: the node_id -> PII crosswalk lands in the SEPARATE file, and only there
    led.export_customer(str(struct), today="2026-08-15", emit_identity=True, identity_path=str(key))
    crosswalk = json.loads(key.read_text())
    assert crosswalk and all({"node_id", "name", "mobile", "codes"} == set(r) for r in crosswalk)
    assert any(r["mobile"] == "5551234567" for r in crosswalk)  # PII lives here, deliberately joined
