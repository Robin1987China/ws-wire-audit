#!/usr/bin/env python3
"""validate.py -- machine-readable validation for ws-wire-audit measurement declarations.

Reads a *session* JSON (a measurement capture in one of this repository's known
shapes) and/or a *declaration* JSON (the four-caliber declaration defined by
SPEC.md), then checks it against ``declaration.schema.json`` and the caliber
invariants.

Standard library only. The JSON-Schema support here is a small, documented
subset of draft 2020-12 (keywords listed in ``SUPPORTED_KEYWORDS``); the schema
file itself is ordinary JSON Schema and validates unchanged with any conforming
validator. See spec/README.md.

Status: this is a *proposal* (SPEC.md), not a standard.

Invariants enforced (in addition to the schema):

  I1  compression.state agrees with (offered_header, response_header):
        no offer, no listing        -> not_offered
        offer,    no listing        -> server_refused
        offer,    listing           -> accepted
        no offer, listing           -> unsolicited
      This is what stops ``server_refused`` being reported as ``not_offered``.
  I2  probe_method / probe[] / measurement_offer_source are mutually consistent.
  I3  size_bytes quantiles are monotonic (min <= p50 <= p90 <= p99 <= max) and
      the mean lies inside [min, max].
  I4  metric counts are non-negative.
  I5  symbols_succeeded <= symbols_requested.
  I6  wire_bytes_total >= wire_bytes.
  I7  when compression.state == "accepted", payload_bytes >= wire_bytes
      (SPEC 1.2: under permessage-deflate, payload >= wire).
  I8  the *per-s rate equals its total / duration_s, within rounding.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(HERE, "declaration.schema.json")

SUPPORTED_KEYWORDS = (
    "type", "required", "properties", "additionalProperties", "items",
    "minItems", "maxItems", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minLength", "maxLength", "pattern", "enum", "const",
    "allOf",
)

COMPRESSION_STATES = ("not_offered", "server_refused", "accepted", "unsolicited")
PROBE_METHODS = ("none", "single-offer", "ladder")
OFFER_SOURCES = ("none", "single-offer", "ladder-accepted", "ladder-fallback-first-offer")
DEFLATE_TOKEN = "permessage-deflate"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_json(path):
    """Load a JSON document from *path* (utf-8)."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_schema(path=None):
    return load_json(path or DEFAULT_SCHEMA)


# --------------------------------------------------------------------------- #
# minimal JSON Schema (draft 2020-12 subset) validator
# --------------------------------------------------------------------------- #
def _typename(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_type(value, t):
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return _is_number(value)
    raise ValueError("unsupported schema type: %r" % (t,))


def schema_validate(instance, schema, path="$"):
    """Validate *instance* against *schema*; return a list of error strings.

    Implements only SUPPORTED_KEYWORDS; unknown keywords are ignored (they act
    as annotations, which is valid JSON-Schema behaviour for unknown keywords).
    """
    errors = []

    if "type" in schema:
        types = schema["type"]
        types = types if isinstance(types, list) else [types]
        if not any(_is_type(instance, t) for t in types):
            errors.append(
                "%s: expected type %s, got %s"
                % (path, "/".join(types), _typename(instance))
            )
            return errors  # no point checking the rest

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected const %r, got %r" % (path, schema["const"], instance))

    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: value %r is not one of %r" % (path, instance, schema["enum"]))

    if _is_number(instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: %s < minimum %s" % (path, instance, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: %s > maximum %s" % (path, instance, schema["maximum"]))
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(
                "%s: %s <= exclusiveMinimum %s" % (path, instance, schema["exclusiveMinimum"])
            )
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append(
                "%s: %s >= exclusiveMaximum %s" % (path, instance, schema["exclusiveMaximum"])
            )

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: length %d < minLength %d" % (path, len(instance), schema["minLength"]))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append("%s: length %d > maxLength %d" % (path, len(instance), schema["maxLength"]))
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append("%s: %r does not match pattern %r" % (path, instance, schema["pattern"]))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: length %d < minItems %d" % (path, len(instance), schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: length %d > maxItems %d" % (path, len(instance), schema["maxItems"]))
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(schema_validate(item, schema["items"], "%s[%d]" % (path, i)))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: missing required property %r" % (path, key))
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors.extend(schema_validate(value, props[key], "%s.%s" % (path, key)))
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    errors.append("%s: additional property %r is not allowed" % (path, key))
                elif isinstance(ap, dict):
                    errors.extend(schema_validate(value, ap, "%s.%s" % (path, key)))

    for sub in schema.get("allOf", []):
        errors.extend(schema_validate(instance, sub, path))

    return errors


