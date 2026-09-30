#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""interleave_ab.py —— 同窗交错 A/B 对照采样驱动器（只读公开行情 WS）。

要解决的问题（见随附报告 §3 / E31）
    同一场所自身跨场次波动可达 +80%（Bybit）/ +116%（Kraken），使**小间距**的
    场所间比较不可判（例：n=1 时 "Bybit > OKX" 在 Bybit 自身区间跨过 OKX 时
    不成立）。本脚本用**同窗交错采样**把"时段/行情节奏"这个混杂因素压下去：
    在同一时间窗内**交替**采样 A、B（A 60 s → B 60 s → A 60 s → …），每段
    一条**新连接**，段内**不并发**任何其它网络任务，并逐段记录开始/结束时间戳。

口径（与既有场次逐条一致，见 SPEC §0 四声明）
    1. 业务消息 = 非控制帧/非心跳/非回执的入站数据帧；只统计入站，不做分片重组。
    2. 字节：payload = 解压后；wire = 读到的 WS 帧长（含帧头）。均不含 TLS/TCP/IP，不测上行。
    3. 压缩：默认 not_offered（测量会话不 offer）。
    4. 出口与窗口：订阅之后起算 duration 秒；每段 1 条连接、无重连；段顺序执行、不并发。

用法
    python3 interleave_ab.py --rounds 6 --duration 60 \
        --a bybit --b okx --symbols-file symbols159-ext-20260929.json \
        --out examples/15-interleaved-bybit-okx-20260930.json

一键：sh RUN-20260930-interleave.sh
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time

TZ8 = datetime.timezone(datetime.timedelta(hours=8))
TZ_UTC = datetime.timezone.utc


def iso8(ts):
    return datetime.datetime.fromtimestamp(ts, TZ8).isoformat()


def iso_utc(ts):
    return datetime.datetime.fromtimestamp(ts, TZ_UTC).isoformat()


def run_one(script, venue, symbols_file, duration, outpath, proxy, extra):
    """跑一段（一个进程、一条连接）。返回 (info_dict, res_or_None)。

    用子进程调用 measure_ws.py，与既有 RUN-*.sh 完全同一条命令口径。
    """
    cmd = [sys.executable, script, "--venue", venue,
           "--symbols-file", symbols_file, "--duration", str(duration),
           "--out", outpath]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd += list(extra)
    t0 = time.time()
    env = dict(os.environ)
    if proxy:
        env["HTTPS_PROXY"] = proxy
        env["HTTP_PROXY"] = proxy
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    t1 = time.time()
    info = {
        "cmd": " ".join(cmd),
        "t_start_epoch": round(t0, 3),
        "t_start": iso8(t0),
        "t_start_utc": iso_utc(t0),
        "t_end_epoch": round(t1, 3),
        "t_end": iso8(t1),
        "t_end_utc": iso_utc(t1),
        "wall_clock_s": round(t1 - t0, 3),
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-500:],
    }
    res = None
    if os.path.exists(outpath):
        try:
            with open(outpath) as fh:
                doc = json.load(fh)
            results = doc.get("results") or []
            res = results[0] if results else None
        except Exception as e:  # noqa: BLE001
            info["parse_error"] = f"{type(e).__name__}: {e}"
    return info, res


def summary_of(res):
    """从一段的完整结果里抽取配对统计要用的关键字段（缺则 None）。"""
    if not res:
        return {"complete": False, "error": "no_result"}
    return {
        "complete": bool(res.get("collection_complete")),
        "error": res.get("error"),
        "business_messages": res.get("business_messages"),
        "msg_per_s": res.get("msg_per_s"),
        "wire_bytes_per_s": res.get("wire_bytes_per_s"),
        "payload_bytes_per_s": res.get("payload_bytes_per_s"),
        "wire_bytes_total_per_s": res.get("wire_bytes_total_per_s"),
        "size_p50": (res.get("size_bytes") or {}).get("p50"),
        "symbols_seen": res.get("symbols_seen"),
        "symbols_count": res.get("symbols_count"),
        "subscribe_acks": res.get("subscribe_acks"),
        "subscribe_errors": res.get("subscribe_errors"),
        "control_frames": res.get("control_frames"),
        "app_ping_frames": res.get("app_ping_frames"),
        "venue_heartbeat_frames": res.get("venue_heartbeat_frames"),
        "inflate_failures": res.get("inflate_failures"),
        "deflate_status": res.get("deflate_status"),
        "elapsed_s": res.get("elapsed_s"),
        "reconnects": res.get("reconnects"),
    }


