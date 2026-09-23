#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
measure_ws.py —— public market-data WebSocket wire-level traffic measurement
版本 v1.3（2026-09-22）：修三处硬缺陷（D1 压缩协商判定 / D2 多交易对规模 / D3 测量会话未带 offer）；见同目录 CHANGELOG.md。

目的
    量化 CCXT #27008 的核心现象：「lbank watch_trades 带宽与 CPU 消耗显著高于其他所」。
    本脚本只测**线级（wire-level）事实**：消息数、字节数、消息大小分布、是否协商压缩。
    它**不测**客户端 CPU（那属于客户端库侧）。

纪律（硬约束，写在代码里）
    * 只连**公开**行情端点，不带任何密钥、不订阅私有频道。
    * 每场次默认采集 60 秒（`--duration` 可到 600 秒），**单连接、无重连、无并发、无压测**。
    * 多交易对**不拆连接**：一条连接上用多条订阅报文（按各所公开协议的批量能力分块）。
    * 三场次**顺序**执行（不是并行），场次之间 sleep。
    * 结果只写本地 JSON/标准输出。**本脚本不运行由 agent 自动触发**，需人工执行。

用法（人工）
    python3 measure_ws.py                                  # 三所各 60 秒，单 pair（btc_usdt/BTCUSDT）
    python3 measure_ws.py --venue lbank --deflate          # 主动 offer 压缩，看服务端是否接受
    python3 measure_ws.py --venue lbank --deflate --deflate-ladder   # 逐个 offer 变体探测（最强证据）
    python3 measure_ws.py --venue lbank --symbols-file symbols159.json --duration 600   # 159 对长场次（随包清单，与 README §3 头条一致）
    python3 measure_ws.py --venue lbank --symbols-file majors.txt --duration 600
    python3 measure_ws.py --selftest                        # 离线自测（零网络），只跑断言

依赖
    仅 Python 3 标准库（socket/ssl/zlib/struct/hashlib/base64/json）。不依赖 ccxt / websockets / aiohttp。
    本机若走代理，请设 HTTPS_PROXY（脚本会读环境变量；否则直连）。

⚠️ 运行前须人工确认（本脚本的端点配置不是权威来源）
    1. 三所官方文档的当前 WS 端点与订阅报文（版本会漂移）。
    2. LBank 官方声明 "Please initiate API calls with non-China IP"；请在合规出口运行。
    3. 若目标所对同一 IP 的多场次连接有连接数限制，请把 --sleep 调大。
    4. 多交易对订阅的**批量能力**按各所公开协议实现，但上限（每报文 args 数 / 每连接 stream 数）
       属会漂移的配置：见 VENUES[*]["subscribe_batch_size"] 与 "subscribe_notes"，运行前复核。

⚠️ 统计口径与已知假设（v1.1 明确，v1.2 续）
    1. **应用层心跳不计入业务指标**：LBank 的 `{"action":"ping"}`、Bybit 的 `{"op":"ping"}`/
       `{"op":"pong"}` 帧只计进 `app_ping_frames` / `heartbeat_pongs_received`，**不**进
       `business_messages` / `payload_bytes` / `wire_bytes` / `size_bytes` / `msg_types`。
    2. **订阅回执同样不计入业务指标**（v1.2 新增）：`{"result":null,"id":1}`（Binance
       SUBSCRIBE 回执）、`{"success":true,"op":"subscribe"}`（Bybit）计进 `subscribe_acks`；
       `success=false` 计进 `subscribe_errors`（多交易对场景下这是「某交易对不存在」的直接信号）。
    3. **客户端主动心跳**：Bybit v5 公开流服务端**不主动**发 ping，客户端须每 <20 秒发一次
       `{"op":"ping"}`，否则约 20 秒被断连。脚本对 bybit 使用 15 秒主动心跳（`active_ping_interval`）。
    4. **未实现分片重组**：读取器按「一帧即一条消息」处理。若服务端在 permessage-deflate 下分片，
       分片会被各计一次、且按帧解压可能失败而退回密文尺寸 → 计数虚高。三所公开成交流的
       报文均为短消息，但**本项是未处理的已知缺口，不是已验证事实**（v1.2：解压失败不再静默，
       计入 `inflate_failures`）。
    5. **压缩方向**：本脚本**只解压服务端帧**；客户端发出的帧一律 RSV1=0（不压缩）。
       RFC 7692 允许 per-message 选择：未压缩帧 RSV1=0 是合法的，故不影响服务端行为。
    6. **异常不丢数据**：任何中途异常（EOF/超时/解析失败）都会把**已采集到的**统计写入结果，
       并把 `collection_complete` 置 false、`error` 记原因（v1.1 修 V-09）。
    7. **代理**：只实现 HTTP CONNECT（`HTTPS_PROXY=http://host:port`）。本机是 socks5 时，
       请把代理指向 Clash 的**混合端口**（HTTP 兼容口），本脚本不实现 SOCKS5 协商。
    8. 握手会计算并记录 `Sec-WebSocket-Accept` 校验结果（`sec_websocket_accept_valid`），
       校验失败**只记录不中断**（测量脚本以采集为主，异常暴露给判读）。

三所多交易对订阅能力（`subscribe_batch_size` 的出处，**运行前须复核**）
    lbank   : 1  —— 公开订阅报文以**单 pair**为单位（`{"action":"subscribe","subscribe":"trade","pair":"btc_usdt"}`）。
                    N 个 pair = 同一连接上 N 条订阅报文（顺序发，`--subscribe-interval` 节流）。
    binance : 1024 —— 公开文档的 SUBSCRIBE 批量法：`{"method":"SUBSCRIBE","params":["btcusdt@trade",...],"id":1}`，
                    一条连接上最多 1024 个 stream（本实现按 1024 分块，超限则同一连接多发几条）。
    bybit   : 10 —— v5 `{"op":"subscribe","args":["publicTrade.BTCUSDT",...]}` 可带多个 args；
                    单报文 args 上限取**保守值 10**（本机未联网复核，取小不取大以免被拒）。

★ v1.2 关键修复（对齐 #27008 条件重测）
    [D1] 压缩协商判定：v1.1 用 `inflate = bool(响应里的 Sec-WebSocket-Extensions 值)` 判定
         —— 只要服务端回**任意**扩展（例如 `x-webkit-deflate-frame`）就被当成 permessage-deflate
         接受并去解压，且「我们没 offer」与「服务端拒绝」在输出里都是 `None`，无法区分。
         修：按 RFC 6455 §9.1 / RFC 7692 解析扩展列表，只有在扩展列表里**按 token 精确匹配**到
         `permessage-deflate` 才算接受；输出 `deflate_offered` / `deflate_accepted` /
         `deflate_status`（not_offered｜server_refused｜accepted｜unsolicited）/ offer 与响应原文；
         并提供 `--deflate-ladder` 逐个 offer 变体探测（bare/params/full），把「服务端拒绝」
         从「我们 offer 写错」里分离出来。
    [D1b] 压缩参数与上下文接管：v1.1 无视 `server_no_context_takeover` / `server_max_window_bits`，
         用**一个持久 inflater** 处理全部消息；v1.2 解析协商参数，按需每消息重置 inflater 与
         窗口位数，并把解压失败计入 `inflate_failures`（不再静默退回密文尺寸）。