def _allows_null(subschema):
    if not isinstance(subschema, dict):
        return False
    t = subschema.get("type")
    if t is None:
        return False
    types = t if isinstance(t, list) else [t]
    return "null" in types


def missing_required(instance, schema, path="$"):
    """List dotted paths of required fields not *declared* in *instance*.

    A key present with an explicit ``null`` counts as declared when the schema
    allows null for it (e.g. the nullable header strings); a null for a
    non-nullable field is reported as missing.
    """
    out = []
    if not isinstance(instance, dict):
        return out
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in instance:
            out.append("%s.%s" % (path, key))
        elif instance[key] is None and not _allows_null(props.get(key)):
            out.append("%s.%s" % (path, key))
    for key, sub in props.items():
        if isinstance(instance, dict) and instance.get(key) is not None:
            out.extend(missing_required(instance[key], sub, "%s.%s" % (path, key)))
    return out


# --------------------------------------------------------------------------- #
# caliber invariants
# --------------------------------------------------------------------------- #
def _expected_state(offered_header, response_header):
    offered = offered_header is not None
    listed = isinstance(response_header, str) and DEFLATE_TOKEN in response_header
    if offered and listed:
        return "accepted"
    if offered and not listed:
        return "server_refused"
    if not offered and listed:
        return "unsolicited"
    return "not_offered"


def check_invariants(decl):
    """Return a list of invariant violations for *decl* (a partial is fine)."""
    errs = []
    obs = decl.get("observation") or {}
    comp = decl.get("compression") or {}
    met = decl.get("metrics") or {}

    # I1 -- compression state vs header strings
    state = comp.get("state")
    offered = comp.get("offered_header") if "offered_header" in comp else None
    response = comp.get("response_header") if "response_header" in comp else None
    if state is not None:
        expected = _expected_state(offered, response)
        if state != expected:
            errs.append(
                "I1 compression.state=%r contradicts offered_header=%r / response_header=%r "
                "(expected %r)" % (state, offered, response, expected)
            )

    # I2 -- probe bookkeeping
    probe = comp.get("probe")
    method = comp.get("probe_method")
    source = comp.get("measurement_offer_source")
    if method == "none":
        if probe:
            errs.append("I2 probe_method='none' but probe[] is non-empty")
        if "offered_header" in comp and comp["offered_header"] is not None:
            errs.append("I2 probe_method='none' but offered_header is set")
    if method in ("single-offer", "ladder") and not probe:
        if method == "ladder":
            errs.append("I2 probe_method='ladder' but probe[] is empty")
    if probe and method not in (None, "ladder"):
        errs.append("I2 probe[] is non-empty but probe_method=%r" % (method,))
    if source == "none" and offered is not None:
        errs.append("I2 measurement_offer_source='none' but an offer header is present")

    # I3 -- size_bytes monotonic
    sb = met.get("size_bytes") or {}
    keys = ["min", "p50", "p90", "p99", "max"]
    vals = [(k, sb[k]) for k in keys if _is_number(sb.get(k))]
    for (k1, v1), (k2, v2) in zip(vals, vals[1:]):
        if v1 > v2:
            errs.append("I3 size_bytes not monotonic: %s=%s > %s=%s" % (k1, v1, k2, v2))
    if _is_number(sb.get("mean")) and vals:
        if sb["mean"] < sb["min"] or sb["mean"] > sb["max"]:
            errs.append(
                "I3 size_bytes.mean=%s outside [min=%s, max=%s]"
                % (sb["mean"], sb.get("min"), sb.get("max"))
            )

    # I4 -- counts non-negative
    for key in ("business_messages", "wire_bytes", "payload_bytes", "wire_bytes_total",
                "acks", "control_frames", "heartbeat_frames"):
        v = met.get(key)
        if _is_number(v) and v < 0:
            errs.append("I4 metrics.%s is negative (%s)" % (key, v))

    # I5 -- symbols succeeded <= requested
    req = obs.get("symbols_requested")
    got = obs.get("symbols_succeeded")
    if isinstance(req, int) and isinstance(got, int) and got > req:
        errs.append("I5 symbols_succeeded=%d > symbols_requested=%d" % (got, req))

    # I6 -- wire_bytes_total >= wire_bytes
    wt = met.get("wire_bytes_total")
    wb = met.get("wire_bytes")
    if _is_number(wt) and _is_number(wb) and wt < wb:
        errs.append("I6 wire_bytes_total=%s < wire_bytes=%s" % (wt, wb))

    # I7 -- payload >= wire when compression is active
    if state == "accepted" and _is_number(met.get("payload_bytes")) and _is_number(wb):
        if met["payload_bytes"] < wb:
            errs.append(
                "I7 state='accepted' but payload_bytes=%s < wire_bytes=%s"
                % (met["payload_bytes"], wb)
            )

    # I8 -- per-second rates agree with total / duration_s
    dur = obs.get("duration_s")
    if _is_number(dur) and dur > 0:
        for total_key, rate_key in (
            ("business_messages", "msg_per_s"),
            ("wire_bytes", "wire_bytes_per_s"),
            ("payload_bytes", "payload_bytes_per_s"),
        ):
            tot, rate = met.get(total_key), met.get(rate_key)
            if _is_number(tot) and _is_number(rate):
                expected = tot / dur
                if abs(rate - expected) > max(1.0, 0.01 * abs(expected)):
                    errs.append(
                        "I8 %s=%s inconsistent with %s/duration_s=%.4f"
                        % (rate_key, rate, total_key, expected)
                    )
    return errs


