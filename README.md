# ws-wire-audit

> **Attribution (settled 2026-09-23).** Copyright holder and public author identity:
> `Robin1987China` — the same identity used for the upstream contributions in this
> project's record. Do not publish this repository until the remaining items in the
> release checklist are complete.

A standard-library-only measurement tool for **wire-level traffic and
compression negotiation on public market-data WebSocket feeds**.

It answers the question *"what does this feed actually put on the wire?"* —
message counts, byte counts, message-size distribution, and whether
`permessage-deflate` was negotiated — for a single WebSocket connection, with
no dependencies and no authentication.

---

## 1. What it is

`measure_ws.py` opens **one** public WebSocket connection to an exchange's
market-data endpoint and records, per session:

| Field group | What is measured |
|---|---|
| Throughput | `business_messages`, `msg_per_s`, `payload_bytes`, `wire_bytes`, `wire_bytes_total` (incl. control frames) |
| Distribution | `size_bytes` — min / p50 / p90 / p99 / max / mean of per-message payload sizes |
| Compression | `deflate_offered`, `deflate_accepted`, `deflate_status`, offer/response header text, `compressed_frames`, `inflate_failures`, `rsv1_without_deflate` |
| Accounting hygiene | `app_ping_frames`, `heartbeat_pongs_received`, `subscribe_acks`, `subscribe_errors`, `control_frames` |
| Integrity | `collection_complete`, `error`, `first_msg_latency_ms`, `sec_websocket_accept_valid` |

Its distinguishing property is **accounting discipline**: application-level
heartbeats, subscribe acks, and control frames are counted in their **own**
fields and are *excluded* from `business_messages` / `payload_bytes` /
`wire_bytes` / `size_bytes` / `msg_types`. Comparing raw byte counters across
venues without this separation produces the wrong answer, because venues differ
wildly in heartbeat style (client-driven pings vs. server-driven pongs vs.
`{"action":"ping"}` payload frames).

## 2. What problem it solves

Cross-venue comparisons of "which exchange's feed is heavier?" are usually done
by pointing two different clients (often two different libraries) at two
endpoints and comparing numbers from two different code paths. That is an
**apples-to-oranges** comparison, because:

- one client may count heartbeats as messages, the other may not;
- one may include subscribe acks, the other may exclude them;
- one may negotiate `permessage-deflate` and report *decompressed* payload size,
  the other may report *compressed* wire size — a 10x-class difference;
- a client that never offers compression cannot distinguish *"server refused
  compression"* from *"we never asked"*, and will silently report "no
  compression" for both.

This tool exists to **align the caliber (口径) before comparing numbers**: one
measurement code path, one accounting rule set, applied identically to every
venue, with compression negotiation reported as an explicit four-state value
(`not_offered` / `server_refused` / `accepted` / `unsolicited`) rather than a
boolean.

The intended use is **caliber alignment for cross-exchange comparison** — it is
a measurement instrument, not a benchmark, and not a load generator.

## 3. How to use

Requires **Python 3.8+** — standard library (`socket`, `ssl`, `zlib`,
`struct`, `hashlib`, `base64`, `json`). No `ccxt`, no `websockets`, no
`aiohttp`. See `requirements.txt`.

### Offline self-test (no network, no endpoints contacted)

```console
$ python3 measure_ws.py --selftest
```

This drives the handshake parser and frame reader against **synthetic**
handshake/frame byte streams and asserts the compression-negotiation states,
the multi-symbol subscription batching, and the accounting invariant
(`wire_bytes_total >= wire_bytes`). It never opens a socket. Run this first to
confirm the tool behaves as documented on your machine.

### A single default session (three venues, 60 s each, one pair)

```console
$ python3 measure_ws.py
```

Three sessions run **sequentially** (never in parallel), one connection each,
with a sleep between venues. Output is a JSON file (`--out`, default
`measure_ws_result.json`) plus a console table.

### Compression negotiation probe

```console
$ python3 measure_ws.py --venue lbank --deflate
$ python3 measure_ws.py --venue lbank --deflate --deflate-ladder
```

`--deflate` sends `Sec-WebSocket-Extensions: permessage-deflate` in the
handshake. `--deflate-ladder` walks a small ladder of offer variants
(bare / with params / with explicit window bits) so that *"the server refused"*
can be separated from *"our offer was malformed"*. Both report
`deflate_measurement_offer_source` so a reader can tell whether the **measured**
session itself carried the offer or only the probe did.

### Probe & automation flags (v1.4)

```console
$ python3 measure_ws.py --probe --venue lbank                 # handshake only, no subscribe/collect
$ python3 measure_ws.py --probe --deflate --venue lbank       # connectivity + compression acceptance
$ python3 measure_ws.py --venue lbank --duration 600 --strict  # exit 1 if any session misbehaved
$ python3 measure_ws.py --version
```

