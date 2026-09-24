# Changelog

Version history for `measure_ws.py`, the single-file, stdlib-only measurement
tool in this package. The tool's version is also exposed as `SCRIPT_VERSION` in
the source; this file is the human-readable record. Note: `pyproject.toml`
carries the PEP 440 form of the same version (`v1.4` ↔ `1.4.0`) — bump both
plus `SCRIPT_VERSION` together on each release.

Versions before v1.2 predate this changelog and are not reconstructed here.

## v1.4 — 2026-09-23

Behaviour changes to `measure_ws.py` (sha256 after release:
`b50f66b1c9b2496a90ca9134a0f3bff81c0a157332ac3ba3f4c7ab4c6bdede48`).

### New CLI flags
- **`--probe`** — expose the handshake-only path that `run_session(probe_only=...)`
  already supported internally: connect, negotiate (honouring `--deflate` /
  `--deflate-ladder`), close immediately. No subscription, no collection.
  Fast connectivity + compression-acceptance check for scripts.
- **`--strict`** — exit code **1** when any measured session has `error`,
  `collection_complete=false`, `inflate_failures > 0` or
  `rsv1_without_deflate > 0`; exit 0 otherwise. Previously a session that
  errored still produced exit code 0, which made automation treat a broken
  run as clean.
- **`--version`** — print `v1.4` and exit.

### Fixes
- **RSV1-without-negotiation counted, not silently mis-recorded.** A server
  frame with RSV1=1 but no negotiated `permessage-deflate` is an RFC 6455
  §5.2 violation; its payload's *semantics are undefined* — typically a raw
  DEFLATE stream, not business plaintext. Previously the reader passed it
  through as-is, silently corrupting the payload size distribution with no
  flag. RFC 6455 §5.2 requires *failing the WebSocket connection* on such a
  frame; this tool deliberately continues in order to keep measuring, and
  instead counts it in the new `rsv1_without_deflate` field (surfaced in the
  JSON result and the console summary like `inflate_failures`).
- **Symbols-file errors are clean exits.** A missing or malformed
  `--symbols-file` previously raised a raw `OSError` / `JSONDecodeError`
  traceback; now `SystemExit` with an actionable one-line message.
- **Dead code removed:** the no-op `if "pair" in j and key == "?"` branch in
  the business-message classifier, the vestigial `pass` block in
  `run_session`, the unused `probe` local and `cfg` local, and an unused
  `import zlib as _z` inside `--selftest`.
- **Doc truth:** README/requirements claimed Python 3.7+; the code uses
  `statistics.fmean` (3.8+) — corrected to 3.8+ in README, requirements and
  the new `pyproject.toml` (`requires-python = ">=3.8"`).

### Packaging & tests (new)
- **`pyproject.toml`** — zero runtime dependencies (the tool's design
  contract is a single stdlib-only file, so packaging adds none), console
  script `ws-wire-audit = measure_ws:main`, pytest + ruff (`F`, `E9`)
  configuration. `pip install .` then `ws-wire-audit --version`.
- **`tests/test_measure_ws.py`** — **79 offline pytest cases** (zero
  network): the built-in 35-assertion `--selftest` logic ported to pytest
  plus new cases for the frame reader (control frames, pong echo, extended
  lengths, masked-frame tolerance, deflate window bits incl. the
  RFC-7692-8-bit case, per-message no-context-takeover, inflate failure
  fallback, RSV1-without-negotiation), session accounting (heartbeat/ack
  segregation, error-path data retention, ladder offer decisions incl.
  accepted-offer reuse, probe-only mode, active Bybit keepalive, empty-session
  distribution), symbols resolution (plain/JSON/int forms, per-venue dicts,
  clean errors), and the CLI (strict exit codes, probe forwarding, version).
- **`.gitignore`** extended for packaging/test artifacts.
- Regression checks: `--selftest` 35/35 PASS; `pytest` 79 passed; `ruff
  check` clean on source and tests.

## English translation of the audit report — 2026-09-23 (docs only, no code change)
- **`contract-audit.en.md` added:** a faithful English translation of
  `contract-audit.md`. The Chinese original is kept unchanged alongside it and
  remains the reference document. Finding IDs, numbers, URLs, field names and
  API names are preserved verbatim; nothing was added or omitted.
