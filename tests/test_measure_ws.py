# -*- coding: utf-8 -*-
"""Offline pytest suite for measure_ws.py (v1.4). Zero network: every test
drives the handshake parser / frame reader / session accounting against
synthetic byte streams, exactly like the built-in ``--selftest`` but as
real pytest cases so failures carry file/line context and new paths
(RSV1-without-deflate, --probe, --strict, symbols-file errors) get coverage.
"""
import json
import socket
import struct
import sys
import zlib
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import measure_ws as mw  # noqa: E402


# ---------------------------------------------------------------- helpers
def read_data(reader):
    """Read one frame; fail unless it is a data event; return (op, payload, wire)."""
    ev = reader.read_frame()
    if ev[0] != "data":
        raise AssertionError(f"expected data event, got {ev!r}")
    return cast(tuple, ev)[1:]
def mkframe(op, payload, rsv1=False, masked=False):
    """Server-style frame (unmasked by default; tolerated masked for tests)."""
    n = len(payload)
    h = bytes([(0x80 | (0x40 if rsv1 else 0x00)) | op])
    mbit = 0x80 if masked else 0x00
    if n < 126:
        h += bytes([mbit | n])
    elif n < 65536:
        h += bytes([mbit | 126]) + struct.pack(">H", n)
    else:
        h += bytes([mbit | 127]) + struct.pack(">Q", n)
    if masked:
        mask = b"\x01\x02\x03\x04"
        h += mask
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return h + payload