- `--probe` opens the connection and performs the handshake (with the offer
  selected by `--deflate` / `--deflate-ladder`), then closes immediately —
  no subscription, no collection. It is the fast path for "can I reach this
  endpoint and does it accept compression?" without a full session.
  Note: `--probe` ignores `--pair` (there is no subscribe step for an override
  to apply to), but the result is still written to `--out` like a normal run.
- `--strict` exits with code **1** when any measured session ended with an
  `error`, `collection_complete=false`, `inflate_failures > 0` or
  `rsv1_without_deflate > 0`; exit 0 otherwise. Intended for scripts and
  monitoring that must not treat a broken session as a clean run.
- `--version` prints the tool version (`v1.4`) and exits.

### Multi-symbol session (large watchlists)

```console
$ python3 measure_ws.py --venue lbank  --symbols-file symbols159.json --duration 600
$ python3 measure_ws.py --venue lbank  --symbols-file majors.txt --duration 600
```

Multiple symbols are **not** split across connections: one connection carries
as many subscription frames as the venue's publicly documented batching allows
(LBank = 1 pair per frame, Binance = up to 1024 streams per frame, Bybit = up to
10 args per frame; see `subscribe_batch_size` in the script and re-verify it
against current docs before running).

### Proxy

```console
$ HTTPS_PROXY=http://127.0.0.1:8080 python3 measure_ws.py --proxy http://127.0.0.1:8080
```

Only HTTP `CONNECT` is implemented. SOCKS5 is not supported; point the proxy at
a mixed HTTP/SOCKS port if your local client exposes one.

Full flag list: `python3 measure_ws.py --help`.

## 4. A real conclusion from a real run