# --------------------------------------------------------------------------- #
# extraction: known session shapes -> a (partial) declaration
# --------------------------------------------------------------------------- #
def _prune(d):
    """Drop keys whose value is None, so 'missing' means 'not in the file'."""
    return {k: v for k, v in d.items() if v is not None}


def _observation_from(r, top, duration_keys=("elapsed_s", "requested_seconds", "window_s")):
    obs = {
        "venue": r.get("venue"),
        "symbols_requested": r.get("symbols_count")
        if r.get("symbols_count") is not None
        else (len(r["symbols_requested"]) if isinstance(r.get("symbols_requested"), list) else None),
        "symbols_succeeded": r.get("symbols_seen"),
        "start": top.get("observed_on") or top.get("generated_at"),
        "end": top.get("generated_at") or top.get("observed_on"),
        "duration_s": next((r[k] for k in duration_keys if _is_number(r.get(k))), None),
        "exit_code": None,
        "tool": (top.get("produced_by") or "measure_ws.py").split()[0],
        "tool_version": r.get("script_version") or top.get("script_version"),
    }
    complete = r.get("collection_complete")
    if complete is None and isinstance(r.get("integrity"), dict):
        complete = r["integrity"].get("collection_complete")
    if complete is not None:
        obs["exit_code"] = 0 if complete else 1
    return _prune(obs)


def _compression_from(r):
    """Compression block from a *live* result record; presence-aware.

    A key that exists in the file (even with value ``null``) is carried over --
    a live run states ``"deflate_offer_header": null`` for ``not_offered``, and
    that is a declaration, not a gap.
    """
    comp = {}
    if "deflate_status" in r:
        comp["state"] = r["deflate_status"]
    if "deflate_offer_header" in r:
        comp["offered_header"] = r["deflate_offer_header"]
    if "deflate_response_header" in r:
        comp["response_header"] = r["deflate_response_header"]
    probe = []
    for p in (r.get("deflate_probe") or []):
        if isinstance(p, dict) and p.get("offer") is not None:
            probe.append(_prune({"offer": p.get("offer"), "status": p.get("status")}))
    comp["probe"] = probe
    comp["probe_method"] = "ladder" if probe else ("single-offer" if r.get("deflate_offered") else "none")
    source = r.get("deflate_measurement_offer_source")
    if "deflate_measurement_offer_source" in r and source in OFFER_SOURCES:
        comp["measurement_offer_source"] = source
    return comp


def _compression_from_curated(comp_in):
    """Compression block from a curated-summary ``compression`` object.

    ``deflate_offered=False`` is decidable (no offer header was sent), so
    ``offered_header`` is carried as an explicit ``null``. The exact response
    header string cannot be recovered from a boolean, so it is left absent (a
    real gap, reported as such).
    """
    comp = {}
    if "deflate_status" in comp_in:
        comp["state"] = comp_in["deflate_status"]
    if "deflate_offered" in comp_in:
        comp["offered_header"] = None if not comp_in["deflate_offered"] else DEFLATE_TOKEN
        if not comp_in["deflate_offered"]:
            comp["measurement_offer_source"] = "none"
    comp["probe"] = []
    comp["probe_method"] = "none"
    return comp


