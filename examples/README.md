# ws-wire-audit

Desensitised example outputs. **Aggregated statistics only** — no raw tick
data, no raw per-symbol message dumps, no raw response bodies.

| File | What it is | Source session |
|---|---|---|
| `01-lbank-vs-binance-159pairs-600s.json` | Same-caliber comparison: same script version, 159 symbols, 600 s, single connection, no reconnect, heartbeats/acks excluded from business metrics | `159-pair_*_600s` sessions, 2026-09-22 |
| `02-permessage-deflate-negotiation.md` | The compression negotiation probe, both venues, as prose + numbers | `159-pair_*_180s_deflate` sessions, 2026-09-22 |
| `03-lbank-deflate-ladder-probe.json` | LBank's response to a ladder of three `permessage-deflate` offer variants | `159-pair_lbank_180s_deflate`, 2026-09-22 |

## What was removed before publishing

Per the project's own blacklist rule, these examples contain **aggregate
session metrics only**:

- ✂️ per-symbol message counts (`symbol_msg_counts`) — venue-composition detail
- ✂️ raw handshake headers and timestamps
- ✂️ local network path details (proxy address, egress)
- ✂️ any raw frame payload / tick data (never stored in these files to begin with)

## Why aggregate-only

Example files in a public repository are for **verifying a claim**, not for
redistributing market data. Every number here is one that a reader can
re-derive by pointing the tool at the same public endpoints for the same
window — which is the only thing an example needs to do.

Each example is labelled with `n_sessions` and `window_s` so no reader can
mistake a single session for a distribution.