- **`measure_ws.py` is unchanged:** its sha256 is the same as recorded below, so
  the tool's recorded identity is unaffected by this documentation addition.

## L-21 re-observation — 2026-09-23 (docs only, no code change)

- **L-21 evidence strengthened from n=1 to n≥3.** Two additional independent
  handshakes were performed on 2026-09-23 against the public market-data
  WebSocket endpoint, each explicitly offering `permessage-deflate`:
  both completed with `101 Switching Protocols` and returned no
  `Sec-WebSocket-Extensions` header, matching the three-variant ladder of
  2026-09-22. Each run was a single connection with no subscription, no retry
  and no account/trading call, closed once the response headers were read.
- **Both language versions updated** (`contract-audit.md` and
  `contract-audit.en.md`), including the note that the responsible layer
  (Cloudflare edge vs origin) remains undetermined.
- **No raw wire captures are published:** only the aggregate outcome is
  recorded, per the evidence policy for this package.

## Documentation fixes — 2026-09-23 (post-v1.3, no behaviour change)

- **`README.md` §4 caliber note:** fixed a mis-pointed cross-reference. The
  caveat "cross-venue semantic equivalence was not validated" pointed to
  "§5, item 2" — but §5 item 2 covers fragmentation reassembly, and no §5
  item carries that disclaimer. The pointer now names the actual carrier:
  `SPEC.md` §1.1, "Not implemented", item 2. The caveat's wording is
  otherwise unchanged.
- **`measure_ws.py` module docstring:** replaced a usage example that could
  not run as written. `--symbols 159` exceeds the built-in smoke-test sample
  (30 assets) and the tool exits with a pointer to `--symbols-file`; the
  example now uses the shipped watchlist directly:
  `--symbols-file symbols159.json --duration 600`, matching `README.md` §3.
  Comment-only change — no logic, fields, or assertions touched (line count
  unchanged at 1259; all symbol/line references in `SPEC.md` unaffected).
- Regression after both edits: `python3 -m py_compile` OK;
  `--selftest` 35/35 PASS, exit 0 (offline, zero network).
- `measure_ws.py` sha256 after the docstring edit:
  `f07f4a5abd9f387494590e426e2afcb2bf03d4464b273b64bfab453ef560806e`;
  the fingerprint block in `README.md` §6 was updated to match.

## v1.3 — 2026-09-22

Fixes three hard defects: **D1** (compression-negotiation detection), **D2**
(multi-symbol scale), **D3** (the measurement session itself did not send a
`permessage-deflate` offer).

### D3 — compression negotiation did not take effect in the measurement session

- **Defect:** on `--deflate-ladder`, if all three offer-variant **probe
  handshakes** were refused, the measurement session's offer was set to `None`;
  the run then reported `deflate_offered=false` + `deflate_status=not_offered`.
  Downstream reading could not distinguish that from *"the user never enabled
  compression"*: within the same result file the probe section listed all three
  variants as `server_refused` while the measurement section claimed
  `not_offered`.
- **Fix:** whenever the user asks for compression (`offers` non-empty), the
  measurement session **always** carries an offer. In ladder mode, if every
  variant is refused, it falls back to `offers[0]` (the raw variant is recorded
  in `deflate_offer_header`) so the measurement session self-reports
  `server_refused`.
- **New fields:** `deflate_measurement_offer_source` (`none` | `single-offer` |
  `ladder-accepted` | `ladder-fallback-first-offer`), `deflate_probe_statuses`,
  `deflate_probe_all_refused`.
- **Clarification:** the single-offer path (`--deflate`) **already** offered
  within the measurement session as of v1.2 (`deflate_offered=true`, from a v1.1
  run); only the ladder fallback degraded to `not_offered`. Readings with
  `--deflate` and `offered=False` therefore came from ladder runs, not from
  single-offer runs.
- New offline self-test **T7** (zero network) covering this path.

## v1.2 — 2026-09-22

Revised after the compression-negotiation output was found to be unreadable in
earlier readings (three venues, `--deflate`, all reporting `deflate=None`).

### D1 — compression-negotiation detection was hard-broken (critical)

