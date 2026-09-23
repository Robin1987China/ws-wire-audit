# SPEC — Declaring Caliber Before Comparing WebSocket Feed Traffic

**Status.** A *proposed* rule of practice — not a standard, not adopted. **Not yet cited by any
third party** that we found (§4). Drawn from **one project's experience**; generalisation
unverified. Adopt as a checklist, not an authority.

---

## 0. The rule

> **Before comparing bandwidth, message rate, or message size across two WebSocket market-data
> feeds, declare four quantities: (1) what counts as a business message, (2) whether byte counts
> are payload or wire bytes, (3) the compression-negotiation state, and (4) the egress and the
> observation window.**
>
> Two numbers produced under undeclared — or differing — choices of these four are not a
> comparison, even when both are correct.

The rule governs the *declaration*, not the instrument: follow it with any client, without this
repository's tool. A claim checkable only with our tool is a product pitch, not something
citable. The four are not exhaustive; they are where two honest measurements of the "same"
thing legitimately differ — invisibly, in the final number.

## 1. The four declarations

Each: **Definition** (decidable without asking the author) · **Why** (wrong conclusion if
undeclared) · **Declare this** · **Tool**. Line numbers refer to the v1.3 `measure_ws.py` as
shipped in this package — **field names are the stable reference**; line numbers drift with edits.

### 1.1 Business-message definition

**Definition.** One inbound data frame, not classified as an RFC 6455 control frame, an
application heartbeat, or a subscribe ack.
**Why.** Heartbeat styles differ: server pongs, client pings, or an ordinary-looking
`{"action":"ping"}` payload frame. Counting heartbeats as messages inflates the rate with no
change in business traffic; acks add a setup-dependent term.
**Declare this.** "One message = one inbound data frame, excluding control frames, heartbeats and
acks. **Inbound only.** Fragments not reassembled."
**Tool.** `business_messages`, `msg_per_s`, `msg_types`; exclusions are counted separately and
never folded in — `app_ping_frames`, `subscribe_acks`, `control_frames`,
`heartbeat_pongs_received` (L356/L367/L374; branches L878–915; control frames L419–427).
**Not implemented — declare yourself:** fragmentation reassembly (a fragment counts as a
message; inflate may fail on non-first fragments — README §5.2); semantic equivalence across
venues is not validated (README §4 note); the classifier is venue-configured
(`app_ping_field`, ack-key heuristics).

### 1.2 Payload vs. wire bytes

**Definition.** `payload_bytes` = inbound payloads **after decompression**; `wire_bytes` =
inbound **WebSocket frame lengths as read**, header included (compressed for a compressed
frame); `wire_bytes_total` = those plus heartbeat/ack/control frames. Under `permessage-deflate`,
payload ≥ wire; otherwise they track.
**Why.** "Bytes/s" is ambiguous by a factor set by compression, and the two quantities move in
*opposite* directions between venues: a compressing venue looks lighter on the wire and heavier
in payload. In `examples/02-permessage-deflate-negotiation.md`, one session's `payload_bytes`
exceeded its `wire_bytes` by roughly 27%. The arithmetic is the point, not the venue.
**Declare this.** "Bytes are **payload (post-inflate)** / **wire (as-read, compressed)** — say
which; **one direction** (server→client); **WebSocket frame bytes**, excluding TLS/TCP/IP."
**Tool.** `payload_bytes`, `payload_bytes_per_s`, `wire_bytes`, `wire_bytes_per_s`,
`wire_bytes_total`, `control_wire_bytes`, `size_bytes` (per-message payload
min/p50/p90/p99/max/mean). Inflate L358 with L320–332; wire length `header_len + ln` L418.
**Not implemented — declare yourself:** TLS/TCP/IP overhead excluded (a TCP- or NIC-level
counter will not reproduce `wire_bytes`); client→server bytes not measured at all (frames sent
RSV1=0, L248); no packet-capture cross-check.

### 1.3 Compression-negotiation state

**Definition.** Four states, from the pair (we offered `permessage-deflate`; the 101 response
lists `permessage-deflate` by exact token):

| State | Offered | Accepted | Means |
|---|---|---|---|
| `not_offered` | no | no | **We never asked.** Says nothing about the server. |
| `server_refused` | yes | no | The server declined *our* offer. |
| `accepted` | yes | yes | Compression active; payload ≠ wire. |
| `unsolicited` | no | yes | Server sent an extension we did not request. |

A fifth diagnostic, `not_offered_server_sent_other_extension`, covers a response carrying *some
other* extension while we offered nothing — the case that makes a naive boolean wrong.
**Why.** A client that never offers cannot distinguish "server refused" from "we never asked":
both render as "no compression", and a capability conclusion is drawn from a measurement that
never tested capability.
**Declare this.** The state **and both header strings** (offer sent, response received). Never a
boolean. With a multi-variant probe, say which offer the *measured* session itself carried.
**Tool.** `deflate_offered`, `deflate_accepted`, `deflate_status`, `deflate_offer_header`,
`deflate_response_header`, `deflate_probe[]`, `deflate_probe_all_refused`,
`deflate_measurement_offer_source` (`none | single-offer | ladder-accepted |
ladder-fallback-first-offer`), `compressed_frames`, `inflate_failures`. Token-exact match L222;
states L234; `server_no_context_takeover` / `server_max_window_bits` applied L306–315.
**Not implemented — declare yourself:** client→server compression (never used); a measured
session carries **one** offer variant — the ladder only *probes* the others; other negotiation
parameters are parsed but not applied.

### 1.4 Egress and observation window