def med(xs):
    ys = sorted(x for x in xs if x is not None)
    if not ys:
        return None
    n = len(ys)
    return ys[n // 2] if n % 2 else round((ys[n // 2 - 1] + ys[n // 2]) / 2, 4)


def rng(xs):
    ys = [x for x in xs if x is not None]
    if not ys:
        return None
    lo, hi = min(ys), max(ys)
    return {"min": lo, "max": hi,
            "range_pct": round((hi / lo - 1) * 100, 2) if lo else None}


def stats_block(rows, key):
    xs = [r.get(key) for r in rows]
    return {"median": med(xs), "min": min([x for x in xs if x is not None], default=None),
            "max": max([x for x in xs if x is not None], default=None),
            "range": rng(xs), "values": xs}


def sign(x):
    if x is None:
        return None
    return 1 if x > 0 else (-1 if x < 0 else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--a", default="bybit")
    ap.add_argument("--b", default="okx")
    ap.add_argument("--order", default="ab", choices=["ab", "ba"],
                    help="每轮的先后（ab=A先，ba=B先）")
    ap.add_argument("--symbols-file", default="symbols159-ext-20260929.json")
    ap.add_argument("--script", default="measure_ws.py")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or "")
    ap.add_argument("--out", default="examples/15-interleaved-bybit-okx-20260930.json")
    ap.add_argument("--rawdir", default=None, help="逐段原始 JSON 存放目录（默认临时目录）")
    ap.add_argument("--keep-raw", action="store_true",
                    help="把逐段原始 JSON 与时间戳落到 --rawdir（默认不落盘）")
    ap.add_argument("--extra", default="", help="追加给 measure_ws.py 的额外参数（空格分隔）")
    a = ap.parse_args()

    extra = a.extra.split() if a.extra else []
    rawdir = a.rawdir or os.path.join(tempfile.gettempdir(), "interleave-ab-raw")
    os.makedirs(rawdir, exist_ok=True)

    sessions = []
    print(f"[{iso8(time.time())}] interleave start: rounds={a.rounds} dur={a.duration}s "
          f"A={a.a} B={a.b} order={a.order} proxy={a.proxy or 'direct'}")
    for r in range(1, a.rounds + 1):
        seq = [a.a, a.b] if a.order == "ab" else [a.b, a.a]
        for v in seq:
            outpath = os.path.join(rawdir, f"{v}_r{r}.json")
            info, res = run_one(a.script, v, a.symbols_file, a.duration, outpath, a.proxy, extra)
            rec = {"round": r, "venue": v, **info, "summary": summary_of(res)}
            if res is not None:
                rec["result"] = res
            sessions.append(rec)
            s = rec["summary"]
            print(f"[{iso8(info['t_end_epoch'])}] r{r} {v:6s} "
                  f"complete={s.get('complete')} msg/s={s.get('msg_per_s')} "
                  f"wire/s={s.get('wire_bytes_per_s')} err={s.get('error')}")
            if a.keep_raw:
                with open(os.path.join(rawdir, "timing.tsv"), "a") as fh:
                    fh.write(f"{r}\t{v}\t{info['t_start_epoch']}\t{info['t_end_epoch']}\t{outpath}\n")

    # ---- 配对（只纳入 collection_complete=True 且 error 为空的段）----
    def by_round(venue):
        return {s["round"]: s for s in sessions
                if s["venue"] == venue and s["summary"].get("complete")
                and not s["summary"].get("error")}

    A, B = by_round(a.a), by_round(a.b)
    rounds = []
    for r in sorted(set(A) & set(B)):
        sa, sb = A[r]["summary"], B[r]["summary"]
        row = {
            "round": r,
            "a": {"venue": a.a, **sa, "t_start": A[r]["t_start"], "t_end": A[r]["t_end"]},
            "b": {"venue": a.b, **sb, "t_start": B[r]["t_start"], "t_end": B[r]["t_end"]},
            "pair_diff_ab": {},
            "pair_ratio_ab": {},
        }
        for k in ("wire_bytes_per_s", "payload_bytes_per_s", "msg_per_s"):
            x, y = sa.get(k), sb.get(k)
            row["pair_diff_ab"][k] = round(x - y, 4) if (x is not None and y is not None) else None
            row["pair_ratio_ab"][k] = round(x / y, 5) if (x and y) else None
        rounds.append(row)

    def pair_stats(key):
        diffs = [row["pair_diff_ab"][key] for row in rounds]
        ratios = [row["pair_ratio_ab"][key] for row in rounds]
        sgn = [sign(d) for d in diffs]
        consistent = bool(sgn) and None not in sgn and len(set(sgn)) == 1 and sgn[0] != 0
        return {
            "key": key,
            "n_pairs": len(rounds),
            "diff_values": diffs,
            "diff_median": med(diffs),
            "diff_min": min([d for d in diffs if d is not None], default=None),
            "diff_max": max([d for d in diffs if d is not None], default=None),
            "ratio_values": ratios,
            "ratio_median": med(ratios),
            "signs": sgn,
            "sign_consistent": consistent,
            "flips": sum(1 for i in range(1, len(sgn)) if sgn[i] != sgn[i - 1]),
        }

    paired = {k: pair_stats(k) for k in ("wire_bytes_per_s", "msg_per_s", "payload_bytes_per_s")}

    # 判据（机械计算，不预设）：配对差符号全轮一致 → 可判；出现翻转 → 不可判。
    w = paired["wire_bytes_per_s"]
    if w["n_pairs"] == 0:
        verdict = "无有效配对，无法判定"
    elif w["n_pairs"] < 3:
        verdict = f"样本不足（n={w['n_pairs']}），不下判"
    elif w["sign_consistent"]:
        verdict = (f"可判（本轮 n={w['n_pairs']}：wire B/s 的 A−B 符号全轮一致，"
                   f"中位比值 A/B={w['ratio_median']}）")
    else:
        verdict = (f"不可判（本轮 n={w['n_pairs']}：wire B/s 的 A−B 符号翻转 {w['flips']} 次）")

    artifact = {
        "generated_at": iso8(time.time()),
        "experiment": "同窗交错 A/B 对照（interleaved same-window alternating sampling）",
        "driver": "interleave_ab.py",
        "script_version": (sessions[0]["result"].get("script_version")
                           if sessions and sessions[0].get("result") else None),
        "design": {
            "a": a.a, "b": a.b, "rounds": a.rounds, "duration_per_session_s": a.duration,
            "order_per_round": " -> ".join([a.a, a.b] if a.order == "ab" else [a.b, a.a]),
            "symbols_file": a.symbols_file,
            "implementation": "每段一个独立进程、一条新连接；两所交替；段内/段间不并发其它网络任务",
            "proxy": a.proxy or "direct",
        },
        "caliber": {
            "business_message": "一条入站数据帧，剔除控制帧/应用心跳/订阅回执；只统计入站；不做分片重组",
            "bytes": "payload=解压后；wire=WS 帧长（含帧头）；均不含 TLS/TCP/IP；不测上行",
            "compression": "not_offered（测量会话不 offer permessage-deflate）",
            "window": f"订阅之后起算 {a.duration} s；每段 1 连接、无重连；段顺序执行、不并发",
        },
        "sessions": sessions,
        "rounds": rounds,
        "per_venue_stats": {
            a.a: {k: stats_block([row["a"] for row in rounds], k)
                  for k in ("business_messages", "msg_per_s", "wire_bytes_per_s", "payload_bytes_per_s")},
            a.b: {k: stats_block([row["b"] for row in rounds], k)
                  for k in ("business_messages", "msg_per_s", "wire_bytes_per_s", "payload_bytes_per_s")},
        },
        "paired": paired,
        "verdict_wire_bytes_per_s": verdict,
    }

    with open(a.out, "w") as fh:
        json.dump(artifact, fh, ensure_ascii=False, indent=1)
    print(f"\n[{iso8(time.time())}] wrote {a.out}")
    print("verdict:", verdict)
    print("pair wire diff:", w["diff_values"], "ratios:", w["ratio_values"])


if __name__ == "__main__":
    main()