def _metrics_from(r, accounting=None):
    acc = accounting or {}
    met = {
        "business_messages": r.get("business_messages"),
        "msg_per_s": r.get("msg_per_s"),
        "wire_bytes": r.get("wire_bytes"),
        "wire_bytes_per_s": r.get("wire_bytes_per_s"),
        "payload_bytes": r.get("payload_bytes"),
        "payload_bytes_per_s": r.get("payload_bytes_per_s"),
        "wire_bytes_total": r.get("wire_bytes_total"),
        "size_bytes": r.get("size_bytes"),
        "acks": r.get("subscribe_acks", acc.get("subscribe_acks")),
        "control_frames": r.get("control_frames", acc.get("control_frames")),
        "heartbeat_frames": r.get("venue_heartbeat_frames")
        if r.get("venue_heartbeat_frames") is not None
        else r.get("app_ping_frames", acc.get("app_ping_frames")),
    }
    if isinstance(met.get("size_bytes"), dict):
        met["size_bytes"] = _prune(dict(met["size_bytes"]))
    return _prune(met)


def _base(top=None):
    top = top or {}
    return {
        "declaration_version": "1.0",
        "status": "proposed",
    }


def declaration_from_session(obj, path="<session>"):
    """Yield (label, partial_declaration) tuples from a known session shape.

    Only values *present in the file* are carried over; anything the file does
    not state is left absent, so the validator can report it as a gap. In
    particular, business_message/bytes/checksum are almost never present in a
    session summary (they are declared, not measured).
    """
    if not isinstance(obj, dict):
        raise ValueError("%s: not a JSON object" % path)

    # Shape A: curated summary -- top-level "sessions": [ {..., "compression": {...}} ]
    if isinstance(obj.get("sessions"), list) and obj["sessions"] and isinstance(obj["sessions"][0], dict) \
            and "compression" in obj["sessions"][0]:
        for i, s in enumerate(obj["sessions"]):
            decl = _base(obj)
            decl["observation"] = _observation_from(s, obj)
            decl["compression"] = _compression_from_curated(s.get("compression") or {})
            decl["metrics"] = _metrics_from(s, s.get("accounting"))
            if isinstance(obj.get("reproduce"), list):
                decl["reproduce"] = [str(x) for x in obj["reproduce"]]
            yield ("%s[%d] %s" % (os.path.basename(path), i, s.get("venue")), decl)
        return

    # Shape B: interleaved experiment -- top-level "sessions": [ {..., "result": {...}} ]
    if isinstance(obj.get("sessions"), list) and obj["sessions"] and isinstance(obj["sessions"][0], dict) \
            and isinstance(obj["sessions"][0].get("result"), dict):
        for i, s in enumerate(obj["sessions"]):
            decl = _base(obj)
            decl["observation"] = _observation_from(s["result"], obj)
            decl["compression"] = _compression_from(s["result"])
            decl["metrics"] = _metrics_from(s["result"])
            if isinstance(obj.get("reproduce"), list):
                decl["reproduce"] = [str(x) for x in obj["reproduce"]]
            yield ("%s[%d] round=%s %s" % (os.path.basename(path), i, s.get("round"), s.get("venue")), decl)
        return

    # Shape C: live runner output -- top-level "results": [ {...flat...} ]
    if isinstance(obj.get("results"), list):
        for i, r in enumerate(obj["results"]):
            decl = _base(obj)
            decl["observation"] = _observation_from(r, obj)
            decl["compression"] = _compression_from(r)
            decl["metrics"] = _metrics_from(r)
            if isinstance(obj.get("reproduce"), list):
                decl["reproduce"] = [str(x) for x in obj["reproduce"]]
            yield ("%s[%d] %s" % (os.path.basename(path), i, r.get("venue")), decl)
        return

    # Shape D: deflate ladder probe -- top-level "measured_session"
    if isinstance(obj.get("measured_session"), dict):
        ms = obj["measured_session"]
        decl = _base(obj)
        offers = obj.get("offers_sent_in_order") or []
        decl["observation"] = _prune(
            {
                "venue": obj.get("venue"),
                "start": obj.get("observed_on"),
                "tool": (obj.get("produced_by") or "measure_ws.py").split()[0],
                "tool_version": None,
            }
        )
        probe = []
        for p in (obj.get("probe_results") or []):
            if isinstance(p, dict) and p.get("offer") is not None:
                probe.append(_prune({"offer": p.get("offer"), "status": p.get("status")}))
        decl["compression"] = _prune(
            {
                "state": ms.get("deflate_status"),
                "offered_header": offers[0] if (ms.get("deflate_offered") and offers) else None,
                "response_header": None,
                "probe": probe,
                "probe_method": "ladder" if probe else "none",
                "measurement_offer_source": ms.get("deflate_offer_source"),
            }
        )
        decl["metrics"] = _prune(
            {
                "wire_bytes": ms.get("wire_bytes"),
                "payload_bytes": ms.get("payload_bytes"),
            }
        )
        if isinstance(obj.get("reproduce"), list):
            decl["reproduce"] = [str(x) for x in obj["reproduce"]]
        yield ("%s (ladder probe: %s)" % (os.path.basename(path), obj.get("venue")), decl)
        return

    raise ValueError(
        "%s: unrecognised session shape (expected top-level 'sessions', 'results' or 'measured_session')"
        % path
    )