"""

import argparse
import base64
import hashlib
import json
import os
import re
import socket
import ssl
import statistics
import struct
import sys
import time
import zlib

# ---------------------------------------------------------------- 常量
SCRIPT_VERSION = "v1.3"
DEFAULT_SAMPLE_ASSETS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC",
    "DOT", "TRX", "MATIC", "SHIB", "UNI", "ATOM", "ETC", "FIL", "APT", "ARB",
    "OP", "NEAR", "INJ", "SUI", "SEI", "TIA", "PEPE", "WIF", "TON", "ORDI",
]
# 压缩 offer 变体（RFC 7692）。ladder 顺序：从「最小 offer」到「带窗口参数的 offer」。
DEFLATE_OFFERS = {
    "bare": "permessage-deflate",
    "params": "permessage-deflate; client_max_window_bits",
    "full": "permessage-deflate; client_max_window_bits=15; server_max_window_bits=15",
}
DEFLATE_LADDER = ["bare", "params", "full"]

# ---------------------------------------------------------------- 端点配置
# 说明：这些是公开文档里常见的端点/报文；**运行前请人工回官方文档复核**。
#       active_ping_interval = 客户端**主动**发应用层心跳的间隔（秒），None = 不需要主动发。
#       symbol_fmt 把「基础资产 + 计价资产」映射成该所的交易对写法。
VENUES = {
    "lbank": {
        "host": "api.lbank.info",
        "port": 443,
        "path": "/ws/V2/",
        "mode": "subscribe",
        # 官方文档：{"action":"subscribe","subscribe":"trade","pair":"btc_usdt"}
        "subscribe": {"action": "subscribe", "subscribe": "trade", "pair": "btc_usdt"},
        "symbol_fmt": "{base}_{quote}",      # 小写（见 symbol_case）
        "symbol_case": "lower",
        "channel": "trade",
        "subscribe_batch_size": 1,
        "subscribe_notes": "公开订阅报文以单 pair 为单位；N 个 pair 在同一连接上顺序发 N 条报文"
                           "（本实现不假设存在逗号批量写法）。每连接订阅上限未复核。",
        "app_ping_field": "ping",
        "active_ping_interval": None,
        "notes": "CCXT pro_lbank.py 用的是 wss://www.lbkex.net/ws/V2/（另一域名）；"
                 "若要复现 CCXT 现场，请 --host www.lbkex.net --path /ws/V2/。"
                 "服务端主动发应用层 ping，客户端回 pong 即可，无需主动心跳。",
    },
    "binance": {
        "host": "stream.binance.com",
        "port": 9443,
        "path": "/ws/btcusdt@trade",
        "path_multi": "/ws",            # 多 stream 时用 SUBSCRIBE 报文，path 用 /ws
        "mode": "path",                 # 单 stream 时订阅信息编在 path 里，无需发报文
        "subscribe": None,
        "symbol_fmt": "{base}{quote}",   # 小写 → btcusdt
        "symbol_case": "lower",
        "channel": "trade",              # stream 名 = <symbol>@trade
        "subscribe_batch_size": 1024,
        "subscribe_notes": "批量法 {\"method\":\"SUBSCRIBE\",\"params\":[\"btcusdt@trade\",...],\"id\":1}；"
                           "公开文档称单连接最多 1024 个 stream（本实现按 1024 分块，仍用同一连接）。",
        "app_ping_field": None,
        "active_ping_interval": None,    # 服务端每 ~20s 发 RFC6455 ping，回 pong 即可
        "notes": "Binance 原始成交流（非 aggTrade），与 LBank trade 语义最接近；"
                 "对照可用 /ws/btcusdt@aggTrade 看聚合通道的差别",
    },
    "bybit": {
        "host": "stream.bybit.com",
        "port": 443,
        "path": "/v5/public/spot",
        "mode": "subscribe",
        "subscribe": {"op": "subscribe", "args": ["publicTrade.BTCUSDT"]},
        "symbol_fmt": "{base}{quote}",   # 大写 → BTCUSDT
        "symbol_case": "upper",
        "channel": "publicTrade",
        "subscribe_batch_size": 10,
        "subscribe_notes": "v5 单条 subscribe 报文可带多个 args；上限取保守值 10/报文"
                           "（官方上限未在本轮联网复核，取小不取大）。",
        "app_ping_field": None,     # Bybit 用 {"op":"ping"}；服务端**不主动**发
        "active_ping_interval": 15,  # 客户端须每 <20s 主动发 {"op":"ping"}，否则被断连（V-09）
        "notes": "Bybit v5 公开现货成交流。注意：v5 要求**客户端主动**心跳（服务端不主动发 ping，"
                 "约 20 秒无包的连接会被断开）；本脚本 15 秒发一次 {\"op\":\"ping\"}，"
                 "服务端回的 {\"op\":\"pong\"} 计进 heartbeat_pongs_received，不计业务消息。",
    },
}


# ---------------------------------------------------------------- 扩展协商解析（D1 修复核心）
def split_extension_list(values):
    """把若干条 `Sec-WebSocket-Extensions` 头值拆成候选字符串。

    RFC 6455 §9.1：header 值 = 1#extension，extension = token *(";" param)，
    多个扩展用逗号分隔（扩展名之间是顶层逗号）。带引号的参数按 RFC 7230 处理最小集。
    """
    parts = []
    for v in values:
        cur = []
        in_q = False
        for ch in v:
            if ch == '"':
                in_q = not in_q
                cur.append(ch)
            elif ch == "," and not in_q:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def parse_extension_header(values):
    """解析 `Sec-WebSocket-Extensions` 头（可多条）→ [(name_lower, params_dict), ...]。

    params_dict：参数名（小写）→ 值字符串；**无值参数**（如 `server_no_context_takeover`）值为 None。
    """
    out = []
    for cand in split_extension_list(values):
        bits = [b.strip() for b in cand.split(";")]
        if not bits or not bits[0]:
            continue
        name = bits[0].lower()
        params = {}
        for b in bits[1:]:
            if not b:
                continue
            if "=" in b:
                k, _, v = b.partition("=")
                params[k.strip().lower()] = v.strip().strip('"')
            else:
                params[b.lower()] = None
        out.append((name, params))
    return out


def find_permessage_deflate(parsed_exts):
    """在解析结果里**按 token 精确匹配** permessage-deflate。

    返回 params dict（可能为空）或 None。注意：不做子串匹配 ——
    `x-webkit-deflate-frame` / `permessage-deflatex` 一律不算（v1.1 的 bug 就在这里）。
    """
    for name, params in parsed_exts:
        if name == "permessage-deflate":
            return params
    return None


def deflate_status(offered, accepted, raw_values):
    """把「我们有没有 offer」与「服务端有没有接受」明确分开（D1 修复目标）。"""
    if offered and accepted:
        return "accepted"
    if offered and not accepted:
        return "server_refused"
    if not offered and accepted:
        return "unsolicited"
    if not offered and raw_values:
        return "not_offered_server_sent_other_extension"
    return "not_offered"


# ---------------------------------------------------------------- WS 线级协议
def _client_frame(opcode: int, payload: bytes, rsv1: bool = False) -> bytes:
    """构造一个带掩码的客户端帧（RFC 6455）。"""
    head = bytes([(0x80 if opcode != 0x0 else 0x00) | (0x40 if rsv1 else 0x00) | opcode])
    mask = os.urandom(4)
    n = len(payload)
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class WSReader:
    """最小服务端帧读取器：支持 文本/二进制/PING/PONG/CLOSE、以及 permessage-deflate。

    统计口径（v1.2）：
      * 业务指标（payload_bytes / wire_bytes / sizes / msg_types）**只统计业务帧**，
        由调用方在归类为业务消息后调用 `record_business()` 写入。
      * 应用层心跳帧（LBank `{"action":"ping"}`、Bybit `{"op":"ping"}`/`{"op":"pong"}`）
        计入 `app_ping_frames` / `app_ping_payload_bytes` / `app_ping_wire_bytes`。
      * 订阅回执计入 `ack_frames` / `ack_wire_bytes`（v1.2）。
      * RFC6455 控制帧计入 `frames_control` / `control_wire_bytes`（自动回 pong）。

    压缩（v1.2，D1b）：`deflate_params` 来自握手协商；`server_no_context_takeover`
      时每消息用**新 inflater**；`server_max_window_bits=N` 时 inflater 窗口取 N。
      解压失败**不再静默**，计入 `inflate_failures` 并保留原（压缩）字节。

    已知缺口（未实现，不得当作已处理）：**分片帧不重组** —— 见模块头 §4。
    """

    def __init__(self, sock, prebuf: bytes = b"", deflate_params=None):
        self.sock = sock
        self.buf = prebuf
        self.pos = 0
        self.deflate_params = deflate_params   # None = 未协商压缩
        self.frames_control = 0
        self.control_wire_bytes = 0
        # 业务指标
        self.payload_bytes = 0
        self.wire_bytes = 0
        self.sizes = []
        self.msg_types = {}
        self.symbol_msg_counts = {}
        self.first_business_msg_at = None
        # 应用层心跳 / 回执（单列，不进业务指标）
        self.app_ping_frames = 0
        self.app_ping_payload_bytes = 0
        self.app_ping_wire_bytes = 0
        self.ack_frames = 0
        self.ack_wire_bytes = 0
        # 压缩统计
        self.compressed_frames = 0
        self.inflate_failures = 0
        self._window = -15
        self._no_context_takeover = False
        if deflate_params is not None:
            self._no_context_takeover = ("server_no_context_takeover" in deflate_params)
            smw = deflate_params.get("server_max_window_bits")
            if smw:
                try:
                    w = int(smw)
                    if 8 <= w <= 15:
                        self._window = -w
                except ValueError:
                    pass
        self._inflater = self._new_inflater() if deflate_params is not None else None

    def _new_inflater(self):
        return zlib.decompressobj(self._window)

    def _inflate(self, payload: bytes):
        """解压一帧的负载。返回 (payload, ok)。"""
        try:
            out = self._inflater.decompress(payload + b"\x00\x00\xff\xff")
        except zlib.error:
            self.inflate_failures += 1
            if self._no_context_takeover:
                self._inflater = self._new_inflater()
            return payload, False
        if self._no_context_takeover:
            self._inflater = self._new_inflater()
        return out, True

    def _ensure(self, k: int, allow_idle: bool = False) -> bool:
        """确保缓冲区至少有 k 字节可读。

        allow_idle=True 时，若**帧边界**读超时（缓冲区空），返回 False 而不抛异常 ——
        这让调用方能在无入站消息时执行「主动心跳 / 到时退出」逻辑（v1.1，Bybit 必需）。
        """
        while len(self.buf) - self.pos < k:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                if allow_idle:
                    return False
                raise
            if not chunk:
                raise EOFError("socket closed")
            self.buf += chunk
        return True

    def _maybe_compact(self):
        if self.pos > 1 << 20:
            self.buf = self.buf[self.pos:]
            self.pos = 0

    def record_business(self, payload: bytes, wire: int, symbol=None):
        """把一帧登记为**业务消息**（计入全部业务指标）。"""
        self.payload_bytes += len(payload)
        self.wire_bytes += wire
        self.sizes.append(len(payload))
        if symbol:
            self.symbol_msg_counts[symbol] = self.symbol_msg_counts.get(symbol, 0) + 1
        if self.first_business_msg_at is None:
            self.first_business_msg_at = time.time()
        self._maybe_compact()

    def record_app_ping(self, payload: bytes, wire: int):
        """把一帧登记为**应用层心跳**（单列计数，不进业务指标）。"""
        self.app_ping_frames += 1
        self.app_ping_payload_bytes += len(payload)
        self.app_ping_wire_bytes += wire
        self._maybe_compact()

    def record_ack(self, payload: bytes, wire: int):
        """把一帧登记为**订阅回执**（单列计数，不进业务指标，v1.2）。"""
        self.ack_frames += 1
        self.ack_wire_bytes += wire
        self._maybe_compact()

    def wire_bytes_total(self) -> int:
        """线级总字节 = 业务 + 应用层心跳 + 订阅回执 + RFC6455 控制帧（均含帧头）。"""
        return (self.wire_bytes + self.app_ping_wire_bytes
                + self.ack_wire_bytes + self.control_wire_bytes)

    def read_frame(self):
        """读一帧。

        返回：
          ("data",    opcode, payload, wire)  —— 业务/文本/二进制帧（尚未归类）
          ("control",)                        —— RFC6455 控制帧（已内部回 pong / 处理）
          ("idle",)                           —— 读超时且帧边界无数据（调用方可发心跳或判到时）
        抛出：
          EOFError             —— 对端关闭连接，或收到 close 帧
          socket.timeout       —— 帧中途读超时（异常状态，交给上层记录）
        """
        if not self._ensure(2, allow_idle=True):
            return ("idle",)
        h2 = self._need(2)
        b0, b1 = h2[0], h2[1]
        opcode = b0 & 0x0F
        rsv1 = bool(b0 & 0x40)
        masked = bool(b1 & 0x80)
        ln = b1 & 0x7F
        header_len = 2
        if ln == 126:
            ln = struct.unpack(">H", self._need(2))[0]
            header_len += 2
        elif ln == 127:
            ln = struct.unpack(">Q", self._need(8))[0]
            header_len += 8
        mask = self._need(4) if masked else b""
        if masked:
            header_len += 4
        payload = self._need(ln) if ln else b""
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

        wire = header_len + ln
        if opcode in (0x9, 0xA, 0x8):       # ping / pong / close
            self.frames_control += 1
            self.control_wire_bytes += wire
            if opcode == 0x9:               # RFC6455 层 ping，必须回 pong
                self.sock.sendall(_client_frame(0xA, payload))
            if opcode == 0x8:
                raise EOFError("server sent close frame")
            return ("control",)

        if rsv1 and self._inflater is not None:     # permessage-deflate（服务端→我们）
            self.compressed_frames += 1
            payload, _ok = self._inflate(payload)

        return ("data", opcode, payload, wire)

    def _need(self, k: int) -> bytes:
        """帧内读取：读超时视为异常（不允许 idle），保证帧状态不被破坏。"""
        self._ensure(k, allow_idle=False)
        out = self.buf[self.pos:self.pos + k]
        self.pos += k
        return out


# ---------------------------------------------------------------- 交易对与订阅报文
def format_symbol(venue: str, base: str, quote: str) -> str:
    cfg = VENUES[venue]
    s = cfg["symbol_fmt"].format(base=base, quote=quote)
    return s.lower() if cfg["symbol_case"] == "lower" else s.upper()


def resolve_symbols(venue: str, args) -> list:
    """决定本场次的交易对列表。

    优先顺序：--raw-symbols（venue 原生写法）> --symbols-file > --symbols > 内置单对。
    --symbols 也接受**纯整数**（= 用内置样表取前 N 个，N 超过内置表长度则报错并提示用 --symbols-file）。
    """
    cfg = VENUES[venue]
    quote = args.quote
    if args.raw_symbols:
        syms = [s.strip() for s in args.raw_symbols.split(",") if s.strip()]
        return syms, {"source": "raw-symbols", "note": "调用方直接给出的 venue 原生交易对，未做格式转换"}
    if args.symbols_file:
        raw = open(args.symbols_file, "r", encoding="utf-8").read()
        txt = raw.strip()
        assets, per_venue = None, None
        if txt.startswith("{") or txt.startswith("["):
            data = json.loads(txt)
            if isinstance(data, list):
                assets = [str(x) for x in data]
            elif isinstance(data, dict):
                if venue in data and isinstance(data[venue], list):
                    per_venue = [str(x) for x in data[venue]]
                else:
                    assets = [str(x) for x in data.get("assets", [])]
            else:
                raise SystemExit(f"--symbols-file JSON 形态不支持: {type(data).__name__}")
        else:
            assets = [ln.split("#")[0].strip() for ln in txt.splitlines()]
            assets = [a for a in assets if a]
        if per_venue is not None:
            return per_venue, {"source": args.symbols_file,
                               "note": f"按 venue='{venue}' 键取原生交易对（未转换）"}
        return [format_symbol(venue, a, quote) for a in assets], {
            "source": args.symbols_file, "quote": quote, "assets_count": len(assets)}
    if args.symbols:
        if re.fullmatch(r"\d+", args.symbols.strip()):
            n = int(args.symbols.strip())
            if n > len(DEFAULT_SAMPLE_ASSETS):
                raise SystemExit(
                    f"--symbols {n} 超过内置样表长度 {len(DEFAULT_SAMPLE_ASSETS)}；"
                    "请用 --symbols-file 提供完整名单（内置样表只是冒烟测试用）")
            assets = DEFAULT_SAMPLE_ASSETS[:n]
            return [format_symbol(venue, a, quote) for a in assets], {
                "source": "builtin-sample", "quote": quote, "assets_count": len(assets),
                "note": "内置样表仅供冒烟；159 对规模请用 --symbols-file"}
        assets = [s.strip() for s in args.symbols.split(",") if s.strip()]
        return [format_symbol(venue, a, quote) for a in assets], {
            "source": "inline", "quote": quote, "assets_count": len(assets)}
    # 默认：向后兼容 v1.1 的单 pair 行为
    return [format_symbol(venue, "BTC", quote)], {"source": "default-single-pair", "quote": quote}


def build_subscribe_messages(venue: str, symbols: list):
    """按各所公开协议构造订阅报文列表（同一连接上顺序发送，不拆连接）。

    返回 (messages: list[dict], meta: dict)。
    Binance 单 stream 且只有 1 个交易对时可走 path 模式（不发报文）→ 返回 ([], meta)，
    由调用方按 cfg['mode'] 决定是否发报文。
    """
    cfg = VENUES[venue]
    bs = max(1, int(cfg.get("subscribe_batch_size") or 1))
    chunks = [symbols[i:i + bs] for i in range(0, len(symbols), bs)] or [[]]
    msgs = []
    if venue == "lbank":
        for ch in chunks:
            for s in ch:
                msgs.append({"action": "subscribe", "subscribe": cfg["channel"], "pair": s})
    elif venue == "binance":
        for i, ch in enumerate(chunks):
            msgs.append({"method": "SUBSCRIBE",
                         "params": [f"{s}@{cfg['channel']}" for s in ch],
                         "id": i + 1})
    elif venue == "bybit":
        for ch in chunks:
            msgs.append({"op": "subscribe",
                         "args": [f"{cfg['channel']}.{s}" for s in ch]})
    else:  # pragma: no cover
        raise SystemExit(f"unknown venue {venue}")
    return msgs, {
        "batch_size": bs,
        "messages_planned": len(msgs),
        "batch_capability": ("批量（单报文多对）" if bs > 1 else "单对（每报文一对）"),
        "notes": cfg.get("subscribe_notes"),
    }


def extract_symbol(j):
    """从业务消息里尽力提取交易对（用于 symbol_msg_counts，纯统计用）。"""
    if not isinstance(j, dict):
        return None
    for k in ("pair", "s", "symbol"):
        v = j.get(k)
        if isinstance(v, str) and v:
            return v
    t = j.get("topic")
    if isinstance(t, str) and t:
        return t.rsplit(".", 1)[-1] or None
    d = j.get("data")
    if isinstance(d, list) and d and isinstance(d[0], dict):
        for k in ("s", "symbol"):
            v = d[0].get(k)
            if isinstance(v, str) and v:
                return v
    return None


# ---------------------------------------------------------------- 连接与握手
def _parse_headers(head: bytes):
    lines = head.split(b"\r\n")
    status = lines[0].decode(errors="replace") if lines else ""
    headers = {}
    order = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        name, _, val = ln.partition(b":")
        k = name.decode(errors="replace").strip().lower()
        v = val.decode(errors="replace").strip()
        order.append(k)
        if k in headers:                    # 同名头出现多次：按 RFC 7230 合并为逗号分隔
            headers[k] = headers[k] + ", " + v
        else:
            headers[k] = v
    return status, headers, order


def _open_socket(cfg, proxy):
    host, port = cfg["host"], cfg["port"]
    res = {}
    if proxy:
        scheme = proxy.split("://", 1)[0].lower() if "://" in proxy else "http"
        if scheme not in ("http", "https"):
            raise RuntimeError(
                f"proxy scheme '{scheme}' unsupported: 本脚本只实现 HTTP CONNECT，"
                "socks5 请改用 Clash 的混合端口（HTTP 兼容口）")
        m = re.search(r"([\w.\-]+):(\d+)", proxy.split("://", 1)[-1])
        ph, pp = (m.group(1), int(m.group(2))) if m else ("127.0.0.1", 7890)
        raw = socket.create_connection((ph, pp), timeout=20)
        raw.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
        resp = raw.recv(4096)
        res["proxy_connect_status"] = resp.split(b"\r\n")[0].decode(errors="replace")
        if b"200" not in resp.split(b"\r\n")[0]:
            raise RuntimeError("proxy CONNECT failed: " + res["proxy_connect_status"])
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(raw, server_hostname=host)
    else:
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(socket.create_connection((host, port), timeout=20),
                               server_hostname=host)
    return sock, res


def do_handshake(sock, cfg, offer_header=None):
    """发握手请求并读响应。返回 (rest_bytes, info_dict)。

    `offer_header`：要放进 `Sec-WebSocket-Extensions` 的**原文**（None = 不 offer）。
    info 里把「我们 offer 了什么」与「服务端回了什么」分开记（D1）。
    """
    host, path = cfg["host"], cfg["path"]
    key = base64.b64encode(os.urandom(16)).decode()
    hdrs = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        "User-Agent: Mozilla/5.0 (compatible; ws-wire-audit/1.3)",
    ]
    if offer_header:
        hdrs.append(f"Sec-WebSocket-Extensions: {offer_header}")
    sock.sendall(("\r\n".join(hdrs) + "\r\n\r\n").encode())

    buf = b""
    while b"\r\n\r\n" not in buf:
        c = sock.recv(4096)
        if not c:
            raise EOFError("closed during handshake")
        buf += c
    head, _, rest = buf.partition(b"\r\n\r\n")
    status, headers, order = _parse_headers(head)

    raw_ext = [v.strip() for k, v in headers.items()
               if k == "sec-websocket-extensions" and v.strip()]
    parsed = parse_extension_header(raw_ext)
    dparams = find_permessage_deflate(parsed)

    expected = base64.b64encode(hashlib.sha1(
        (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    info = {
        "http_status": status,
        "handshake_headers": [f"{k}: {headers[k]}" for k in order],
        "sec_websocket_accept": headers.get("sec-websocket-accept"),
        "sec_websocket_accept_valid": (headers.get("sec-websocket-accept") == expected),
        "deflate_offered": bool(offer_header),
        "deflate_offer_header": offer_header,
        "deflate_response_header": headers.get("sec-websocket-extensions"),
        "deflate_response_raw_values": raw_ext,
        "deflate_extensions_parsed": [[n, p] for n, p in parsed],
        "deflate_accepted": dparams is not None,
        "deflate_params": dparams,
        "deflate_status": deflate_status(bool(offer_header), dparams is not None, raw_ext),
        # 兼容 v1.1 字段名（判读脚本可能仍在读它）
        "negotiated_permessage_deflate": headers.get("sec-websocket-extensions"),
    }
    return rest, info


# ---------------------------------------------------------------- 场次
def run_session(venue: str, seconds: int, host=None, path=None, offer_headers=None,
                symbols=None, symbol_meta=None, proxy=None, subscribe_interval=0.05,
                probe_only=False, verbose=False):
    """跑一个场次。

    offer_headers: 要尝试的 `Sec-WebSocket-Extensions` 原文列表。
      * 空/None            → 不 offer
      * 1 条               → 在本次测量握手里 offer 它（v1.1 行为）
      * ≥2 条（ladder）    → 先逐个 offer 做**探测握手**（不订阅、不采集、立即关闭），
                             再用第一个被接受的 offer 跑测量；全被拒则以「不 offer」跑测量。
    probe_only=True 时只做握手探测并返回（供 ladder 用）。
    """
    cfg = dict(VENUES[venue])
    if host:
        cfg["host"] = host
    if path:
        cfg["path"] = path
    offers = list(offer_headers or [])
    if len(offers) > 1 and cfg.get("path_multi") and symbols:
        pass  # path 在多 stream 时由下方统一处理

    res = {
        "venue": venue,
        "script_version": SCRIPT_VERSION,
        "ws_url": f"wss://{cfg['host']}:{cfg['port']}{cfg['path']}",
        "requested_seconds": seconds,
        "proxy": proxy or "direct",
        "symbols_requested": list(symbols or []),
        "symbols_count": len(symbols or []),
        "symbol_meta": symbol_meta or {},
        # D1：offered / accepted 分开记
        "deflate_offered": False,
        "deflate_accepted": False,
        "deflate_status": None,
        "deflate_offer_header": None,
        "deflate_response_header": None,
        "negotiated_permessage_deflate": None,   # v1.1 兼容字段
        "deflate_probe": [],
        # v1.3 新增：测量会话自身 offer 的来源（none|single-offer|ladder-accepted|ladder-fallback-first-offer）
        "deflate_measurement_offer_source": None,
        "deflate_probe_statuses": [],
        "deflate_probe_all_refused": None,
        "http_status": None,
        "sec_websocket_accept": None,
        "sec_websocket_accept_valid": None,      # v1.1：握手校验（只记录，不中断）
        "reconnects": 0,                          # 本会话不做重连，恒为 0（异常会记录在 error）
        "collection_complete": False,             # v1.1：异常中断时为 false，但已采数据仍会落盘
        "error": None,
    }

    t_start = time.time()
    reader = None
    t_subscribed = None
    probe = None
    app_pings_sent = 0         # 我们对入站 app-ping 回的 pong（LBank）
    app_pongs_sent = 0         # 我们对入站 op=ping 回的 pong（Bybit 兼容分支）
    heartbeat_pings_sent = 0   # 我们**主动**发的心跳（Bybit v5 必需，v1.1 修 V-09）
    heartbeat_pongs_received = 0  # 心跳回应（Bybit 回 {"op":"pong"}）
    subscribe_messages_sent = 0
    subscribe_errors = []

    def finalize():
        """把 reader 当前的统计写进 res。

        v1.1（修 V-09）：成功路径与异常路径**共用**本函数，异常时不再丢弃已采集数据。
        v1.2：新增 symbols_count / wire_bytes_total / deflate_* / subscribe_* / 压缩失败计数。
        """
        if reader is None:
            return
        elapsed = (time.time() - t_subscribed) if t_subscribed else 0.0
        n = len(reader.sizes)
        sizes = sorted(reader.sizes)
        total = reader.wire_bytes_total()
        res.update({
            "elapsed_s": round(elapsed, 3),
            "business_messages": n,
            "control_frames": reader.frames_control,
            "app_ping_frames": reader.app_ping_frames,
            "app_ping_payload_bytes": reader.app_ping_payload_bytes,
            "app_ping_wire_bytes": reader.app_ping_wire_bytes,
            "subscribe_acks": reader.ack_frames,
            "subscribe_ack_wire_bytes": reader.ack_wire_bytes,
            "subscribe_messages_sent": subscribe_messages_sent,
            "subscribe_errors": subscribe_errors,
            "app_pings_sent": app_pings_sent,
            "app_pongs_sent": app_pongs_sent,
            "heartbeat_pings_sent": heartbeat_pings_sent,
            "heartbeat_pongs_received": heartbeat_pongs_received,
            "payload_bytes": reader.payload_bytes,
            "wire_bytes": reader.wire_bytes,
            "wire_bytes_total": total,                      # v1.2：含心跳/回执/控制帧
            "control_wire_bytes": reader.control_wire_bytes,
            "compressed_frames": reader.compressed_frames,
            "inflate_failures": reader.inflate_failures,
            "msg_per_s": round(n / elapsed, 3) if elapsed else None,
            "payload_bytes_per_s": round(reader.payload_bytes / elapsed, 1) if elapsed else None,
            "wire_bytes_per_s": round(reader.wire_bytes / elapsed, 1) if elapsed else None,
            "wire_bytes_total_per_s": round(total / elapsed, 1) if elapsed else None,
            "msg_types": reader.msg_types,
            "symbol_msg_counts": dict(sorted(reader.symbol_msg_counts.items(),
                                             key=lambda kv: -kv[1])),
            "symbols_seen": len(reader.symbol_msg_counts),
            "size_bytes": {
                "min": sizes[0] if sizes else None,
                "p50": sizes[n // 2] if sizes else None,
                "p90": sizes[int(n * 0.9)] if sizes else None,
                "p99": sizes[int(n * 0.99)] if sizes else None,
                "max": sizes[-1] if sizes else None,
                "mean": round(statistics.fmean(sizes), 1) if sizes else None,
            },
            "first_msg_latency_ms": (round((reader.first_business_msg_at - t_subscribed) * 1000, 1)
                                     if reader.first_business_msg_at else None),
        })
        res["collection_complete"] = res.get("error") is None

    try:
        # ---- 压缩 offer 决策（v1.3 修 D3：**测量会话本身**必须 offer）----
        # v1.2 缺陷：ladder 时若探测全部被拒 → 测量会话 offer=None → 输出 deflate_offered=False
        #            （与「用户根本没开 --deflate」在下游判读里无法区分）。
        # v1.3：只要用户要了压缩（offers 非空），**测量会话一定带 offer**：
        #   - 单 offer（--deflate / --deflate-offer）→ 直接用该 offer；
        #   - ladder：逐变体探测；有被接受的用被接受的那个；全被拒则用 offers[0]（变体原文见
        #     deflate_offer_header）→ 测量会话得到 server_refused，即「服务端拒绝」由测量会话自证。
        offer, offer_source = None, "none"
        if len(offers) == 1:
            offer, offer_source = offers[0], "single-offer"
        elif len(offers) > 1:
            accepted_offer = None
            for o in offers:
                try:
                    psock, _pinfo = _open_socket(cfg, proxy)
                    try:
                        _prest, pinfo = do_handshake(psock, cfg, offer_header=o)
                    finally:
                        try:
                            psock.close()
                        except Exception:
                            pass
                except Exception as e:
                    pinfo = {"deflate_offer_header": o,
                             "deflate_status": "probe_error",
                             "probe_error": f"{type(e).__name__}: {e}"}
                res["deflate_probe"].append(pinfo)
                if pinfo.get("deflate_accepted"):
                    accepted_offer = o
                    break
            if accepted_offer is not None:
                offer, offer_source = accepted_offer, "ladder-accepted"
            else:
                offer, offer_source = offers[0], "ladder-fallback-first-offer"
        res["deflate_measurement_offer_source"] = offer_source
        res["deflate_probe_statuses"] = [
            {"offer": p.get("deflate_offer_header"), "status": p.get("deflate_status")}
            for p in res["deflate_probe"]]
        res["deflate_probe_all_refused"] = bool(res["deflate_probe"]) and all(
            not p.get("deflate_accepted") for p in res["deflate_probe"])

        sock, sinfo = _open_socket(cfg, proxy)
        rest, info = do_handshake(sock, cfg, offer_header=offer)
        res.update(info)
        res.update(sinfo)
        res["deflate_offer_header"] = offer

        if probe_only:
            try:
                sock.close()
            except Exception:
                pass
            res["collection_complete"] = True
            return res

        inflate_params = info["deflate_params"] if info["deflate_accepted"] else None
        reader = WSReader(sock, rest, deflate_params=inflate_params)

        # ---- 订阅（多交易对：同一连接上发 N 条/分块报文，不拆连接）----
        syms = list(symbols or [])
        if cfg["mode"] == "path" and len(syms) <= 1:
            # 单 stream：订阅信息编在 path 里，无需发报文（v1.1 行为）
            res["subscribe_mode"] = "path"
            res["subscribe_plan"] = {"batch_size": 1, "messages_planned": 0,
                                     "batch_capability": "path 写法（单 stream）"}
        else:
            if cfg["mode"] == "path" and cfg.get("path_multi"):
                res["subscribe_mode"] = "path_multi+SUBSCRIBE"
            else:
                res["subscribe_mode"] = "subscribe"
            msgs, plan = build_subscribe_messages(venue, syms)
            if cfg.get("path_multi") and venue == "binance":
                res["subscribe_note"] = (f"多 stream 使用 path {cfg['path_multi']} + SUBSCRIBE 报文；"
                                         "订阅前请回官方文档复核 stream 上限（本实现按 1024 分块）")
            # 若调用方用 --path 覆盖过，则不改 path（尊重人工覆盖）
            res["subscribe_plan"] = plan
            for msg in msgs:
                sock.sendall(_client_frame(0x1, json.dumps(msg).encode()))
                subscribe_messages_sent += 1
                if subscribe_interval:
                    time.sleep(subscribe_interval)
        t_subscribed = time.time()
        last_send = time.time()

        # ---- 采集 ----
        # 1 秒短超时 + 帧边界 idle 判定：这样空闲时才能发主动心跳（Bybit v5 必需）
        end = t_subscribed + seconds
        sock.settimeout(1.0)
        while time.time() < end:
            ev = reader.read_frame()
            if ev[0] == "idle":
                iv = cfg.get("active_ping_interval")
                if iv and (time.time() - last_send) >= iv:
                    sock.sendall(_client_frame(0x1, json.dumps({"op": "ping"}).encode()))
                    last_send = time.time()
                    heartbeat_pings_sent += 1
                continue
            if ev[0] == "control":
                continue
            _, opcode, payload, wire = ev
            try:
                j = json.loads(payload.decode("utf-8", "replace"))
            except Exception:
                j = None
            # LBank 应用层 ping：必须回 pong，否则服务端 1 分钟内断连（官方文档原文）
            # 该帧是心跳，不是业务数据 → 单独计数，不进业务指标（v1.1 修 V-10①）
            if isinstance(j, dict) and cfg["app_ping_field"] and j.get("action") == "ping":
                pid = j.get(cfg["app_ping_field"])
                sock.sendall(_client_frame(0x1, json.dumps({"action": "pong", "pong": pid}).encode()))
                app_pings_sent += 1
                last_send = time.time()
                reader.record_app_ping(payload, wire)
                continue
            # Bybit：若服务端仍发 op=ping（v5 公开流不主动发，保留兼容分支）
            if isinstance(j, dict) and j.get("op") == "ping":
                sock.sendall(_client_frame(0x1, json.dumps({"op": "pong"}).encode()))
                app_pongs_sent += 1
                last_send = time.time()
                reader.record_app_ping(payload, wire)
                continue
            # Bybit：对我们主动心跳的回应（{"op":"pong"}）同样不是业务数据
            if isinstance(j, dict) and j.get("op") == "pong":
                heartbeat_pongs_received += 1
                reader.record_app_ping(payload, wire)
                continue
            # 订阅回执（v1.2）：不算业务数据；success=false 另记（多交易对场景的关键信号）
            if isinstance(j, dict) and (
                    set(j.keys()) <= {"result", "id"}
                    or (j.get("op") == "subscribe" and "success" in j)):
                reader.record_ack(payload, wire)
                if j.get("success") is False:
                    if len(subscribe_errors) < 50:
                        subscribe_errors.append(payload.decode("utf-8", "replace"))
                continue
            # 业务消息：按 type/op/e/topic 归类
            if isinstance(j, dict):
                key = j.get("type") or j.get("op") or j.get("e") or j.get("topic") or "?"
                if "pair" in j and key == "?":
                    key = "?"
            else:
                key = "non-json"
            reader.record_business(payload, wire, symbol=extract_symbol(j))
            reader.msg_types[key] = reader.msg_types.get(key, 0) + 1

        try:
            sock.close()
        except Exception:
            pass
    except Exception as e:
        # v1.1（修 V-09）：异常路径**不丢**已采集统计 —— 由 finally 的 finalize() 落盘
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        finalize()
        res["wall_clock_s"] = round(time.time() - t_start, 3)
    return res


# ---------------------------------------------------------------- 离线自测（零网络）
def _selftest():
    """离线断言（零网络）：用**伪造的握手响应/帧字节流**验证协商解析与计数口径。

    本函数不建立任何真实连接。
    """
    import types  # noqa
    fails = []

    def check(label, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  <- {detail}" if detail else ""))
        if not cond:
            fails.append(label)

    print("T1 扩展解析：permessage-deflate 被正确接受（含参数）")
    parsed = parse_extension_header(["permessage-deflate; server_max_window_bits=15; client_no_context_takeover"])
    p = find_permessage_deflate(parsed)
    check("T1a 解析出 permessage-deflate", p is not None, repr(parsed))
    check("T1b 参数 server_max_window_bits=15", (p or {}).get("server_max_window_bits") == "15")
    check("T1c 无值参数 client_no_context_takeover 记为 None",
          "client_no_context_takeover" in (p or {}) and (p or {}).get("client_no_context_takeover") is None)
    check("T1d status=accepted", deflate_status(True, p is not None, ["permessage-deflate"]) == "accepted")

    print("T2 假阳性回归（v1.1 缺陷 D1）：其他扩展不得被当成压缩接受")
    parsed2 = parse_extension_header(["x-webkit-deflate-frame", "permessage-deflatex"])
    check("T2a x-webkit-deflate-frame 不匹配", find_permessage_deflate(parsed2) is None, repr(parsed2))
    check("T2b status=server_refused", deflate_status(True, False, ["x-webkit-deflate-frame"]) == "server_refused")
    check("T2c 大小写不敏感（PerMessage-Deflate 仍匹配）",
          find_permessage_deflate(parse_extension_header(["PerMessage-Deflate"])) is not None)

    print("T3 「我们没 offer」与「服务端拒绝」可区分（D1 的核心目标）")
    check("T3a not_offered", deflate_status(False, False, []) == "not_offered")
    check("T3b server_refused", deflate_status(True, False, []) == "server_refused")
    check("T3c unsolicited（未 offer 但服务端回）",
          deflate_status(False, True, ["permessage-deflate"]) == "unsolicited")

    print("T4 伪造握手响应（多条扩展头 + 帧流）驱动 run_session")
    # 伪造 socket/ssl，让 run_session 全程离线；只验证解析与计数，不发任何真实请求
    def mkframe(op, payload, rsv1=False):
        n = len(payload)
        h = bytes([(0x80 | (0x40 if rsv1 else 0x00)) | op])
        if n < 126:
            h += bytes([n])
        elif n < 65536:
            h += bytes([126]) + struct.pack(">H", n)
        else:
            h += bytes([127]) + struct.pack(">Q", n)
        return h + payload

    def deflate_indep(msg):     # 每消息独立压缩（server_no_context_takeover 场景）
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        return (c.compress(msg) + c.flush(zlib.Z_SYNC_FLUSH))[:-4]

    class FakeSock:
        def __init__(s, data):
            s.data, s.i, s.sent = data, 0, []

        def recv(s, n):
            if s.i >= len(s.data):
                raise socket.timeout("idle")
            c = s.data[s.i:s.i + n]
            s.i += len(c)
            return c

        def sendall(s, b):
            s.sent.append(b)

        def settimeout(s, t):
            pass

        def close(s):
            pass

    class FakeCtx:
        def __init__(s, data):
            s.data = data

        def wrap_socket(s, sk, **kw):
            return FakeSock(s.data)

    def run_fake(resp_bytes, offer, label, venue="binance", seconds=1, symbols=None):
        orig_cc, orig_ctx = socket.create_connection, ssl.create_default_context
        socket.create_connection = lambda *a, **k: object()
        ssl.create_default_context = lambda *a, **k: FakeCtx(resp_bytes)
        try:
            return run_session(venue, seconds, offer_headers=([offer] if offer else []),
                               symbols=symbols, subscribe_interval=0)
        finally:
            socket.create_connection, ssl.create_default_context = orig_cc, orig_ctx

    def hdr(*extra):
        return ("\r\n".join(["HTTP/1.1 101 Switching Protocols", "Upgrade: websocket",
                             "Sec-WebSocket-Accept: not-checked"] + list(extra)) + "\r\n\r\n").encode()

    # T4a：未 offer → 即使服务端回别的扩展，也必须是 not_offered 且 inflate 关闭
    body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
    r = run_fake(hdr("Sec-WebSocket-Extensions: x-webkit-deflate-frame") + body, None, "no-offer")
    check("T4a 未 offer 时 status=not_offered_server_sent_other_extension",
          r["deflate_status"] == "not_offered_server_sent_other_extension", str(r["deflate_status"]))
    check("T4a 未 offer 时 deflate_accepted=False 且未压缩计数=0",
          r["deflate_accepted"] is False and r.get("compressed_frames") == 0,
          f"accepted={r['deflate_accepted']}")
    check("T4a 业务消息仍被统计（1 条，16B 以上）", r["business_messages"] == 1, str(r["business_messages"]))
    check("T4a 新字段 wire_bytes_total 存在且>=wire_bytes",
          isinstance(r.get("wire_bytes_total"), int) and r["wire_bytes_total"] >= r["wire_bytes"])

    # T4b：offer + 服务端回 permessage-deflate（带 server_no_context_takeover）→ 两条**独立压缩**消息都要解对
    mA = b'{"e":"trade","s":"BTCUSDT","q":"1"}'
    mB = b'{"e":"trade","s":"ETHUSDT","q":"2"}'
    import zlib as _z
    # 每消息独立压缩 → 模拟 server_no_context_takeover
    f = mkframe(0x1, deflate_indep(mA), rsv1=True) + mkframe(0x1, deflate_indep(mB), rsv1=True)
    r2 = run_fake(hdr("Sec-WebSocket-Extensions: permessage-deflate; server_no_context_takeover") + f,
                  DEFLATE_OFFERS["params"], "accepted-noctx")
    check("T4b status=accepted", r2["deflate_status"] == "accepted", str(r2["deflate_status"]))
    check("T4b deflate_offered=True / accepted=True",
          r2["deflate_offered"] is True and r2["deflate_accepted"] is True)
    check("T4b 两条消息均解压成功（inflate_failures=0）", r2["inflate_failures"] == 0,
          f"failures={r2['inflate_failures']}")
    check("T4b 解压后负载=原文（p50=len(mA)）", r2["size_bytes"]["p50"] == len(mA),
          f"p50={r2['size_bytes']['p50']} vs {len(mA)}")
    check("T4b 业务消息=2（压缩帧仍计业务）", r2["business_messages"] == 2)

    # T4c：多交易对订阅报文（lbank 单对 ×3 / binance 批量 1 条 / bybit 批量 1 条）
    msgs_l, plan_l = build_subscribe_messages("lbank", ["btc_usdt", "eth_usdt", "sol_usdt"])
    check("T4c lbank 发 3 条单对报文（batch=1）",
          len(msgs_l) == 3 and all(m["pair"] in ("btc_usdt", "eth_usdt", "sol_usdt") for m in msgs_l)
          and plan_l["batch_size"] == 1, str(msgs_l))
    msgs_b, plan_b = build_subscribe_messages("binance", ["btcusdt", "ethusdt", "solusdt"])
    check("T4c binance 单条批量报文（params 3 个 stream）",
          len(msgs_b) == 1 and msgs_b[0]["method"] == "SUBSCRIBE"
          and msgs_b[0]["params"] == ["btcusdt@trade", "ethusdt@trade", "solusdt@trade"], str(msgs_b))
    msgs_y, plan_y = build_subscribe_messages("bybit", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    check("T4c bybit 单条批量报文（args 3 个 publicTrade.*）",
          len(msgs_y) == 1 and msgs_y[0]["args"] == ["publicTrade.BTCUSDT", "publicTrade.ETHUSDT",
                                                     "publicTrade.SOLUSDT"], str(msgs_y))
    # 21 个 bybit args → 按保守 batch=10 分 3 条（仍同一连接）
    msgs_y2, _ = build_subscribe_messages("bybit", [f"AAA{i}USDT" for i in range(21)])
    check("T4c bybit 21 对 → 3 条报文（10/10/1，单连接）",
          len(msgs_y2) == 3 and [len(m["args"]) for m in msgs_y2] == [10, 10, 1],
          str([len(m["args"]) for m in msgs_y2]))

    # T5：多交易对场次（lbank，3 对）→ symbols_count / wire_bytes_total / per-symbol 计数
    trades = b"".join(mkframe(0x1, json.dumps({"type": "trade", "pair": p}).encode())
                      for p in ("btc_usdt", "eth_usdt", "btc_usdt"))
    r5 = run_fake(hdr() + trades, None, "multi", venue="lbank",
                  symbols=["btc_usdt", "eth_usdt", "btc_usdt"])
    check("T5a symbols_count=3", r5["symbols_count"] == 3, str(r5["symbols_count"]))
    check("T5b 订阅报文 3 条（lbank 单对/条）", r5["subscribe_messages_sent"] == 3,
          str(r5.get("subscribe_messages_sent")))
    check("T5c symbol_msg_counts = {btc_usdt:2, eth_usdt:1}",
          r5["symbol_msg_counts"] == {"btc_usdt": 2, "eth_usdt": 1}, str(r5["symbol_msg_counts"]))
    check("T5d wire_bytes_total 与 wire_bytes 一致（无心跳/回执/控制帧）",
          r5["wire_bytes_total"] == r5["wire_bytes"])

    # T6：异常路径不丢数据（v1.1 回归）
    class Boom(FakeSock):
        def recv(s, n):
            if s.i >= len(s.data):
                raise ConnectionResetError("reset by peer")
            return FakeSock.recv(s, n)

    orig_cc, orig_ctx = socket.create_connection, ssl.create_default_context
    socket.create_connection = lambda *a, **k: object()
    ssl.create_default_context = lambda *a, **k: FakeCtx(None)
    ssl.create_default_context = lambda *a, **k: type("C", (), {"wrap_socket":
        lambda s, sk, **kw: Boom(hdr() + trades)})()
    try:
        r6 = run_session("lbank", 1, symbols=["btc_usdt"], subscribe_interval=0)
    finally:
        socket.create_connection, ssl.create_default_context = orig_cc, orig_ctx
    check("T6 异常后已采 3 条业务消息仍落盘", r6["business_messages"] == 3, str(r6["business_messages"]))
    check("T6 collection_complete=False 且有 error", r6["collection_complete"] is False and r6["error"])

    print("T7 压缩：ladder 全被拒时**测量会话自身**仍带 offer（v1.3 修 D3）")
    orig_cc, orig_ctx = socket.create_connection, ssl.create_default_context
    socket.create_connection = lambda *a, **k: object()
    ssl.create_default_context = lambda *a, **k: FakeCtx(hdr("Sec-WebSocket-Extensions: x-webkit-deflate-frame") + body)
    try:
        r7 = run_session("lbank", 1,
                         offer_headers=[DEFLATE_OFFERS["bare"], DEFLATE_OFFERS["params"]],
                         symbols=["btc_usdt"], subscribe_interval=0)
    finally:
        socket.create_connection, ssl.create_default_context = orig_cc, orig_ctx
    check("T7a deflate_offered=True（测量会话确带 offer）", r7["deflate_offered"] is True,
          str(r7["deflate_offered"]))
    check("T7b deflate_status=server_refused（服务端只回别的扩展）",
          r7["deflate_status"] == "server_refused", str(r7["deflate_status"]))
    check("T7c offer_source=ladder-fallback-first-offer",
          r7["deflate_measurement_offer_source"] == "ladder-fallback-first-offer",
          str(r7.get("deflate_measurement_offer_source")))
    check("T7d probe 记录 2 条且 all_refused=True",
          len(r7["deflate_probe_statuses"]) == 2 and r7["deflate_probe_all_refused"] is True,
          str(r7["deflate_probe_statuses"]))
    check("T7e ladder 探测不影响业务计数口径（1 条业务消息）",
          r7["business_messages"] == 1, str(r7["business_messages"]))
    r7f = run_fake(hdr() + body, None, "no-deflate-flag")
    check("T7f 未传任何 offer 时 offer_source=none（与 server_refused 可区分）",
          r7f["deflate_measurement_offer_source"] == "none"
          and r7f["deflate_status"].startswith("not_offered"),
          f"{r7f.get('deflate_measurement_offer_source')}/{r7f['deflate_status']}")

    print(f"\n自测结果：{'全部通过' if not fails else '失败 ' + str(len(fails)) + ' 项'}")
    for x in fails:
        print(f"  - FAILED: {x}")
    return 0 if not fails else 1


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="公开 WS 行情传输量测量（低频、单连接、无压测）")
    ap.add_argument("--venue", default="all", choices=["all"] + list(VENUES))
    ap.add_argument("--duration", type=int, default=None,
                    help="每场次采集秒数（默认 60；可到 600 做 #27008 规模重测）")
    ap.add_argument("--seconds", type=int, default=None,
                    help="--duration 的旧别名（v1.1 及以前用此名；两者同时给出且不一致则报错）")
    ap.add_argument("--pair", default=None, help="覆盖单交易对（当前仅 lbank 生效，默认 btc_usdt）")
    ap.add_argument("--symbols", default=None,
                    help="交易对：逗号分隔的**基础资产**（如 BTC,ETH,SOL）；也接受一个整数 N"
                         "（用内置样表取前 N 个，仅供冒烟，159 对请用 --symbols-file）")
    ap.add_argument("--symbols-file", default=None,
                    help="交易对清单文件：JSON 列表 / JSON {assets:[...]} / JSON {lbank:[...],...} / "
                         "纯文本每行一个基础资产（# 注释）")
    ap.add_argument("--raw-symbols", default=None,
                    help="逗号分隔的 venue 原生交易对（不做格式转换；配合单一 --venue 使用）")
    ap.add_argument("--quote", default="USDT", help="计价资产（默认 USDT；lbank 自动转小写）")
    ap.add_argument("--subscribe-interval", type=float, default=0.05,
                    help="多条订阅报文之间的间隔秒（默认 0.05，礼貌节流；0=不等待）")
    ap.add_argument("--host", default=None, help="覆盖 host（仅对 --venue lbank 生效，例如 www.lbkex.net，复现 CCXT 现场）")
    ap.add_argument("--path", default=None, help="覆盖 path（仅对 --venue lbank 生效）")
    ap.add_argument("--deflate", action="store_true",
                    help="主动 offer permessage-deflate；服务端是否回该扩展 = 服务端能力证据")
    ap.add_argument("--deflate-offer", default=None,
                    help="offer 原文或预设名（bare|params|full）。默认 params = "
                         "'permessage-deflate; client_max_window_bits'")
    ap.add_argument("--deflate-ladder", action="store_true",
                    help="逐个 offer 变体（bare→params→full）做探测握手，用第一个被接受的跑测量；"
                         "全部被拒 → 以不 offer 跑基线。这是把『服务端拒绝』与『我们 offer 写错』分开的最强证据")
    ap.add_argument("--sleep", type=float, default=5.0, help="场次间隔秒（默认 5，礼貌节流）")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "",
                    help="HTTP CONNECT 代理（形如 http://127.0.0.1:7890）；留空=直连。socks5 不支持")
    ap.add_argument("--out", default="measure_ws_result.json")
    ap.add_argument("--selftest", action="store_true", help="只跑离线自测（零网络），不连任何服务端")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()

    if a.duration is None and a.seconds is None:
        duration = 60
    elif a.duration is not None and a.seconds is not None and a.duration != a.seconds:
        raise SystemExit("--duration 与 --seconds 同时给出且不一致，请只用一个")
    else:
        duration = a.duration if a.duration is not None else a.seconds
    if duration <= 0:
        raise SystemExit("--duration/--seconds 必须为正整数")
    if duration > 300:
        print(f"⚠️  {duration}s 长场次：请确认是 #27008 规模重测（单连接、公开端点、无压测），"
              "并固定出口。", flush=True)

    offers = []
    if a.deflate or a.deflate_ladder or a.deflate_offer:
        if a.deflate_ladder:
            offers = [DEFLATE_OFFERS[k] for k in DEFLATE_LADDER]
        elif a.deflate_offer:
            offers = [DEFLATE_OFFERS[a.deflate_offer]
                      if a.deflate_offer in DEFLATE_OFFERS else a.deflate_offer]
        else:
            offers = [DEFLATE_OFFERS["params"]]

    venues = list(VENUES) if a.venue == "all" else [a.venue]
    if a.symbols_file and a.venue == "all":
        print("提示：--symbols-file 的分 venue 写法只在单 --venue 时生效；"
              "「基础资产」写法对三所分别转换，可配合 --venue all。", flush=True)

    results = []
    for i, v in enumerate(venues):
        if i:
            time.sleep(a.sleep)
        symbols, smeta = resolve_symbols(v, a)
        if a.pair and len(symbols) == 1:
            symbols = [a.pair]
            smeta = {"source": "--pair 覆盖"}
        print(f"[{time.strftime('%H:%M:%S')}] 采集 {v} … {duration}s，交易对 {len(symbols)} 个"
              f"（{smeta.get('source')}）", flush=True)
        r = run_session(v, duration, host=(a.host if v == "lbank" else None),
                        path=(a.path if v == "lbank" else None),
                        offer_headers=offers, symbols=symbols, symbol_meta=smeta,
                        proxy=a.proxy, subscribe_interval=a.subscribe_interval)
        results.append(r)
        flag = "ERR " + str(r["error"]) if r["error"] else "ok"
        print(f"   {flag}  symbols={r.get('symbols_count')} seen={r.get('symbols_seen')}  "
              f"msg={r.get('business_messages')}  wire/s={r.get('wire_bytes_per_s')}  "
              f"p50={r.get('size_bytes', {}).get('p50')}B  "
              f"deflate: offered={r.get('deflate_offered')} accepted={r.get('deflate_accepted')} "
              f"status={r.get('deflate_status')} src={r.get('deflate_measurement_offer_source')}  "
              f"app_ping_frames={r.get('app_ping_frames')}  hb_sent={r.get('heartbeat_pings_sent')}  "
              f"inflate_fail={r.get('inflate_failures')}", flush=True)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "script_version": SCRIPT_VERSION,
            "seconds_per_venue": duration,
            "deflate_offer_headers": offers,
            "method": ("single connection per venue, sequential, no reconnect, no keys, "
                       "public channels only"),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n写入 {a.out}")
    print("\n判读要点：")
    print("  * 比 wire_bytes_per_s 与 msg_per_s —— 若 LBank 显著更高且 size 分布相近，则为『服务端发送频率/粒度』问题")
    print("  * 看 deflate_status：accepted=服务端接受压缩（CCXT 侧可修）；server_refused=服务端拒绝（服务端行为）；")
    print("    not_offered=本次没 offer（不可作为能力证据）；unsolicited=服务端未请求即回扩展（协议异常，本脚本不禁用 inflate 之外的任何推断）")
    print("  * size p50 若明显偏大 —— 每消息 JSON 冗余字段（无聚合通道）")
    print("  * symbols_seen < symbols_count —— 部分交易对在该窗口内无成交（不是订阅失败；看 subscribe_errors）")
    print("  * app_ping_frames / subscribe_acks / heartbeat_* 已从业务指标剔除；异常场次看 collection_complete 与 error")
    print("  * inflate_failures > 0 —— 解压失败（分片/参数不匹配），该场次的 payload 尺寸按密文计，须先查因再比较")
    print("  * 单点拒绝（未回扩展）建议多出口复测后再定性")


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------- 修订记录
# 版本历史（v1.2 / v1.3 的缺陷与修复，含 D1/D1b/D2/D3）已迁出本文件，
# 见同目录 CHANGELOG.md。保留此指引以便读者从源码定位版本溯源；
# 本文件不再内嵌变更记录。
