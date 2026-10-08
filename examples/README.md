# ws-wire-audit

Desensitised example outputs. **Aggregated statistics only** — no raw tick
data, no raw per-symbol message dumps, no raw response bodies.

| File | What it is | Source session |
|---|---|---|
| `01-lbank-vs-binance-159pairs-600s.json` | Same-caliber comparison: same script version, 159 symbols, 600 s, single connection, no reconnect, heartbeats/acks excluded from business metrics | `159-pair_*_600s` sessions, 2026-09-22 |
| `02-permessage-deflate-negotiation.md` | The compression negotiation probe, both venues, as prose + numbers | `159-pair_*_180s_deflate` sessions, 2026-09-22 |
| `03-lbank-deflate-ladder-probe.json` | LBank's response to a ladder of three `permessage-deflate` offer variants | `159-pair_lbank_180s_deflate`, 2026-09-22 |
| `04-bybit-103pairs-600s-20260929.json` | Same-caliber 600 s session, Bybit spot — 103 pairs (intersection with the 159-asset list) | `bybit` 600 s, 2026-09-29 |
| `05-okx-110pairs-600s-20260929.json` | Same-caliber 600 s session, OKX spot `trades-all` — 110 pairs | `okx` 600 s, 2026-09-29 |
| `06-kraken-20pairs-600s-20260929.json` | Same-caliber 600 s session, Kraken v2 `trade` — 20 pairs (Kraken quotes most alts in USD) | `kraken` 600 s, 2026-09-29 |
| `07-bybit-deflate-ladder-20260929.json` | `permessage-deflate` ladder probe, Bybit (60 s, 3 pairs) | `bybit` probe, 2026-09-29 |
| `08-okx-deflate-ladder-20260929.json` | `permessage-deflate` ladder probe, OKX (60 s, 3 pairs) | `okx` probe, 2026-09-29 |
| `09-kraken-deflate-ladder-20260929.json` | `permessage-deflate` ladder probe, Kraken (60 s, 3 pairs) | `kraken` probe, 2026-09-29 |
| `10-five-venue-600s-20260929.json` | Curated five-venue same-caliber comparison (adds Bybit/OKX/Kraken to the 2026-09-22 LBank/Binance rows) + derived ratios | 2026-09-22 + 2026-09-29 |
| `11-bybit-103pairs-600s-20260930-r2.json` | Same-caliber 600 s session, Bybit spot — 103 pairs, repeat #2 (n=3 aggregate with `04`+`13`) | `bybit` 600 s, 2026-09-30 |
| `12-kraken-20pairs-600s-20260930-r2.json` | Same-caliber 600 s session, Kraken v2 `trade` — 20 pairs, repeat #2 (n=3 aggregate with `06`+`14`) | `kraken` 600 s, 2026-09-30 |
| `13-bybit-103pairs-600s-20260930-r3.json` | Same-caliber 600 s session, Bybit spot — 103 pairs, repeat #3 | `bybit` 600 s, 2026-09-30 |
| `14-kraken-20pairs-600s-20260930-r3.json` | Same-caliber 600 s session, Kraken v2 `trade` — 20 pairs, repeat #3 | `kraken` 600 s, 2026-09-30 |
| `15-interleaved-bybit-okx-20260930.json` | **Interleaved same-window A/B**: Bybit vs OKX alternating (A 60 s → B 60 s × 6 rounds), per-session start/end timestamps, per-round paired diffs + mechanical verdict | `bybit`/`okx` interleaved, 2026-09-30 19:04–19:17 |
| `16-lbank-159pairs-600s-20261007-r2.json` | Same-caliber 600 s session, LBank spot — 159 pairs, repeat #2 (n=3 aggregate with `01`+`18`) | `lbank` 600 s, 2026-10-07 |
| `17-binance-159pairs-600s-20261007-r2.json` | Same-caliber 600 s session, Binance spot — 159 pairs, repeat #2 (n=3 aggregate with `01`+`19`) | `binance` 600 s, 2026-10-07 |
| `18-lbank-159pairs-600s-20261008-r3.json` | Same-caliber 600 s session, LBank spot — 159 pairs, repeat #3 | `lbank` 600 s, 2026-10-08 |
| `19-binance-159pairs-600s-20261008-r3.json` | Same-caliber 600 s session, Binance spot — 159 pairs, repeat #3 | `binance` 600 s, 2026-10-08 |
>
> **Note (2026-10-08, LBank/Binance thickening):** entries `16`–`19` raise LBank and Binance to
> **n=3** same-caliber 600 s sessions each (with `01`). Cross-session `wire B/s` ranges: LBank
> 15,947.1–19,525.1 (+22.4%); Binance 18,261.3–51,255.0 (+180.7%). Binance's own range
> **overlaps** LBank's, so the n=1 ranking "Binance > LBank by `wire B/s`" is **not decidable**;
> the message-rate direction survives (Binance `msg/s` min 134.289 > LBank max 101.272, ~1.33x).
> Watchlist: `symbols159.txt`. No tool change (still v1.4).
>
> **Note (2026-09-29):** entries `04`–`10` are the *raw* session outputs of the
> extension run (they carry `symbols_requested`, handshake header list, per-symbol
> counts, proxy string). They are stored for internal reproducibility of the
> extension; the desensitisation rule above still governs anything that leaves
> this project.
>
> **Note (2026-09-30, interleaved A/B):** entry `15` is the **raw** output of the interleaved
> same-window A/B run (`RUN-20260930-interleave.sh` → `interleave_ab.py`, both new). It embeds the
> 12 per-session summaries (full tool output) plus a `rounds`/`paired`/`verdict` block. Verdict:
> the small-gap **byte-rate** ordering (Bybit vs OKX `wire B/s`) is **not decidable** (paired-diff
> sign flips once, monotonic drift within the 12-min window), while the **message-rate direction**
> and **per-message size** are decidable. No tool change (still v1.4).
> **Note (2026-09-30, thickening):** the
> thickening run (`RUN-20260930-thicken.sh`), raising Bybit and Kraken to n=3
> same-caliber 600 s sessions. Cross-session ranges: Bybit `wire B/s`
> 5,619.8–10,159.5 (+80.8%); Kraken 39.2–84.8 (+116.3%, but business frames
> 96–235 stay below the venue heartbeat 622–623 in every session, so Kraken's
> USDT face is **not** a suitable throughput sample). No tool change was made
> (still v1.4).
| `report-lbank-vs-binance.md` / `.html` | Human-readable report generated from `01-…json` by `measure_ws.py --report` (Markdown + self-contained HTML); every figure carries its source-JSON field | `01-…`, 2026-09-22 |
| `report-lbank-deflate-ladder.md` / `.html` | Human-readable report generated from `03-…json` (probe shape) | `03-…`, 2026-09-22 |

The two report pairs are **regenerable offline** from the JSONs next to them
(`--from-json`, no network) and are kept as the rendering examples for the
report mode. The `.html` files are self-contained: inline CSS, no external
scripts, fonts or CDN — the only outbound link is the repository URL.

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
