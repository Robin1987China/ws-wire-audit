"""Offline tests for spec/validate.py (ws-wire-audit measurement declarations).

Run from the repository root:

    python3 -m pytest tests/test_spec_validate.py -q

The module under test is standard-library only; the tests themselves need no
network and no fixtures beyond the repository's own ``examples/``.
"""

import copy
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_DIR = os.path.join(REPO_ROOT, "spec")
VALIDATE = os.path.join(SPEC_DIR, "validate.py")
sys.path.insert(0, SPEC_DIR)

import validate  # noqa: E402  (path set above)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def base():
    """A complete, invariant-clean declaration (modelled on examples/01, lbank)."""
    return {
        "declaration_version": "1.0",
        "status": "proposed",
        "observation": {
            "venue": "lbank",
            "symbols_requested": 159,
            "symbols_succeeded": 159,
            "start": "2026-09-22",
            "end": "2026-09-22",
            "duration_s": 600.0,
            "exit_code": 0,
            "tool": "measure_ws.py",
            "tool_version": "v1.3",
        },
        "business_message": {
            "definition": "one inbound data frame, excluding control frames, heartbeats and acks",
            "direction": "inbound",
            "excludes_control_frames": True,
            "excludes_heartbeats": True,
            "excludes_acks": True,
            "reassembles_fragments": False,
        },
        "bytes": {
            "wire_includes_frame_header": True,
            "payload_is_post_inflate": True,
            "direction": "server_to_client",
            "includes_tls_tcp_ip": False,
            "client_uplink_measured": False,
        },
        "compression": {
            "state": "not_offered",
            "offered_header": None,
            "response_header": None,
            "probe": [],
            "probe_method": "none",
            "measurement_offer_source": "none",
        },
        "metrics": {
            "business_messages": 54309,
            "msg_per_s": 90.514,
            "wire_bytes": 10463286,
            "wire_bytes_per_s": 17438.7,
            "payload_bytes": 10246050,
            "payload_bytes_per_s": 17076.6,
            "wire_bytes_total": 10463706,
            "size_bytes": {
                "min": 178, "p50": 188, "p90": 193, "p99": 202, "max": 209, "mean": 188.7,
            },
            "acks": 0,
            "control_frames": 0,
            "heartbeat_frames": 10,
        },
        "checksum": {"capture_sha256": "a" * 64, "algorithm": "sha256"},
        "reproduce": ["python3 measure_ws.py --venue lbank --duration 600"],
    }


def schema():
    return validate.load_schema(os.path.join(SPEC_DIR, "declaration.schema.json"))


def errors_of(decl):
    schema_errors, invariant_errors = validate.validate_declaration(decl, schema())
    return schema_errors + invariant_errors


