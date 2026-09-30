#!/bin/sh
# 2026-09-30 同窗交错 A/B 对照实验（Bybit vs OKX）—— 一键复跑。
#
# 目的：把"时段/行情节奏"这个混杂因素压到最小，检验**小间距**排序能否可判。
# 设计：同一时间窗内交替采样 A/B（A 60 s → B 60 s → A 60 s → …），每段一条新连接；
#       每段记录开始/结束时间戳；段顺序执行、**不并发**其它网络任务。
# 口径：与既有场次逐条一致（业务消息=非控制/非心跳/非回执的入站数据帧；payload=解压后、
#       wire=帧字节；压缩 not_offered）；订阅之后起算 60 s；单连接、无重连。
#
# 复现前提：HTTPS_PROXY/HTTP_PROXY=http://<proxy-host>:<port>（HTTP CONNECT）。
#   ⚠ 整个采样期间（约 12 分钟）不得并发其它网络任务。
# 产出：examples/15-interleaved-bybit-okx-20260930.json（含每段原始 summary + 配对统计 + 判据）。
# 说明：本脚本**新增**，不覆盖 RUN-20260929-ext.sh / RUN-20260930-thicken.sh。
set -e
cd "$(dirname "$0")"

: "${ROUNDS:=6}"
: "${DURATION:=60}"
: "${SYMBOLS_FILE:=symbols159-ext-20260929.json}"
: "${OUT:=examples/15-interleaved-bybit-okx-20260930.json}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://<proxy-host>:<port>}"

echo "[$(date '+%F %T')] interleaved A/B: rounds=$ROUNDS duration=${DURATION}s proxy=$HTTPS_PROXY"
python3 interleave_ab.py \
  --rounds "$ROUNDS" --duration "$DURATION" \
  --a bybit --b okx --order ab \
  --symbols-file "$SYMBOLS_FILE" \
  --proxy "$HTTPS_PROXY" \
  --rawdir <workdir> \
  --out "$OUT"
echo "[$(date '+%F %T')] DONE -> $OUT"