The tool's first studied case was a reported bandwidth/CPU gap between
**LBank** and **Binance** public trade streams (`ff, watch_trades`, CCXT
issue #27008). Two questions only a wire-level instrument can separate:

**(a) Is the gap a compression-negotiation difference?** The ladder probe says
**no**. Offering three variants of `permessage-deflate` to LBank's public WS
endpoint, the server returned **no** `Sec-WebSocket-Extensions` header in the
101 response for any variant → `deflate_status = server_refused`,
`deflate_probe_all_refused = true`. Binance, offered the same header, **accepted**
(`deflate_status = accepted`). So compression is *available on one venue and
refused on the other* — which means any comparison that reports "payload bytes"
must state whether it means decompressed payload or compressed wire bytes, or
the two venues are not being compared on the same quantity.

**(b) Aligning caliber, how far apart are they?** With the **same** script,
same 159 symbols, same 600 s window, same single-connection/no-reconnect rule,
and heartbeats/acks excluded from business metrics:

| Metric (600 s, 159 symbols) | LBank | Binance |
|---|---|---|
| Business messages | 54,309 | 225,749 |
| Messages / s | 90.5 | 376.2 |
| Wire bytes / s | 17,439 | 51,255 |
| Payload size p50 | 188 B | 132 B |
| Payload size p99 | 202 B | 136 B |
| `deflate_status` (no offer) | `not_offered` | `not_offered` |

> **Caliber note (read with the numbers):** the ratios below are ratios **under this tool's accounting
> rule** — control frames, heartbeats and acks are excluded from business figures, and `payload_bytes`
> (post-decompression) is reported separately from `wire_bytes` (post-compression). They are **not** a
> claim that a "message" means the same business event on both venues: **cross-venue semantic
> equivalence was not validated** (see SPEC §1.1, "Not implemented", item 2). Treat them as **accounting-caliber ratios**.

Read this as: **at equal caliber, Binance's trade stream carries ~4.2x the
messages and ~2.9x the wire bytes per second, while each of its messages is
~0.7x the size (median 132 B vs 188 B).** The two venues differ in *rate* and
in *per-message size in opposite directions* — Binance wins on volume by
sending many more, smaller messages. That is precisely the kind of compound
statement a "my library said X bytes" comparison cannot make: a single
aggregate byte count cannot tell you whether it is composed of few-large or
many-small messages, and the two venues here are not the same shape.
Reproducible artifacts (aggregate-only, desensitised): `examples/`.

> Caveat (see §5): these are two single sessions on one day from one egress,
> not a distribution. The tool reports a session; it does not establish that
> the observed ratio is stable over time — **nor that the two venues' messages
> are semantically equivalent** (accounting rule is shared; business semantics
> were not cross-validated).

## 5. Limitations — read before citing

The tool measures **one connection over one interval from one network egress**.
It is designed to be honest about what that does and does not support.

1. **Single observation is not a distribution.** Session-level numbers
   (`msg_per_s`, `wire_bytes_per_s`) move with market activity. Report a
   timestamp and a window, not a bare number; do not upgrade n=1 into a
   "venue X is always lighter" claim.
2. **No fragmentation reassembly.** The reader treats *one frame = one
   message*. If a server fragments a message under `permessage-deflate`, each
   fragment is counted separately and per-frame inflate may fail, falling back
   to the undefined-semantics payload size (typically a raw DEFLATE stream) →
   inflated counts. Public trade streams use short frames,
   but **this is an unhandled gap, not a verified non-issue.**
3. **Inflate failures are surfaced, not hidden.** Since v1.2 an inflate failure
   increments `inflate_failures` instead of silently reporting the
   undefined-semantics payload size (typically a raw DEFLATE stream);
   a non-zero value invalidates the size distribution for that session.
4. **`rsv1_without_deflate`.** A server frame with RSV1=1 without negotiated
   `permessage-deflate` violates RFC 6455 §5.2, which requires *failing the
   WebSocket connection*. This tool deliberately continues in order to keep
   measuring, and counts such frames in `rsv1_without_deflate` instead; their
   payload semantics are undefined (typically a raw DEFLATE stream, not
   business plaintext), so a non-zero value also invalidates the size
   distribution for that session.
5. **`permessage-deflate` negotiation parameters are partially honoured.**
   v1.3 parses and applies `server_no_context_takeover` and
   `server_max_window_bits` (per-message inflater reset and window bits), but
   only the server→client direction is decompressed; client→server frames are
   always sent uncompressed (RSV1=0), which RFC 7692 permits.
6. **Batching limits are configuration that drifts.** `subscribe_batch_size`
   and endpoint paths are hard-coded per venue and reflect the public docs **at
   the time of writing**. Re-verify before a run; a venue silently lowering its
   per-frame symbol limit changes `subscribe_acks` and error counts, not the
   wire-level message rate.
7. **Only public endpoints.** No API keys, no signing, no private channels, no
   order or funding endpoints. Single connection, no reconnect, no concurrency,
   no load testing: this is a *measurement* tool, not a stress tool.
8. **Egress matters.** Some venues gate public API access by egress region and
   will return different results (or refuse connections) from a different
   network path. Record your egress; results are not portable across it without
   re-measurement.
9. **`Sec-WebSocket-Accept` is validated and recorded, not enforced.** A
   handshake-validation failure is reported so a reader can judge it; the
   session is not aborted, because a measurement run prioritises collecting
   data over refusing to run.

## 6. Repository layout

```
ws-wire-audit/
├── README.md            # this file
├── LICENSE              # MIT (copyright holder: Robin1987China)
├── CHANGELOG.md         # version history for measure_ws.py (moved out of the source)
├── measure_ws.py        # the measurement tool (stdlib only)
├── requirements.txt     # "none" — standard library only
├── symbols159.json      # the 159-pair watchlist used for the headline session
├── examples/            # desensitised aggregate results (no raw ticks)
│   ├── README.md
│   ├── 01-lbank-vs-binance-159pairs-600s.json
│   ├── 02-permessage-deflate-negotiation.md
│   └── 03-lbank-deflate-ladder-probe.json
├── pyproject.toml        # packaging (zero runtime deps) + pytest/ruff config
├── tests/                # offline pytest suite (79 cases, zero network)
│   └── test_measure_ws.py
├── contract-audit.md     # companion report: LBank public API contract issues
└── SPEC.md               # proposed four-declaration rule for cross-venue comparison
```

### ✅ Publication status

**Publication-ready as of 2026-09-23.** The pre-publication checklist file
(`PENDING-SANITIZATION.md`) has been removed; every blocker it tracked is
resolved, with the verification recorded here:

1. **Internal identifiers in `measure_ws.py` — resolved.** The `User-Agent` is
   now `Mozilla/5.0 (compatible; ws-wire-audit/1.3)`; the module docstring, the
   self-test docstring and the run-summary banner are neutral; and the version
   history block (which carried internal process references) has been moved to
   `CHANGELOG.md` in sanitised form.
2. **`LICENSE` copyright holder — resolved** (2026-09-23: `Robin1987China`).

All of these were comment/header/metadata-level changes that do not alter
program behaviour. Verified after sanitisation:

```console
$ # (internal-term scan: run privately; the term list is not reproduced here)
# zero matches
$ python3 measure_ws.py --selftest     # 自测结果：全部通过 (35 assertions)
$ python3 -m pytest tests/ -q          # v1.4 offline suite: 79 passed
$ shasum -a 256 measure_ws.py
6fc6d43d6fdc99c97da0bf8dfffcb983bedc0f3bbd71ddc337d2dd999413124b  measure_ws.py
```

### `tests/` and packaging (v1.4)

The tool stays a single stdlib-only file — that is its design contract ("the
accounting rules are visible in one file"). What v1.4 adds around it:

- `pyproject.toml`: zero runtime dependencies, `ws-wire-audit` console script
  (`python3 -m pip install .` then `ws-wire-audit --version`), pytest and
  ruff (`F`, `E9` — bug-catching only) configuration.
- `tests/test_measure_ws.py`: **79 offline pytest cases** (zero network)
  covering the handshake/extension parser, the frame reader (control frames,
  pong echo, deflate window bits, no-context-takeover, inflate failures,
  RSV1-without-negotiation), session accounting (heartbeat/ack segregation,
  error-path data retention, ladder offer decisions, probe-only mode) and the
  CLI (strict exit codes, symbols-file errors). The built-in `--selftest`
  remains the 35-assertion smoke check.

### `contract-audit.md`

**23 numbered items** about **LBank's public API contract**: **17 contract-level
defects** (documentation-vs-implementation mismatches, missing documentation)
plus **6 non-contract items** (3 reachability / repo-ops, 1 n=1 behaviour
observation, 1 undetermined, 1 closed non-defect). Each item carries a
reproduction method and an evidence grade (A = official doc text or official
endpoint observation / B = third-party public source). It is the tool's first
substantive output: it is the report that motivated the wire-level measurements
above.

It is kept in this repository (rather than a separate one) because the tool and
the report are one argument: *the report states the contract-level findings, the
tool is the instrument that produces the wire-level ones.* Splitting them makes
the tool look like a generic utility and the report look like an unsourced
opinion. See §4 of the release plan for the trade-off.

## 7. Provenance and honesty rules the author applies

- Every number in this repository is traceable to a **stored artifact that ships with it**:
  the per-session summary JSONs under `examples/` (each carries `observed_on`, `produced_by`
  and a `reproduce` block). **Raw per-frame session dumps, and the individual HTTP response
  captures the contract checklist cites, are not shipped** (size and third-party content);
  findings that rest on those are marked *not public* rather than asserted.
- The `examples/` JSONs are **curated summaries**: their key set is a **subset** of the tool's
  live per-session output. Where a field is absent from a summary, treat it as not published.
- Single observations are labelled as such; negative findings are written as
  *"not seen in the public material we searched"* rather than *"does not
  exist"*.
- Facts and inferences are labelled separately; no absolute quantifiers
  ("all", "never", "only") appear without a stated sample.
- No exfiltration: the tool only writes local JSON; nothing is uploaded.

---

## 附录：中文说明

**这是什么**：一个只用 Python 标准库的**线级（wire-level）流量测量工具**，
面向**公开行情 WebSocket**。它测的是"这条连接到底在线上发了多少东西"：
消息数、字节数、消息大小分布，以及是否协商了 `permessage-deflate` 压缩。

**解决什么问题**：跨交易所比较"谁的行情更重"时，如果两边用的是不同客户端/
不同库，口径就不可比 —— 一边把心跳算进消息数、一边不算；一边报解压后的
payload、一边报压缩后的线字节；一个从不发起压缩协商的客户端，根本分不清
"服务端拒绝了压缩"和"我们压根没问"。本工具用一个代码路径、一套记账规则，
对每个交易所**用同一把尺子**测，并把压缩协商结果报成四态
（`not_offered` / `server_refused` / `accepted` / `unsolicited`）而不是真假值。
用途定位：**跨所对比前的口径对齐**。

**怎么用**：先跑 `python3 measure_ws.py --selftest`（零网络自测，验证本机行为
与文档一致），再按需跑 `--venue` / `--deflate-ladder` / `--symbols`。详见 §3。

**一个真实结论**：同一脚本、159 个交易对、600 秒、单连接不重连，把心跳与订阅
回执排除在业务指标之外后 —— Binance 的成交流每秒消息数约为 LBank 的 **4.2 倍**、
每秒线字节约为 **2.9 倍**；但**单条消息反而更小**（中位数 132 B vs LBank 188 B，
约 **0.7 倍**）。也就是说两所在「条数」与「单条大小」上方向相反：Binance 靠
"更多、更小"的消息取得总吞吐优势。压缩方面：LBank 对三种 `permessage-deflate`
offer 变体**全部拒绝**，Binance **接受**。这意味着任何跨所比较都必须声明
"payload 字节"指解压前还是解压后。

**局限**：单连接、单时间窗、单出口 = 一次会话，不是分布（不要用 n=1 做定性）；
未做分片重组（已知缺口）；批量订阅上限属会漂移的配置，运行前需复核；只碰公开
端点，不重连、不并发、不压测；出口地区会改变可达性结论。完整 8 条见 §5。

**署名**：**`Robin1987China`**