**Definition.** **Egress** = the public network origin of the connection (region/ASN/IP), not
merely the proxy setting. **Window** = calendar start and end, length, and **when the clock
starts** (after subscribe, not after TCP connect), plus sessions run and reconnects.
**Why.** Venues gate or reroute public access by region, so results are not portable across a
network path without re-measurement. Session rates move with market activity: a bare "90 msg/s"
is not a fact about a venue, and one session is an observation, not a distribution.
**Declare this.** "Observed \<date, timezone\>, window N s **starting after subscribe**, M
sessions, no reconnects, egress \<region/ASN\> — or *unknown*." Write "unknown"; do not omit it.
**Tool.** `requested_seconds`, `elapsed_s`, `wall_clock_s`, `proxy`, `ws_url`, `reconnects`
(never reconnects, so always `0`), `collection_complete`, `error`.
**Not implemented — declare yourself:** no calendar timestamp anywhere (`elapsed_s` is a
duration; there is no `date`/`observed_on` key); the proxy string is recorded but not the egress
IP/ASN/region; no session aggregation (`n_sessions` is hand-added in the curated `examples/`,
whose key set is a subset of live output — README §7).

## 2. Glossary

| Term | Meaning here |
|---|---|
| **Business message** | One inbound data frame not classified as control / heartbeat / ack (§1.1). |
| **Control frames** | RFC 6455 opcodes 0x9 (ping), 0xA (pong), 0x8 (close): protocol-level, auto-answered, never business data. |
| **Payload bytes** | Post-inflate application bytes. |
| **Wire bytes** | On-wire WebSocket frame bytes as read (header + payload), compressed if it arrived compressed. Excludes TLS/TCP/IP. |
| **Frame vs. message** | Here one frame = one message; fragmented messages are not reassembled. |
| **`permessage-deflate`** | RFC 7692 compression extension, negotiated per connection via `Sec-WebSocket-Extensions`. |
| **Negotiation state** | `not_offered` / `server_refused` / `accepted` / `unsolicited` (§1.3). |
| **RSV1** | The frame bit marking a compressed payload under RFC 7692. |
| **Egress** | The public network origin of the connection (region/ASN/IP). |
| **Window** | The observation interval and its start condition (§1.4). |
| **Caliber** | The full set of counting rules in force for a figure (§0). |

## 3. How to cite

**Full form.**

> "When comparing message rates or bandwidth across WebSocket market-data feeds, declare four
> quantities first — the business-message definition, payload vs. wire bytes, the
> compression-negotiation state, and the egress and observation window — as set out in the
> *ws-wire-audit* SPEC (2026)."

**Inline form.**

> "…under a declared caliber [business message = non-heartbeat inbound data frame; wire bytes =
> on-wire frame bytes; compression state `not_offered`; single 600 s session], …"

```
ws-wire-audit SPEC (2026). "Declaring Caliber Before Comparing WebSocket Feed Traffic."
Author identity per the repository LICENSE. https://<repo-url>/SPEC.md
```

Cite the **rule**, not a number: the rule is meant to outlive the readings. Numbers in this
repository are single observations and must not be cited as venue properties.

## 4. Honest boundaries

1. **Not yet cited.** As of 2026-09-23 we found **no third-party citation** of this rule; its
   value as a citable claim is an **expectation, not an established fact**.
2. **Single-source.** Distilled from **one project's measurement experience**; transfer to other
   venues, asset classes or feed types is **unverified**.
3. **No case studies.** No venue comparison, no case study: using a directed measurement, made
   for one party's question, as a *case* would misrepresent both the evidence and the rule. The
   single number in §1.2 is an in-repository worked example of the arithmetic.
4. **No verdicts.** It does not claim any venue is better or worse: compression refusal can be a
   deliberate server-side CPU/memory trade-off, and RFC 7692 makes negotiation optional.
5. **Instrument-independent.** Actionable with any conforming client; where a tool does not
   implement a declaration, the omission is marked, not quietly filled with a guess.

---

## 附录：中文说明

**一页主张**：跨所比较 WebSocket 行情的带宽/消息率之前，**必须先声明四个量**，否则两个各自
都正确的数字仍然不可比：

1. **业务消息定义** —— 什么算一条消息（本仓口径：入站数据帧，剔除控制帧、应用层心跳、订阅
   回执；**只统计入站方向**；**不做分片重组**）。不声明 → 把心跳算进消息数的一方与不算的一方
   "差出"一个纯口径差。
2. **payload 与 wire 的区别** —— 字节数是**解压后 payload** 还是**压缩后 wire**；本仓 `wire`
   只含 WebSocket 帧（含帧头），**不含 TLS/TCP/IP**，且**不测客户端上行**。不声明 → 压缩与否
   带来几十个百分点的差异被误读成"某所更重"。
3. **压缩协商状态** —— 四态（`not_offered` / `server_refused` / `accepted` / `unsolicited`），
   不是真假值。从不发起 offer 的客户端，测不出服务端能力。本仓另记
   `deflate_measurement_offer_source`，说明**测量会话自身**带没带 offer。
4. **出口与窗口** —— 日历时间（含时区）、窗口长度与**起算点**（订阅之后）、会话数、是否重连、
   以及**出口地区/ASN**。**本工具未实现**日历时间戳与出口记录（只记 proxy 字符串，`n_sessions`
   是示例文件里手工加的键）——**属调用方需自行声明**。

**诚实边界**：该主张**尚未被任何第三方引用**（本轮检索未找到），属**预期**而非既成事实；
来自**单一项目经验**，泛化性未验证；本文**不含任何交易所对比、不含案例**；工具只碰公开行情
端点，单连接、不重连、不并发。

**引用**：见 §3；引用"规则"而非某个读数。
