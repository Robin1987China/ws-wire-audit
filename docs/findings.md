# Cross-venue WebSocket market data: what is on the wire, and what these numbers cannot decide

- Date: 2026-10-08 (GMT+8)
- Scope: one measurement tool, one declared caliber, five public crypto-spot trade
  feeds: **LBank, Binance, Bybit, OKX, Kraken**.
- Nature: public write-up. Every claim below carries an evidence code `E##` that
  links to a session file in this repository. A claim with no repository evidence
  is not written here; anything we could not verify is listed under
  [What we cannot conclude](#4-what-we-cannot-conclude).
- Companion artifacts: the machine-readable rule is `SPEC.md`; the numeric
  comparison page is `docs/index.html`.

Tool: `measure_ws.py` (standard library only, no keys). One public WebSocket
connection per session, no reconnect, no concurrency, one egress.

---

## 1. What we measured

A single session records, for one connection:

- **Throughput** - business messages, `msg/s`, `payload B/s`, `wire B/s`.
- **Distribution** - per-message size min / p50 / p90 / p99 / max / mean.
- **Compression** - the negotiation state, the offer and response header text,
  compressed-frame count, inflate failures.
- **Accounting hygiene** - subscribe acks, subscribe errors, RFC 6455 control
  frames, and application heartbeats, each in its own counter and **excluded**
  from the business metrics above.
- **Integrity** - `collection_complete`, `error`, first-message latency,
  `Sec-WebSocket-Accept` validity.

Sessions used in this write-up (600 s window each, one connection, no reconnect):

| Venue   | Sessions (n) | Window start dates (GMT+8)        | Symbols req/seen |
|---------|--------------|-----------------------------------|------------------|
| LBank   | 3            | 2026-09-22, 2026-10-07, 2026-10-08| 159 / 158-159    |
| Binance | 3            | 2026-09-22, 2026-10-07, 2026-10-08| 159 / 157-159    |
| Bybit   | 3            | 2026-09-29, 2026-09-30 x2         | 103 / 94-98      |
| OKX     | 1 (+1 interleaved run) | 2026-09-29, 2026-09-30 | 110 / 102|
| Kraken  | 3            | 2026-09-29, 2026-09-30 x2         | 20 / 12-15       |

The symbol counts are each venue's tradeable **intersection** with one 159-asset
watchlist (`symbols159.txt` / `symbols159.json`), so this is the same ruler, not
the same symbol set. Cross-session spread is why several rows below are ranges
and not single numbers.

---

## 2. Method - the four declarations

Two numbers are comparable only if four quantities are declared. This project's
rule (see `SPEC.md`) is:

1. **What counts as a business message.** One inbound data frame, excluding
   RFC 6455 control frames, application heartbeats and subscribe acks; inbound
   only; fragmented messages are not reassembled. (`E14`)
2. **Payload vs. wire bytes.** `payload` = inbound bytes after decompression;
   `wire` = WebSocket frame bytes as read (header included, compressed bytes if
   the frame arrived compressed). Both exclude TLS/TCP/IP overhead; the
   client-to-server direction is not measured. (`E14`)
3. **Compression-negotiation state.** Four states, never a boolean:
   `not_offered` / `server_refused` / `accepted` / `unsolicited`. (`E14`)
4. **Egress and observation window.** Calendar time, window length and start
   point (after subscribe), sessions run, reconnects, and egress region/ASN.
   (`E14`)

Every 600 s session in this write-up ran with **no compression offer**, so its
session state is `not_offered` for all five venues. Capability is a separate,
shorter probe (Section 3.1).

---

## 3. What we found

### 3.1 Compression is four states, not two

"Not offered" and "server refused" both look like "no compression" in a naive
implementation, but they are different physical facts. Probing capability with a
separate 60 s offer ladder (three `permessage-deflate` variants):

| Venue   | Capability probe state | Compressed frames | Evidence |
|---------|------------------------|-------------------|----------|
| LBank   | `server_refused` (3/3) | 0                 | `E02`, `E03` |
| Binance | `accepted`             | 62,058            | `E02` |
| Bybit   | `accepted`             | 313               | `E26` |
| OKX     | `accepted`             | 5 of 387 frames   | `E26` |
| Kraken  | `server_refused` (3/3) | 0                 | `E26` |

`accepted` does not mean every frame is compressed: OKX accepted the extension
but only 5 of 387 frames carried a compressed payload. Bybit's probe recorded a
larger **payload** rate than wire rate (958.9 wire vs. 2,583.0 payload B/s) -
the payload figure is the post-inflate size, so "compression made it bigger"
in that probe is not a contradiction, it is two different quantities. The lesson
is in the declaration, not in the number: a cross-venue byte comparison that
collapses four states into a boolean is comparing two different quantities.
(`E14`, `E26`)

### 3.2 Subscription receipts and control frames are structural

These counters did not move across sessions for the same venue - they are
properties of the feed's behaviour, not of the market's activity:

| Venue   | Subscribe acks | Control frames | Application heartbeat | Evidence |
|---------|---------------:|---------------:|-----------------------|----------|
| LBank   | 0              | 0              | inbound ping 10       | `E04`, `E37` |
| Binance | 1              | 30             | 0                     | `E13`, `E38` |
| Bybit   | 11             | 0              | server ping 2         | `E23`, `E29` |
| OKX     | 110            | 0              | string ping 2 / pong 2| `E24` |
| Kraken  | 20             | 0              | venue heartbeat 622-623| `E25`, `E30` |

The contrast between LBank (0 acks) and OKX (110 acks, one per subscription) is
the clearest single seam: a client that assumes an ack will never see one on
LBank, and a client that assumes no ack will fall out of sync on OKX. What is
*not* universal is the "no anchor" story - most venues do return receipts and
carry a monotonic id (see `E28` for the per-venue sequence/checksum semantics).
What these counters *are* useful for is exactly this: as structural invariants
that survive a noisy rate measurement.

### 3.3 Byte rates are intervals, not numbers

With repeated same-caliber sessions, a per-venue byte rate is a range:

| Venue   | wire B/s interval        | spread (n)  | msg/s interval        | Evidence |
|---------|--------------------------|-------------|-----------------------|----------|
| LBank   | 15,947.1 - 19,525.1      | +22.4% (3)  | 82.697 - 101.272      | `E13`, `E37` |
| Binance | 18,261.3 - 51,255.0      | +180.7% (3) | 134.289 - 376.245     | `E13`, `E38` |
| Bybit   | 5,619.8 - 10,159.5       | +80.8% (3)  | 15.478 - 26.951       | `E23`, `E29` |
| OKX     | 6,568.7 (n=1); interleaved median 6,534.7, range 3,968.2 - 14,377.1 | +262.3% (within one 12-min window) | 35.330 (n=1) | `E24`, `E35` |
| Kraken  | 39.2 - 84.8              | +116.3% (3) | 0.160 - 0.392         | `E25`, `E30` |

Per-message size is the stable companion: LBank p50 188-189 B, Binance 132-133 B,
Bybit 217-218 B, OKX 181-183 B, Kraken 194-195 B, constant across sessions.
So the venues differ in *rate* much more than in *point structure*: OKX pushes
more, smaller messages; Bybit pushes fewer, larger ones.

---

## 4. What we cannot conclude

### 4.1 A narrow byte-rate gap is undecidable

Two facts combine to make small byte-rate orderings undecidable:

- A venue's own spread can exceed the gap between venues (Section 4.3).
- A same-window **interleaved A/B** run (Bybit vs. OKX, 6 rounds x 60 s
  alternating, one connection per segment) still could not decide it: the paired
  difference `A-B` for `wire B/s` was
  `-7,819.1, -7,972.6, -582.1, +425.8, +2,177.4, +1,904.9` - the sign **flips
  once** and drifts monotonically, which points to market activity rather than
  instrument noise. (`E34`, `E35`, `E36`)

Consequences, stated as they are:

- **"Bybit > OKX by `wire B/s`" does not hold.** Bybit's own n=3 interval
  `[5,619.8, 10,159.5]` straddles OKX's 6,568.7. (`E31`)
- **"Binance > LBank by `wire B/s`" does not hold either.** At n=1 it looked
  like 51,255.0 vs. 17,438.7 (about 2.9x), but Binance's own n=3 interval
  `[18,261.3, 51,255.0]` overlaps LBank's `[15,947.1, 19,525.1]`. The one
  ordering that survives is the **message-rate direction** (Binance's `msg/s`
  minimum, 134.289, is still above LBank's maximum, 101.272 - a floor of about
  1.33x), and even that is a direction, not a stable multiplier. (`E13`, `E37`,
  `E38`)

What *is* decidable: the message-rate **direction** and the per-message **size**
(OKX's `msg/s` exceeded Bybit's in all 6 interleaved rounds, 1.33x-5.36x; p50
sizes separated cleanly at 217-218 B vs. 181-183 B). Rule of thumb from these
observations: treat byte-rate orderings separated by less than about 2x as
undecided unless each venue has several sessions. (`E35`, `E36`)

### 4.2 Kraken is not a throughput sample

In all three Kraken sessions the number of business frames (96-235) was *fewer*
than the venue's own heartbeat frames (622-623, about one per second), and the
absolute volume was 39-85 B/s. Its +116.3% spread is a relative figure on a tiny
base. This is not a claim that Kraken is "slow" - it is that this watchlist
under-samples Kraken, whose spot book here is thin (most of its assets quote in
USD, which was not measured). It is reported as a curve, not as a ranking.
(`E25`, `E30`)

### 4.3 A venue's own cross-session variation is as large as some between-venue gaps

The spread column in Section 3.3 is the headline caveat: Bybit +80.8%, Kraken
+116.3%, and Binance +180.7% across three same-caliber sessions each. LBank was
the most stable at +22.4%. Any single-session cross-venue comparison whose gap is
smaller than the compared venue's own spread is **not attributable to the
venue**. (`E29`, `E30`, `E37`, `E38`)

Additional limits that apply to everything above:

- **Not a distribution.** One session is an observation. Even the n=3 venues are
  three observations, not a distribution.
- **Different symbol sets.** Each venue is measured on its intersection with the
  159-asset watchlist (Bybit 103, OKX 110, Kraken 20), not a common set.
- **One egress.** All sessions ran from a single egress. A different region may
  change reachability and rates; re-measure before generalising.
- **Not measured.** No orders, no signing, no private channels, no load test, no
  CPU. The client-to-server direction is not measured.

---

## 5. How to reproduce

One command reproduces a session of this shape (standard library only, public
unauthenticated endpoints):

```console
python3 measure_ws.py --venue bybit --symbols-file symbols159.txt --duration 600 --out bybit-600s.json
```

Run `python3 measure_ws.py --selftest` for the offline self-test (no network).
The tool, the watchlist and every session file are in the repository:
<https://github.com/Robin1987China/ws-wire-audit>.

The interleaved A/B run (Section 4.1) uses the bundled driver:

```console
python3 interleave_ab.py --rounds 6 --duration 60 --a bybit --b okx \
  --symbols-file symbols159-ext-20260929.json \
  --out examples/15-interleaved-bybit-okx-20260930.json
```

---

## 6. Evidence index

Each code is a claim above; each link is the repository file that carries the raw
session output behind it. All session JSONs are curated aggregate summaries
(no raw tick data).

| Code | Claim it carries | Repository evidence |
|------|------------------|---------------------|
| `E02` | LBank refuses `permessage-deflate`; Binance accepts | `examples/02-permessage-deflate-negotiation.md` |
| `E03` | LBank refusal raised to n>=3 | `examples/03-lbank-deflate-ladder-probe.json` |
| `E04` | LBank: 0 subscribe acks, 10 inbound app pings, 0 control frames | `examples/01-lbank-vs-binance-159pairs-600s.json` |
| `E13` | LBank vs. Binance, 159 pairs, 600 s, same caliber | `examples/01-lbank-vs-binance-159pairs-600s.json` |
| `E14` | The four declarations | `SPEC.md` |
| `E23` | Bybit, 103 pairs, 600 s (r1) | `examples/04-bybit-103pairs-600s-20260929.json` |
| `E24` | OKX `trades-all`, 110 pairs, 600 s | `examples/05-okx-110pairs-600s-20260929.json` |
| `E25` | Kraken, 20 pairs, 600 s (r1) | `examples/06-kraken-20pairs-600s-20260929.json` |
| `E26` | Compression ladder: Bybit/OKX accept, Kraken refuses | `examples/07-`, `examples/08-`, `examples/09-` (deflate-ladder) |
| `E28` | Per-venue sequence / checksum / reconnect-backfill semantics | `contract-audit.md`, `SPEC.md` |
| `E29` | Bybit n=3 spread (wire +80.8%) | `examples/04-`, `examples/11-`, `examples/13-` (Bybit r1/r2/r3) |
| `E30` | Kraken n=3, heartbeat-dominated | `examples/06-`, `examples/12-`, `examples/14-` (Kraken r1/r2/r3) |
| `E31` | Cross-session spread limits n=1 between-venue byte comparison | `examples/04-`, `examples/05-`, `examples/11-`, `examples/13-` |
| `E34` | Interleaved same-window A/B design | `examples/15-interleaved-bybit-okx-20260930.json` |
| `E35` | Interleaved A/B readings (n=6 per venue) | `examples/15-interleaved-bybit-okx-20260930.json` |
| `E36` | Verdict: small-gap byte-rate ranking undecidable | `examples/15-interleaved-bybit-okx-20260930.json` |
| `E37` | LBank n=3 spread (wire +22.4%) | `examples/01-`, `examples/16-`, `examples/18-` (LBank r1/r2/r3) |
| `E38` | Binance n=3 spread (wire +180.7%); LBank/Binance intervals overlap | `examples/01-`, `examples/17-`, `examples/19-` (Binance r1/r2/r3) |

---

*Aggregated session statistics only; no raw tick data. Author identity per the
repository LICENSE. This document is static text and loads no external
resources.*