# --------------------------------------------------------------------------- #
# top-level validation
# --------------------------------------------------------------------------- #
def validate_declaration(decl, schema):
    """Full schema validation + invariants for a complete declaration."""
    return schema_validate(decl, schema), check_invariants(decl)


def validate_session_obj(obj, schema, path="<session>"):
    """Validate every session found in a session capture. Returns a list of dicts."""
    reports = []
    for label, decl in declaration_from_session(obj, path):
        missing = missing_required(decl, schema)
        errs = check_invariants(decl)
        reports.append({
            "session": label,
            "ok": not missing and not errs,
            "missing_required": missing,
            "invariant_errors": errs,
        })
    return reports


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_session_reports(reports, as_json):
    if as_json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
        return
    for rep in reports:
        print("== %s" % rep["session"])
        print("   status: %s" % ("PASS" if rep["ok"] else "GAP"))
        if rep["missing_required"]:
            print("   missing_required (%d):" % len(rep["missing_required"]))
            for m in rep["missing_required"]:
                print("     - %s" % m)
        if rep["invariant_errors"]:
            print("   invariant_errors (%d):" % len(rep["invariant_errors"]))
            for e in rep["invariant_errors"]:
                print("     - %s" % e)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="validate.py",
        description=(
            "Validate a ws-wire-audit measurement declaration and/or a session capture. "
            "Proposal, not a standard (SPEC.md). Standard library only."
        ),
    )
    parser.add_argument("--declaration", metavar="FILE",
                        help="a declaration JSON to validate against the schema + invariants")
    parser.add_argument("--session", metavar="FILE",
                        help="a session capture JSON; a declaration is derived and checked for gaps")
    parser.add_argument("--schema", metavar="FILE", default=DEFAULT_SCHEMA,
                        help="schema to validate against (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    if not args.declaration and not args.session:
        parser.error("give at least one of --declaration FILE or --session FILE")

    try:
        schema = load_schema(args.schema)
    except (OSError, ValueError) as exc:
        print("error: cannot load schema: %s" % exc, file=sys.stderr)
        return 2

    failed = False

    if args.declaration:
        try:
            decl = load_json(args.declaration)
        except (OSError, ValueError) as exc:
            print("error: cannot load declaration: %s" % exc, file=sys.stderr)
            return 2
        schema_errors, invariant_errors = validate_declaration(decl, schema)
        ok = not schema_errors and not invariant_errors
        failed = failed or not ok
        if args.json:
            print(json.dumps({
                "declaration": args.declaration,
                "ok": ok,
                "schema_errors": schema_errors,
                "invariant_errors": invariant_errors,
            }, indent=2, ensure_ascii=False))
        else:
            print("== declaration: %s" % args.declaration)
            print("   status: %s" % ("PASS" if ok else "FAIL"))
            for e in schema_errors:
                print("   schema:    %s" % e)
            for e in invariant_errors:
                print("   invariant: %s" % e)

    if args.session:
        try:
            obj = load_json(args.session)
        except (OSError, ValueError) as exc:
            print("error: cannot load session: %s" % exc, file=sys.stderr)
            return 2
        try:
            reports = validate_session_obj(obj, schema, args.session)
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        if not reports:
            print("error: no sessions found in %s" % args.session, file=sys.stderr)
            return 2
        _print_session_reports(reports, args.json)
        if any(not r["ok"] for r in reports):
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