def run_cli(*args):
    return subprocess.run(
        [sys.executable, VALIDATE, *args],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


# --------------------------------------------------------------------------- #
# positive cases
# --------------------------------------------------------------------------- #
def test_01_valid_declaration_passes():
    assert errors_of(base()) == []


def test_02_valid_unsolicited_state_passes():
    d = base()
    d["compression"] = {
        "state": "unsolicited",
        "offered_header": None,
        "response_header": "permessage-deflate",
        "probe": [],
        "probe_method": "none",
        "measurement_offer_source": "none",
    }
    assert errors_of(d) == []


def test_03_valid_accepted_state_passes():
    d = base()
    d["compression"] = {
        "state": "accepted",
        "offered_header": "permessage-deflate; client_max_window_bits",
        "response_header": "permessage-deflate",
        "probe": [{"offer": "permessage-deflate", "status": "accepted"}],
        "probe_method": "ladder",
        "measurement_offer_source": "ladder-accepted",
    }
    # compression active: payload must be >= wire (SPEC 1.2), so flip the sizes.
    d["metrics"]["payload_bytes"] = 12000000
    d["metrics"]["payload_bytes_per_s"] = 20000.0
    assert errors_of(d) == []


# --------------------------------------------------------------------------- #
# negative cases -- compression declaration
# --------------------------------------------------------------------------- #
def test_04_server_refused_mislabeled_as_not_offered_is_rejected():
    d = base()
    d["compression"]["state"] = "not_offered"
    d["compression"]["offered_header"] = "permessage-deflate"
    assert errors_of(d) != []


def test_05_accepted_without_offer_is_rejected():
    d = base()
    d["compression"]["state"] = "accepted"
    # no offer, no listing -> the pair actually means not_offered
    assert errors_of(d) != []


def test_06_accepted_but_response_lacks_token_is_rejected():
    d = base()
    d["compression"]["state"] = "accepted"
    d["compression"]["offered_header"] = "permessage-deflate"
    d["compression"]["response_header"] = "x-some-other-extension"
    assert errors_of(d) != []


def test_07_invalid_compression_state_enum_is_rejected():
    d = base()
    d["compression"]["state"] = "compressed"
    assert errors_of(d) != []


def test_08_ladder_without_probe_records_is_rejected():
    d = base()
    d["compression"]["probe_method"] = "ladder"
    d["compression"]["probe"] = []
    assert errors_of(d) != []


# --------------------------------------------------------------------------- #
# negative cases -- metrics invariants
# --------------------------------------------------------------------------- #
def test_09_quantiles_out_of_order_is_rejected():
    d = base()
    d["metrics"]["size_bytes"]["p90"] = 250  # p90 > p99
    assert errors_of(d) != []


def test_10_quantile_min_greater_than_p50_is_rejected():
    d = base()
    d["metrics"]["size_bytes"]["min"] = 1000  # min > p50
    assert errors_of(d) != []


def test_11_negative_count_is_rejected():
    d = base()
    d["metrics"]["business_messages"] = -1
    assert errors_of(d) != []


def test_12_symbols_succeeded_over_requested_is_rejected():
    d = base()
    d["observation"]["symbols_succeeded"] = 200
    assert errors_of(d) != []


def test_13_wire_total_below_wire_is_rejected():
    d = base()
    d["metrics"]["wire_bytes_total"] = 1
    assert errors_of(d) != []


def test_14_payload_below_wire_when_accepted_is_rejected():
    d = base()
    d["compression"] = {
        "state": "accepted",
        "offered_header": "permessage-deflate",
        "response_header": "permessage-deflate",
        "probe": [{"offer": "permessage-deflate", "status": "accepted"}],
        "probe_method": "ladder",
        "measurement_offer_source": "ladder-accepted",
    }
    # payload_bytes (10246050) < wire_bytes (10463286) with compression active
    assert errors_of(d) != []


def test_15_rate_inconsistent_with_duration_is_rejected():
    d = base()
    d["metrics"]["msg_per_s"] = 999.0
    assert errors_of(d) != []


def test_16_mean_outside_min_max_is_rejected():
    d = base()
    d["metrics"]["size_bytes"]["mean"] = 500  # > max
    assert errors_of(d) != []


# --------------------------------------------------------------------------- #
# negative cases -- schema structure
# --------------------------------------------------------------------------- #
def test_17_missing_checksum_is_reported_as_missing():
    d = base()
    del d["checksum"]
    assert "$.checksum" in validate.missing_required(d, schema())
    assert errors_of(d) != []


def test_18_wrong_type_rate_is_rejected():
    d = base()
    d["metrics"]["msg_per_s"] = "90.5"
    assert errors_of(d) != []


def test_19_bad_sha256_pattern_is_rejected():
    d = base()
    d["checksum"]["capture_sha256"] = "not-a-hash"
    assert errors_of(d) != []


def test_20_status_must_be_proposed_not_standard():
    d = base()
    d["status"] = "standard"
    assert errors_of(d) != []


def test_21_extra_property_is_rejected():
    d = base()
    d["notes"] = "should not be here"
    assert errors_of(d) != []


# --------------------------------------------------------------------------- #
# session extraction + CLI
# --------------------------------------------------------------------------- #
def test_22_extract_from_real_session_reports_checksum_gap():
    path = os.path.join(REPO_ROOT, "examples", "01-lbank-vs-binance-159pairs-600s.json")
    obj = json.load(open(path, encoding="utf-8"))
    reports = validate.validate_session_obj(obj, schema(), path)
    assert len(reports) == 2
    for rep in reports:
        assert "$.checksum" in rep["missing_required"]
        # compression is structured in this file, so its invariant holds
        assert rep["invariant_errors"] == []


def test_23_cli_help_exits_zero():
    res = run_cli("--help")
    assert res.returncode == 0
    assert "declaration" in res.stdout


def test_24_cli_valid_declaration_exits_zero(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(base()), encoding="utf-8")
    res = run_cli("--declaration", str(p))
    assert res.returncode == 0, res.stdout
    assert "PASS" in res.stdout


def test_25_cli_invalid_declaration_exits_nonzero(tmp_path):
    d = base()
    d["metrics"]["size_bytes"]["p90"] = 999
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    res = run_cli("--declaration", str(p))
    assert res.returncode == 1
    assert "FAIL" in res.stdout


def test_26_cli_session_on_real_example_exits_nonzero_with_gaps():
    path = os.path.join(REPO_ROOT, "examples", "01-lbank-vs-binance-159pairs-600s.json")
    res = run_cli("--session", path)
    assert res.returncode == 1  # known gaps: checksum + declared calibers
    assert "missing_required" in res.stdout


def test_27_schema_itself_decodes_and_lists_required():
    s = schema()
    assert s["title"].startswith("ws-wire-audit")
    for key in ("observation", "business_message", "bytes", "compression",
                "metrics", "checksum", "reproduce"):
        assert key in s["required"]


def test_28_unsolicited_with_offer_is_rejected():
    d = base()
    d["compression"] = {
        "state": "unsolicited",
        "offered_header": "permessage-deflate",
        "response_header": "permessage-deflate",
        "probe": [],
        "probe_method": "single-offer",
        "measurement_offer_source": "single-offer",
    }
    # offer + listing actually means "accepted"
    assert errors_of(d) != []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