- **Defect:** v1.1 used `inflate = bool(res['negotiated_permessage_deflate'])` —
  the presence of **any** `Sec-WebSocket-Extensions` value was treated as
  permessage-deflate accepted, and decompression was enabled. It was confirmed
  offline that when the server returns
  `Sec-WebSocket-Extensions: x-webkit-deflate-frame`, the v1.1 inflate switch
  became `True` (forcing zlib on uncompressed frames → `zlib.error` → silent
  fallback to ciphertext sizes). Also, *"we did not offer"* and *"the server
  refused"* were **both** `None` in v1.1 output and could not be told apart —
  which is why readings of the form `deflate=None` were unreadable.
- **Fix:**
  - new `parse_extension_header()` / `find_permessage_deflate()`: splits the
    RFC 6455 §9.1 extension-list (multiple same-name headers, comma separation,
    quoted parameters, case-insensitive) and matches the `permessage-deflate`
    **token exactly** (substring matches do not count);
  - output `deflate_offered` / `deflate_accepted` / `deflate_status`
    (`not_offered` | `server_refused` | `accepted` | `unsolicited` |
    `not_offered_server_sent_other_extension`)
    + `deflate_offer_header` (what we sent, verbatim) + `deflate_response_header`
    (what the server returned, verbatim) + `handshake_headers` (all response
    headers, for the record); the v1.1 field `negotiated_permessage_deflate` is kept;
  - new `--deflate-offer` (`bare` | `params` | `full` or a raw string) and
    `--deflate-ladder`: a probe handshake per offer variant (no subscribe, no
    collection, closed immediately), with the first accepted variant used for
    measurement; if all are refused, the baseline is measured **without** an
    offer — separating *"the server refused"* from *"we wrote the offer wrong"*
    (the `deflate_probe` array records each attempt).
- **Correction to a previously stated fact:** v1.1 **did** send
  `Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits`
  (verified by capturing the raw request with a forged socket). So an output of
  `deflate=None` did not mean *"no offer was sent"*; it meant *"a single field
  could not distinguish the cases"* + *"only one offer variant existed"*. Whether
  the server refuses or accepts must be determined by re-measuring with
  `--deflate-ladder`.

### D1b — compression parameters and context takeover

- v1.1 ignored `server_no_context_takeover` / `server_max_window_bits` and used
  one persistent inflater for all messages; when the server declared
  `server_no_context_takeover`, decompression from the second message on could
  fail and be **silently swallowed** (falling back to ciphertext sizes).
- **Fix:** parse the negotiated parameters; build a fresh inflater per message
  when `no_context_takeover` is set; build a window of size N when
  `server_max_window_bits=N`; count decompression failures in `inflate_failures`
  (no longer silent).

### D2 — multi-symbol scale

- New `--symbols` (comma-separated base assets, or an integer N taking the
  built-in sample list), `--symbols-file` (JSON or plain text), `--raw-symbols`
  (venue-native spelling), `--quote`. **No connection splitting**: messages are
  sent sequentially on one connection, chunked by each venue's published batch
  capability — lbank 1 per message (single pair), binance 1024 per message
  (`SUBSCRIBE` batch), bybit 10 per message (conservative cap). The provenance of
  each figure is recorded in `VENUES[*]['subscribe_notes']` and must be
  re-checked before a run.
- New output: `symbols_requested` / `symbols_count` / `symbol_msg_counts` /
  `symbols_seen` / `subscribe_plan` / `subscribe_messages_sent` /
  `subscribe_errors` (a receipt with `success=false` directly exposes
  non-existent pairs).

### Also in v1.2

- `--duration` is the primary parameter (`--seconds` kept as an alias),
  supporting 600 s long sessions (a hint is printed above 300 s);
- new `wire_bytes_total` (business + application-level heartbeats + subscription
  receipts + control frames, all including frame headers) and `control_wire_bytes`;
- subscription receipts are no longer counted as business metrics
  (`ack_frames` / `ack_wire_bytes`); new `compressed_frames`;
- new `--selftest`: offline self-test (zero network, forged handshake/frame byte
  streams) covering D1 / D1b / D2 and v1.1 regressions.

> **Scope of this revision:** no network session was run (zero network requests);
> every assertion was driven by locally forged byte streams.
>
> **Self-test boundary:** it proves parsing / counting / protocol-construction
> logic only. It does **not** prove any real server behaviour (whether
> compression is accepted, whether a long connection is held, whether the
> symbols are subscribable) — those can only come from real, approved
> measurement sessions run by the operator. Making is not verifying.