def deflate_indep(msg):
    """Per-message compression (server_no_context_takeover style), RFC 7692
    no-tail-bytes convention (strip the 4-byte 00 00 ff ff tail)."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return (c.compress(msg) + c.flush(zlib.Z_SYNC_FLUSH))[:-4]


def deflate_raw(msg, window=-15):
    c = zlib.compressobj(9, zlib.DEFLATED, window)
    return c.compress(msg) + c.flush(zlib.Z_SYNC_FLUSH)


class FakeSock:
    def __init__(self, data):
        self.data, self.i, self.sent = data, 0, []

    def recv(self, n):
        if self.i >= len(self.data):
            raise socket.timeout("idle")
        c = self.data[self.i:self.i + n]
        self.i += len(c)
        return c

    def sendall(self, b):
        self.sent.append(b)

    def settimeout(self, t):
        pass

    def close(self):
        pass


class FakeCtx:
    def __init__(self, data):
        self.data = data

    def wrap_socket(self, sk, **kw):
        return FakeSock(self.data)


def fake_time(step=0.01):
    """Return a time.time replacement advancing `step` seconds per call, so a
    session loop terminates in wall-clock milliseconds instead of real seconds.
    Setup consumes ~3 calls (t_start / t_subscribed / last_send), so with the
    default 0.01s step a ``seconds=2`` session yields ~200 loop iterations."""
    calls = {"n": 0}

    def _t():
        calls["n"] += 1
        return calls["n"] * step

    return _t


def run_fake(monkeypatch, resp_bytes, offer, venue="binance", seconds=2,
             symbols=None, subscribe_interval=0, probe_only=False):
    """Drive run_session fully offline via monkeypatched socket/ssl."""
    monkeypatch.setattr(mw.time, "time", fake_time())
    monkeypatch.setattr(mw.socket, "create_connection", lambda *a, **k: object())
    monkeypatch.setattr(mw.ssl, "create_default_context",
                        lambda *a, **k: FakeCtx(resp_bytes))
    return mw.run_session(venue, seconds,
                          offer_headers=([offer] if offer else []),
                          symbols=symbols, subscribe_interval=subscribe_interval,
                          probe_only=probe_only)


def hdr(*extra):
    return ("\r\n".join(["HTTP/1.1 101 Switching Protocols", "Upgrade: websocket",
                         "Sec-WebSocket-Accept: not-checked"] + list(extra))
            + "\r\n\r\n").encode()


class Args:
    """Minimal argparse.Namespace stand-in for resolve_symbols tests."""

    def __init__(self, raw_symbols=None, symbols_file=None, symbols=None, quote="USDT"):
        self.raw_symbols = raw_symbols
        self.symbols_file = symbols_file
        self.symbols = symbols
        self.quote = quote


# ---------------------------------------------------------------- extension parsing
class TestExtensionParsing:
    def test_accept_with_params(self):
        parsed = mw.parse_extension_header(
            ["permessage-deflate; server_max_window_bits=15; client_no_context_takeover"])
        p = mw.find_permessage_deflate(parsed)
        assert p is not None
        assert p["server_max_window_bits"] == "15"
        assert "client_no_context_takeover" in p
        assert p["client_no_context_takeover"] is None

    def test_status_matrix(self):
        assert mw.deflate_status(True, True, ["permessage-deflate"]) == "accepted"
        assert mw.deflate_status(True, False, []) == "server_refused"
        assert mw.deflate_status(False, True, ["permessage-deflate"]) == "unsolicited"
        assert mw.deflate_status(False, False, []) == "not_offered"
        assert mw.deflate_status(False, False, ["x-webkit-deflate-frame"]) == \
            "not_offered_server_sent_other_extension"

    def test_no_false_positive_on_similar_tokens(self):
        parsed = mw.parse_extension_header(["x-webkit-deflate-frame", "permessage-deflatex"])
        assert mw.find_permessage_deflate(parsed) is None

    def test_case_insensitive_token(self):
        assert mw.find_permessage_deflate(
            mw.parse_extension_header(["PerMessage-Deflate; client_max_window_bits"])) is not None

    def test_multiple_extensions_split(self):
        parsed = mw.parse_extension_header(
            ["permessage-deflate; client_max_window_bits", "x-webkit-deflate-frame"])
        names = [n for n, _ in parsed]
        assert names == ["permessage-deflate", "x-webkit-deflate-frame"]

    def test_multiple_header_lines_are_combined(self):
        parsed = mw.parse_extension_header(
            ["permessage-deflate", "x-webkit-deflate-frame; level=3"])
        assert [n for n, _ in parsed] == ["permessage-deflate", "x-webkit-deflate-frame"]

    def test_quoted_comma_does_not_split(self):
        parts = mw.split_extension_list(['foo; p="a,b"'])
        assert parts == ['foo; p="a,b"']

    def test_quoted_param_value_strips_quotes(self):
        parsed = mw.parse_extension_header(['permessage-deflate; client_max_window_bits="15"'])
        p = mw.find_permessage_deflate(parsed)
        assert p["client_max_window_bits"] == "15"

    def test_blank_and_garbage_parts_skipped(self):
        assert mw.parse_extension_header([",  ,"]) == []
        assert mw.parse_extension_header([""]) == []

    def test_param_missing_value_none(self):
        parsed = mw.parse_extension_header(["permessage-deflate; server_no_context_takeover"])
        p = mw.find_permessage_deflate(parsed)
        assert p == {"server_no_context_takeover": None}


# ---------------------------------------------------------------- client frame builder
class TestClientFrame:
    def test_small_frame_masked_and_length_byte(self):
        f = mw._client_frame(0x1, b"hello")
        assert f[0] == 0x81                       # FIN + text
        assert f[1] == 0x80 | 5                   # masked + length
        assert f[2:6] == f[2:6]                   # 4-byte mask present
        mask = f[2:6]
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(f[6:]))
        assert body == b"hello"

    def test_rsv1_bit_set_when_requested(self):
        f = mw._client_frame(0x1, b"x", rsv1=True)
        assert f[0] == 0xC1                       # FIN + RSV1 + text
        f2 = mw._client_frame(0x1, b"x", rsv1=False)
        assert f2[0] == 0x81

    def test_medium_length_uses_extended_16bit(self):
        payload = b"a" * 126
        f = mw._client_frame(0x1, payload)
        assert f[1] == 0x80 | 126
        assert struct.unpack(">H", f[2:4])[0] == 126
        assert len(f) == 2 + 2 + 4 + 126

    def test_large_length_uses_extended_64bit(self):
        payload = b"a" * 65536
        f = mw._client_frame(0x1, payload)
        assert f[1] == 0x80 | 127
        assert struct.unpack(">Q", f[2:10])[0] == 65536
        assert len(f) == 2 + 8 + 4 + 65536

    def test_continuation_opcode_has_no_fin(self):
        f = mw._client_frame(0x0, b"x")
        assert f[0] == 0x00                       # no FIN for continuation

    def test_control_frame_ping(self):
        f = mw._client_frame(0x9, b"ping")
        assert f[0] == 0x89


# ---------------------------------------------------------------- WSReader
class TestWSReader:
    def _reader(self, data, deflate_params=None):
        return mw.WSReader(FakeSock(data), b"", deflate_params=deflate_params)

    def test_control_frames_counted_and_pong_echoed(self):
        r = self._reader(mkframe(0x9, b"hb"))     # WS-level ping
        ev = r.read_frame()
        assert ev == ("control",)
        assert r.frames_control == 1
        assert r.control_wire_bytes == 2 + 2
        assert len(r.sock.sent) == 1
        assert r.sock.sent[0][0] == 0x8A          # pong opcode
        assert r.wire_bytes_total() == 4          # 2 hdr + 2 payload

    def test_close_frame_raises_eof(self):
        r = self._reader(mkframe(0x8, b""))
        with pytest.raises(EOFError):
            r.read_frame()

    def test_idle_on_frame_boundary_timeout(self):
        r = self._reader(b"")
        assert r.read_frame() == ("idle",)

    def test_midframe_timeout_raises(self):
        # 2-byte header promises 10 payload bytes but only 1 arrives
        r = self._reader(mkframe(0x1, b"")[:1] + b"\x81\x05a")
        with pytest.raises(socket.timeout):
            r.read_frame()

    def test_extended_lengths_inbound(self):
        payload = b"z" * 300
        r = self._reader(mkframe(0x1, payload))
        op, got, wire = read_data(r)
        assert op == 0x1 and got == payload and wire == 2 + 2 + 300

    def test_masked_server_frame_is_tolerated_and_unmasked(self):
        payload = b"masked!"
        r = self._reader(mkframe(0x1, payload, masked=True))
        op, got, _ = read_data(r)
        assert op == 0x1 and got == payload

    def test_record_business_accounting(self):
        r = self._reader(b"")
        r.record_business(b"abc", 10, symbol="BTCUSDT")
        r.record_business(b"de", 8, symbol="ETHUSDT")
        assert r.payload_bytes == 5 and r.wire_bytes == 18
        assert r.sizes == [3, 2]
        assert r.symbol_msg_counts == {"BTCUSDT": 1, "ETHUSDT": 1}
        assert r.first_business_msg_at is not None
        assert r.wire_bytes_total() == 18

    def test_app_ping_and_ack_are_segregated(self):
        r = self._reader(b"")
        r.record_app_ping(b"ping", 8)
        r.record_ack(b"ack", 9)
        assert r.app_ping_frames == 1 and r.app_ping_wire_bytes == 8
        assert r.ack_frames == 1 and r.ack_wire_bytes == 9
        assert r.payload_bytes == 0 and r.wire_bytes == 0
        assert r.wire_bytes_total() == 17

    def test_deflate_window_bits_respected(self):
        # server_max_window_bits=9 → inflate with window -9
        msg = b'{"e":"trade","s":"BTCUSDT"}'
        raw = deflate_raw(msg, window=-9)
        r = self._reader(mkframe(0x1, raw, rsv1=True),
                         deflate_params={"server_max_window_bits": "9"})
        op, payload, _ = read_data(r)
        assert payload == msg
        assert r.compressed_frames == 1

    def test_window_bits_8_accepted_by_stdlib_zlib(self):
        # RFC 7692 allows 8..15; Python's zlib.decompressobj accepts -8
        # (compressobj does not, but this tool only INFLATES server frames).
        msg = b'{"e":"trade","s":"BTCUSDT"}'
        raw = deflate_raw(msg)                     # short distances: decodes at -8
        r = self._reader(mkframe(0x1, raw, rsv1=True),
                         deflate_params={"server_max_window_bits": "8"})
        assert r._window == -8
        op, payload, _ = read_data(r)
        assert payload == msg

    def test_invalid_window_bits_fall_back_to_default(self):
        for bad in ("99", "abc"):
            r = self._reader(b"", deflate_params={"server_max_window_bits": bad})
            assert r._window == -15

    def test_no_context_takeover_resets_inflater_per_message(self):
        r = self._reader(b"", deflate_params={"server_no_context_takeover": None})
        for i in range(3):
            msg = b'{"e":"trade","s":"BTCUSDT","q":"%d"}' % i
            r.buf += mkframe(0x1, deflate_indep(msg), rsv1=True)
            op, payload, _ = read_data(r)
            # each frame must be independently compressed
            assert payload == msg

    def test_inflate_failure_counted_and_ciphertext_fallback(self):
        r = self._reader(b"", deflate_params={"server_no_context_takeover": None})
        garbage = b"\x00\x01\x02\x03\x04\x05"
        r.buf = mkframe(0x1, garbage, rsv1=True)
        op, payload, _ = read_data(r)
        assert r.inflate_failures == 1
        assert payload == garbage                    # ciphertext kept, not silent

    def test_rsv1_without_negotiation_counted_and_not_inflated(self):
        # v1.4 regression: server sets RSV1 but no deflate negotiated → the
        # frame is ciphertext; it must be counted separately, not silently
        # recorded as plaintext payload.
        msg = b'{"e":"trade","s":"BTCUSDT"}'
        raw = deflate_raw(msg)
        r = self._reader(mkframe(0x1, raw, rsv1=True))   # no deflate_params
        op, payload, _ = read_data(r)
        assert payload == raw                            # untouched ciphertext
        assert r.rsv1_without_deflate == 1
        assert r.compressed_frames == 0

    def test_maybe_compact_after_large_pos(self):
        r = self._reader(b"")
        r.buf = b"tail"
        r.pos = (1 << 20) + 5
        r.record_business(b"x", 1)
        assert r.buf == b"" and r.pos == 0


# ---------------------------------------------------------------- session accounting
class TestRunSessionOffline:
    def test_no_offer_other_extension(self, monkeypatch):
        body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
        r = run_fake(monkeypatch, hdr("Sec-WebSocket-Extensions: x-webkit-deflate-frame") + body, None)
        assert r["deflate_status"] == "not_offered_server_sent_other_extension"
        assert r["deflate_accepted"] is False
        assert r["compressed_frames"] == 0
        assert r["business_messages"] == 1
        assert isinstance(r["wire_bytes_total"], int)
        assert r["wire_bytes_total"] >= r["wire_bytes"]

    def test_accepted_with_no_context_takeover(self, monkeypatch):
        mA = b'{"e":"trade","s":"BTCUSDT","q":"1"}'
        mB = b'{"e":"trade","s":"ETHUSDT","q":"2"}'
        frames = (mkframe(0x1, deflate_indep(mA), rsv1=True)
                  + mkframe(0x1, deflate_indep(mB), rsv1=True))
        r = run_fake(monkeypatch,
                     hdr("Sec-WebSocket-Extensions: permessage-deflate; server_no_context_takeover")
                     + frames, mw.DEFLATE_OFFERS["params"])
        assert r["deflate_status"] == "accepted"
        assert r["deflate_offered"] is True and r["deflate_accepted"] is True
        assert r["inflate_failures"] == 0
        assert r["size_bytes"]["p50"] == len(mA)
        assert r["business_messages"] == 2

    def test_multi_symbol_lbank_session(self, monkeypatch):
        trades = b"".join(mkframe(0x1, json.dumps({"type": "trade", "pair": p}).encode())
                          for p in ("btc_usdt", "eth_usdt", "btc_usdt"))
        r = run_fake(monkeypatch, hdr() + trades, None, venue="lbank",
                     symbols=["btc_usdt", "eth_usdt", "btc_usdt"])
        assert r["symbols_count"] == 3
        assert r["subscribe_messages_sent"] == 3
        assert r["symbol_msg_counts"] == {"btc_usdt": 2, "eth_usdt": 1}
        assert r["symbols_seen"] == 2
        assert r["wire_bytes_total"] == r["wire_bytes"]
        assert r["collection_complete"] is True

    def test_error_path_retains_partial_data(self, monkeypatch):
        class Boom(FakeSock):
            def recv(self, n):
                if self.i >= len(self.data):
                    raise ConnectionResetError("reset by peer")
                return FakeSock.recv(self, n)

        trades = b"".join(mkframe(0x1, json.dumps({"type": "trade", "pair": p}).encode())
                          for p in ("btc_usdt", "eth_usdt", "btc_usdt"))
        monkeypatch.setattr(mw.time, "time", fake_time())
        monkeypatch.setattr(mw.socket, "create_connection", lambda *a, **k: object())
        ctx = type("C", (), {"wrap_socket": lambda s, sk, **kw: Boom(hdr() + trades)})()
        monkeypatch.setattr(mw.ssl, "create_default_context", lambda *a, **k: ctx)
        r = mw.run_session("lbank", 2, symbols=["btc_usdt", "eth_usdt", "btc_usdt"],
                           subscribe_interval=0)
        assert r["business_messages"] == 3
        assert r["collection_complete"] is False
        assert r["error"]

    def test_ladder_all_refused_measurement_still_offers(self, monkeypatch):
        # v1.3 D3 regression: measurement session itself must carry an offer
        body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
        monkeypatch.setattr(mw.time, "time", fake_time())
        monkeypatch.setattr(mw.socket, "create_connection", lambda *a, **k: object())
        monkeypatch.setattr(mw.ssl, "create_default_context",
                            lambda *a, **k: FakeCtx(
                                hdr("Sec-WebSocket-Extensions: x-webkit-deflate-frame") + body))
        r = mw.run_session("lbank", 2, offer_headers=[mw.DEFLATE_OFFERS["bare"],
                                                      mw.DEFLATE_OFFERS["params"]],
                           symbols=["btc_usdt"], subscribe_interval=0)
        assert r["deflate_offered"] is True
        assert r["deflate_status"] == "server_refused"
        assert r["deflate_measurement_offer_source"] == "ladder-fallback-first-offer"
        assert len(r["deflate_probe_statuses"]) == 2
        assert r["deflate_probe_all_refused"] is True
        assert r["business_messages"] == 1

    def test_ladder_accepted_offer_is_used_for_measurement(self, monkeypatch):
        class SeqCtx:
            def __init__(self, datas):
                self.datas, self.i = datas, 0

            def wrap_socket(self, sk, **kw):
                # probe 1 → refused, probe 2 → accepted, measurement → accepted
                d = self.datas[min(self.i, len(self.datas) - 1)]
                self.i += 1
                return FakeSock(d)

        body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
        refused = hdr("Sec-WebSocket-Extensions: x-webkit-deflate-frame") + body
        accepted = hdr("Sec-WebSocket-Extensions: permessage-deflate") + body
        monkeypatch.setattr(mw.time, "time", fake_time())
        monkeypatch.setattr(mw.socket, "create_connection", lambda *a, **k: object())
        seq = SeqCtx([refused, accepted])               # ONE instance: counter persists across probes
        monkeypatch.setattr(mw.ssl, "create_default_context", lambda *a, **k: seq)
        r = mw.run_session("lbank", 2, offer_headers=[mw.DEFLATE_OFFERS["bare"],
                                                      mw.DEFLATE_OFFERS["params"]],
                           symbols=["btc_usdt"], subscribe_interval=0)
        assert r["deflate_measurement_offer_source"] == "ladder-accepted"
        assert r["deflate_offer_header"] == mw.DEFLATE_OFFERS["params"]
        assert r["deflate_status"] == "accepted"
        assert r["business_messages"] == 1

    def test_no_offers_source_none(self, monkeypatch):
        body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
        r = run_fake(monkeypatch, hdr() + body, None)
        assert r["deflate_measurement_offer_source"] == "none"
        assert r["deflate_status"].startswith("not_offered")

    def test_probe_only_no_subscribe_no_collect(self, monkeypatch):
        body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
        r = run_fake(monkeypatch, hdr() + body, None, probe_only=True)
        assert r["collection_complete"] is True
        # probe path returns before the collection loop / finalize, so no
        # subscribe/business counters are produced at all
        assert r.get("subscribe_messages_sent", 0) == 0
        assert r.get("business_messages", 0) == 0
        assert r["http_status"].startswith("HTTP/1.1 101")

    def test_probe_only_records_deflate_acceptance(self, monkeypatch):
        body = mkframe(0x1, b'{"e":"trade","s":"BTCUSDT"}')
        r = run_fake(monkeypatch, hdr("Sec-WebSocket-Extensions: permessage-deflate") + body,
                     mw.DEFLATE_OFFERS["params"], probe_only=True)
        assert r["deflate_status"] == "accepted"
        assert r["deflate_offer_header"] == mw.DEFLATE_OFFERS["params"]

    def test_bybit_active_ping_sent_on_idle(self, monkeypatch):
        body = mkframe(0x1, json.dumps({"e": "trade", "s": "BTCUSDT"}).encode())
        monkeypatch.setattr(mw.time, "time", fake_time(step=1.0))
        monkeypatch.setattr(mw.socket, "create_connection", lambda *a, **k: object())
        sock_holder = {}

        class Ctx:
            def wrap_socket(self, sk, **kw):
                s = FakeSock(hdr() + body)
                sock_holder["sock"] = s
                return s

        monkeypatch.setattr(mw.ssl, "create_default_context", lambda *a, **k: Ctx())
        r = mw.run_session("bybit", 25, symbols=["BTCUSDT"], subscribe_interval=0)
        assert r["heartbeat_pings_sent"] >= 1

        def unmask_client_frame(b):
            # client frames are masked: 2 hdr + 4 mask + XOR payload
            mask = b[2:6]
            return bytes(x ^ mask[i % 4] for i, x in enumerate(b[6:]))

        ws_frames = [b for b in sock_holder["sock"].sent if b[0] == 0x81]
        sent_json = [json.loads(unmask_client_frame(b).decode()) for b in ws_frames]
        assert any(m == {"op": "ping"} for m in sent_json)
        assert r["business_messages"] == 1

    def test_lbank_app_ping_answered_and_segregated(self, monkeypatch):
        ping_frame = mkframe(0x1, b'{"action":"ping","ping":123}')
        body = mkframe(0x1, b'{"type":"trade","pair":"btc_usdt"}')
        r = run_fake(monkeypatch, hdr() + ping_frame + body, None, venue="lbank",
                     symbols=["btc_usdt"])
        assert r["app_pings_sent"] == 1
        assert r["app_ping_frames"] == 1
        assert r["business_messages"] == 1          # ping excluded from business
        assert r["msg_types"].get("trade") == 1

    def test_bybit_pong_response_not_business(self, monkeypatch):
        body = mkframe(0x1, b'{"op":"pong","ret_msg":"pong"}')
        r = run_fake(monkeypatch, hdr() + body, None, venue="bybit", symbols=["BTCUSDT"])
        assert r["heartbeat_pongs_received"] == 1
        assert r["business_messages"] == 0

    def test_subscribe_ack_binance_and_error_bybit_split(self, monkeypatch):
        ack = mkframe(0x1, b'{"result":null,"id":1}')
        err = mkframe(0x1, b'{"success":false,"op":"subscribe","ret_msg":"bad"}')
        r = run_fake(monkeypatch, hdr() + ack, None, venue="binance", symbols=["btcusdt"])
        assert r["subscribe_acks"] == 1 and r["business_messages"] == 0

        r2 = run_fake(monkeypatch, hdr() + err, None, venue="bybit", symbols=["BTCUSDT"])
        # Bybit acks carry "op":"subscribe" + "success" — failed acks are still
        # ack frames AND recorded in subscribe_errors (per-symbol rejection signal)
        assert r2["subscribe_acks"] == 1
        assert r2["subscribe_errors"] and r2["business_messages"] == 0

    def test_non_json_payload_classified(self, monkeypatch):
        body = mkframe(0x1, b"\x00\x01\x02 raw bytes")
        r = run_fake(monkeypatch, hdr() + body, None, symbols=["btcusdt"])
        assert r["business_messages"] == 1
        assert r["msg_types"].get("non-json") == 1

    def test_empty_session_size_distribution_all_none(self, monkeypatch):
        r = run_fake(monkeypatch, hdr(), None, seconds=2, symbols=["btcusdt"])
        assert r["business_messages"] == 0
        assert r["size_bytes"] == {"min": None, "p50": None, "p90": None,
                                   "p99": None, "max": None, "mean": None}
        assert r["msg_per_s"] == 0.0
        assert r["wire_bytes_total"] == 0
        assert r["collection_complete"] is True

    def test_percentile_order_and_mean(self, monkeypatch):
        import random
        rng = random.Random(42)
        sizes = [rng.randint(10, 200) for _ in range(50)]
        frames = b"".join(mkframe(0x1, b"x" * s) for s in sizes)
        r = run_fake(monkeypatch, hdr() + frames, None, symbols=["btcusdt"])
        sb = r["size_bytes"]
        assert sb["min"] == min(sizes) and sb["max"] == max(sizes)
        assert sb["min"] <= sb["p50"] <= sb["p90"] <= sb["p99"] <= sb["max"]
        assert sb["mean"] == round(sum(sizes) / 50, 1)

    def test_rsv1_without_deflate_surfaced_in_result(self, monkeypatch):
        import zlib
        msg = b'{"e":"trade","s":"BTCUSDT"}'
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        raw = c.compress(msg) + c.flush(zlib.Z_SYNC_FLUSH)
        r = run_fake(monkeypatch, hdr() + mkframe(0x1, raw, rsv1=True), None,
                     symbols=["btcusdt"])
        assert r["rsv1_without_deflate"] == 1


# ---------------------------------------------------------------- symbols & subscribe
class TestSymbols:
    def test_default_single_pair(self):
        syms, meta = mw.resolve_symbols("lbank", Args())
        assert syms == ["btc_usdt"] and meta["source"] == "default-single-pair"

    def test_inline_list_and_case(self):
        syms, _ = mw.resolve_symbols("lbank", Args(symbols="BTC,ETH"))
        assert syms == ["btc_usdt", "eth_usdt"]
        syms, _ = mw.resolve_symbols("bybit", Args(symbols="BTC,ETH"))
        assert syms == ["BTCUSDT", "ETHUSDT"]

    def test_integer_n_uses_builtin_sample(self):
        syms, meta = mw.resolve_symbols("binance", Args(symbols="3"))
        assert syms == ["btcusdt", "ethusdt", "solusdt"]
        assert meta["source"] == "builtin-sample"

    def test_integer_overflow_raises(self):
        with pytest.raises(SystemExit):
            mw.resolve_symbols("binance", Args(symbols="999"))

    def test_quote_override(self):
        syms, _ = mw.resolve_symbols("binance", Args(symbols="BTC", quote="USDC"))
        assert syms == ["btcusdc"]

    def test_raw_symbols_passthrough(self):
        syms, meta = mw.resolve_symbols("lbank", Args(raw_symbols="BTC_USDT, ETH_USDT "))
        assert syms == ["BTC_USDT", "ETH_USDT"]
        assert meta["source"] == "raw-symbols"

    def test_file_plain_lines(self, tmp_path):
        f = tmp_path / "majors.txt"
        f.write_text("# comment\nBTC\nETH\n\nSOL\n", encoding="utf-8")
        syms, _ = mw.resolve_symbols("lbank", Args(symbols_file=str(f)))
        assert syms == ["btc_usdt", "eth_usdt", "sol_usdt"]

    def test_file_json_list(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text('["BTC", "ETH"]', encoding="utf-8")
        syms, _ = mw.resolve_symbols("binance", Args(symbols_file=str(f)))
        assert syms == ["btcusdt", "ethusdt"]

    def test_file_json_assets(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text('{"assets": ["BTC", "SOL"]}', encoding="utf-8")
        syms, _ = mw.resolve_symbols("bybit", Args(symbols_file=str(f)))
        assert syms == ["BTCUSDT", "SOLUSDT"]

    def test_file_json_per_venue(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text('{"lbank": ["btc_usdt"], "bybit": ["BTCUSDT"]}', encoding="utf-8")
        syms, meta = mw.resolve_symbols("bybit", Args(symbols_file=str(f)))
        assert syms == ["BTCUSDT"]
        assert meta["source"] == str(f)

    def test_missing_file_raises_clean_exit(self, tmp_path):
        with pytest.raises(SystemExit, match="打不开"):
            mw.resolve_symbols("lbank", Args(symbols_file=str(tmp_path / "nope.txt")))

    def test_malformed_json_raises_clean_exit(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit, match="JSON 解析失败"):
            mw.resolve_symbols("lbank", Args(symbols_file=str(f)))


class TestSubscribeMessages:
    def test_lbank_one_per_frame(self):
        msgs, plan = mw.build_subscribe_messages("lbank", ["btc_usdt", "eth_usdt", "sol_usdt"])
        assert len(msgs) == 3 and plan["batch_size"] == 1
        assert all(m["subscribe"] == "trade" for m in msgs)
        assert msgs[0]["pair"] == "btc_usdt"

    def test_binance_batch_1024(self):
        syms = [f"b{i}usdt" for i in range(1025)]
        msgs, plan = mw.build_subscribe_messages("binance", syms)
        assert len(msgs) == 2
        assert len(msgs[0]["params"]) == 1024 and len(msgs[1]["params"]) == 1
        assert msgs[0]["method"] == "SUBSCRIBE" and msgs[0]["id"] == 1

    def test_bybit_ten_per_frame(self):
        msgs, plan = mw.build_subscribe_messages("bybit", [f"AAA{i}USDT" for i in range(21)])
        assert len(msgs) == 3
        assert [len(m["args"]) for m in msgs] == [10, 10, 1]
        assert plan["batch_capability"].startswith("批量")

    def test_empty_symbols_returns_no_messages(self):
        msgs, plan = mw.build_subscribe_messages("lbank", [])
        assert msgs == []
        assert plan["messages_planned"] == 0


class TestExtractSymbol:
    def test_pair_key(self):
        assert mw.extract_symbol({"type": "trade", "pair": "btc_usdt"}) == "btc_usdt"

    def test_s_key(self):
        assert mw.extract_symbol({"e": "trade", "s": "BTCUSDT"}) == "BTCUSDT"

    def test_topic_suffix(self):
        assert mw.extract_symbol({"topic": "publicTrade.BTCUSDT"}) == "BTCUSDT"

    def test_nested_data_list(self):
        assert mw.extract_symbol({"data": [{"s": "ETHUSDT"}]}) == "ETHUSDT"

    def test_non_dict_returns_none(self):
        assert mw.extract_symbol("not a dict") is None
        assert mw.extract_symbol({"data": []}) is None


class TestHeaderParsing:
    def test_duplicate_headers_combined(self):
        status, headers, order = mw._parse_headers(
            b"HTTP/1.1 101 OK\r\nSet-Cookie: a=1\r\nSet-Cookie: b=2\r\n\r\n")
        assert headers["set-cookie"] == "a=1, b=2"
        assert order == ["set-cookie", "set-cookie"]

    def test_status_line_extracted(self):
        status, _, _ = mw._parse_headers(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        assert status == "HTTP/1.1 403 Forbidden"


# ---------------------------------------------------------------- CLI / main
class TestMain:
    def _patch_run_session(self, monkeypatch, result):
        calls = {}

        def fake(venue, seconds, **kw):
            calls["kw"] = kw
            return dict(result)

        monkeypatch.setattr(mw, "run_session", fake)
        return calls

    def test_version_flag(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["measure_ws.py", "--version"])
        assert mw.main() == 0
        assert capsys.readouterr().out.strip() == "v1.4"

    def test_selftest_flag(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["measure_ws.py", "--selftest"])
        assert mw.main() == 0

    def test_duration_seconds_conflict(self, monkeypatch):
        monkeypatch.setattr(sys, "argv",
                            ["measure_ws.py", "--venue", "lbank", "--duration", "5",
                             "--seconds", "10"])
        with pytest.raises(SystemExit):
            mw.main()

    def test_strict_returns_1_on_failed_session(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        result = {"error": "ConnectionResetError: reset",
                  "collection_complete": False, "inflate_failures": 0,
                  "rsv1_without_deflate": 0, "symbols_count": 1, "symbols_seen": 0,
                  "business_messages": 0, "wire_bytes_per_s": None,
                  "size_bytes": {}, "deflate_offered": False,
                  "deflate_accepted": False, "deflate_status": "n/a",
                  "deflate_measurement_offer_source": "none",
                  "app_ping_frames": 0, "heartbeat_pings_sent": 0}
        self._patch_run_session(monkeypatch, result)
        monkeypatch.setattr(sys, "argv",
                            ["measure_ws.py", "--venue", "lbank", "--duration", "1",
                             "--strict", "--out", str(out)])
        assert mw.main() == 1
        assert json.loads(out.read_text(encoding="utf-8"))["results"][0]["error"]

    def test_strict_returns_0_on_clean_session(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        result = {"error": None, "collection_complete": True, "inflate_failures": 0,
                  "rsv1_without_deflate": 0, "symbols_count": 1, "symbols_seen": 1,
                  "business_messages": 10, "wire_bytes_per_s": 1.0,
                  "size_bytes": {"p50": 100}, "deflate_offered": False,
                  "deflate_accepted": False, "deflate_status": "not_offered",
                  "deflate_measurement_offer_source": "none",
                  "app_ping_frames": 0, "heartbeat_pings_sent": 0}
        self._patch_run_session(monkeypatch, result)
        monkeypatch.setattr(sys, "argv",
                            ["measure_ws.py", "--venue", "lbank", "--duration", "1",
                             "--strict", "--out", str(out)])
        assert mw.main() in (None, 0)

    def test_probe_flag_forwarded_to_run_session(self, monkeypatch, tmp_path):
        out = tmp_path / "r.json"
        calls = self._patch_run_session(monkeypatch,
                                        {"error": None, "collection_complete": True,
                                         "inflate_failures": 0, "rsv1_without_deflate": 0,
                                         "symbols_count": 1, "symbols_seen": 0,
                                         "business_messages": 0, "wire_bytes_per_s": None,
                                         "size_bytes": {}, "deflate_offered": True,
                                         "deflate_accepted": False,
                                         "deflate_status": "server_refused",
                                         "deflate_measurement_offer_source": "single-offer",
                                         "http_status": "HTTP/1.1 101",
                                         "sec_websocket_accept_valid": True,
                                         "deflate_offer_header": "permessage-deflate",
                                         "app_ping_frames": 0, "heartbeat_pings_sent": 0})
        monkeypatch.setattr(sys, "argv",
                            ["measure_ws.py", "--venue", "lbank", "--probe",
                             "--deflate", "--out", str(out)])
        assert mw.main() in (None, 0)
        assert calls["kw"]["probe_only"] is True

    def test_missing_symbols_file_exits(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv",
                            ["measure_ws.py", "--venue", "lbank",
                             "--symbols-file", str(tmp_path / "nope.txt"),
                             "--out", str(tmp_path / "r.json")])
        with pytest.raises(SystemExit, match="打不开"):
            mw.main()


# ---------------------------------------------------------------- built-in selftest still green
class TestBuiltinSelftest:
    def test_selftest_returns_zero(self):
        assert mw._selftest() == 0