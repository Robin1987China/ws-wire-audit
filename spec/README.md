# Machine-readable declarations for ws-wire-audit

**Status: a *proposed* rule of practice — not a standard, not adopted.**

`SPEC.md` states the four declarations a WebSocket feed comparison must carry (business-message
definition; payload vs. wire bytes; compression-negotiation state; egress and window). In
`SPEC.md` those are *prose*, so two third parties who follow them by hand drift apart on the
details. This directory makes the same four declarations **machine-readable and checkable**.

It adds nothing to the instrument: `measure_ws.py` still measures, and a session is still a
session. What is new is a spelling of the declaration and a checker for it. Follow `SPEC.md`;
use these files only as a way to write the declaration down without ambiguity.

---

## 30-second quick start

```sh
# 1. Check a declaration document (schema + invariants). Exit 0 = PASS.
python3 spec/validate.py --declaration spec/examples/declaration.template.json

# 2. Check a real session capture: derive a declaration and list the gaps.
python3 spec/validate.py --session examples/01-lbank-vs-binance-159pairs-600s.json

# 3. Run the offline test suite (positive and negative cases).
python3 -m pytest tests/test_spec_validate.py -q
```

`--json` emits the same result as machine-readable JSON. `--schema FILE` overrides the schema.

Exit codes: `0` all checked documents conform; `1` at least one does not (gaps or violations);
`2` usage / load error. In `--session` mode a *gap* means the capture does not declare the field,
not that the measurement is wrong.

---

## Files

| File | What it is |
|---|---|
| `declaration.schema.json` | JSON Schema (draft 2020-12) for one measurement declaration. |
| `validate.py` | Standard-library-only checker: schema subset + caliber invariants + session extraction. |
| `examples/declaration.template.json` | A fully conforming declaration (worked from `examples/01`), with an **illustrative** checksum. |
| `../tests/test_spec_validate.py` | Offline pytest suite: positive and negative cases. |

`validate.py` imports only the standard library (`argparse`, `json`, `os`, `re`, `sys`), so it runs
on a bare Python 3.8+ checkout with no `pip install`.

---

## What a declaration must contain

The schema requires, at the top level: `declaration_version`, `status`, `observation`,
`business_message`, `bytes`, `compression`, `metrics`, `checksum`, `reproduce`. In short:

- **observation** — venue, requested/succeeded symbol counts, start/end, `duration_s`, `exit_code`,
  tool and version, and an `egress` string (write `"unknown"` rather than omit it, per `SPEC.md` §1.4).
- **business_message** — the definition text, `direction: inbound`, and four explicit booleans:
  whether control frames, heartbeats and acks are excluded, and whether fragments are reassembled.
- **bytes** — whether the wire count includes the frame header, whether payload is post-inflate,
  the direction, and two explicit `false`s: TLS/TCP/IP excluded, client uplink not measured.
- **compression** — the four-state `state` (`not_offered` / `server_refused` / `accepted` /
  `unsolicited`), **both header strings**, the ladder `probe[]`, how the probe was run
  (`probe_method`), and which offer the *measured* session carried (`measurement_offer_source`).
- **metrics** — `business_messages`, `msg_per_s`, `wire_bytes`/`_per_s`, `payload_bytes`/`_per_s`,
  the `size_bytes` distribution (`min`/`p50`/`p90`/`p99`/`max`/`mean`), and `acks`,
  `control_frames`, `heartbeat_frames`.
- **checksum** — `capture_sha256` (64 lowercase hex) and `algorithm: sha256`, so a reader can tie
  the numbers back to the exact capture.
- **reproduce** — the command(s) that produced the capture.

## Invariants (checked by `validate.py`, beyond the schema)

| | Invariant |
|---|---|
| I1 | `compression.state` agrees with the header pair: no offer + not listed = `not_offered`; offer + not listed = `server_refused`; offer + listed = `accepted`; no offer + listed = `unsolicited`. **This is what stops `server_refused` being written as `not_offered`.** |
| I2 | `probe_method`, `probe[]` and `measurement_offer_source` are mutually consistent. |
| I3 | `size_bytes` quantiles are monotonic (`min ≤ p50 ≤ p90 ≤ p99 ≤ max`) and `mean` lies in `[min, max]`. |
| I4 | Metric counts are non-negative. |
| I5 | `symbols_succeeded ≤ symbols_requested`. |
| I6 | `wire_bytes_total ≥ wire_bytes`. |
| I7 | When `state == accepted`, `payload_bytes ≥ wire_bytes` (`SPEC.md` §1.2). |
| I8 | Each `*_per_s` rate equals its total ÷ `duration_s`, within rounding. |

## Schema support note

`validate.py` implements a **documented subset** of JSON Schema draft 2020-12: `type`, `required`,
`properties`, `additionalProperties`, `items`, `minItems`/`maxItems`, `minimum`/`maximum`/
`exclusiveMinimum`/`exclusiveMaximum`, `minLength`/`maxLength`, `pattern`, `enum`, `const`, `allOf`.
The schema file is ordinary JSON Schema, so it also validates unchanged with any conforming
validator (e.g. the `jsonschema` package) if you prefer one.

## Honest boundaries

1. **Not a standard.** Like `SPEC.md`, this is a *proposed* spelling; `status` is pinned to
   `"proposed"` so nothing here reads as adopted. It has no third-party adoption.
2. **It checks declarations, not truth.** The validator confirms a declaration is well-formed and
   self-consistent; it cannot confirm the numbers were measured honestly. The `checksum` only ties
   the declaration to a capture *you* hold.
3. **The existing `examples/` are summaries, not declarations.** Running `--session` over them
   reports gaps by design (see the accompanying report): they carry compression state and metrics,
   but not the declared calibers, the capture checksum, or a reproduce command. That gap is exactly
   what this directory exists to surface.
4. **Where a thing is not implemented, the schema says so by requiring an explicit value** — e.g.
   `client_uplink_measured: false`, `includes_tls_tcp_ip: false` — rather than leaving it silent.

## Cite

Cite the *rule*, not a number; see `SPEC.md` §3. When you attach a machine-readable declaration,
cite this spelling as "the `ws-wire-audit` declaration schema (proposed)".
