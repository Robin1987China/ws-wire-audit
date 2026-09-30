#!/bin/sh
# 2026-09-30 加厚样本：Bybit / Kraken 各补 2 场（600 s），把 2026-09-29 的 n=1 提到 n=3。
# 目的：观察跨场次波动；不修改任何既有场次文件（04–10 保持原样）。
# 口径与 2026-09-29 既有场次完全一致：
#   - 业务消息 = 非控制帧/非心跳/非回执的入站数据帧（只统计入站，不做分片重组）；
#   - wire = 帧字节（含帧头，不含 TLS/TCP/IP）；payload = 解压后；
#   - 压缩默认 not_offered（不做 offer）；
#   - 订阅之后起算 600 s；每所 1 条连接、无重连；会话顺序执行、不并发。
# 复现前提：HTTPS_PROXY/HTTP_PROXY=http://<proxy-host>:<port>（HTTP CONNECT）。
#   600 s 窗口内不得并发其它网络任务（本脚本不含任何其它网络动作）。
# 出口：与 2026-09-29 同为单一出口（见随附报告的方法说明）。
set -e
SF=symbols159-ext-20260929.json

run() {  # $1=venue  $2=outfile
  echo "[$(date '+%F %T')] START $1 -> $2"
  python3 measure_ws.py --venue "$1" --symbols-file $SF --duration 600 --out "examples/$2"
  echo "[$(date '+%F %T')] END   $1 -> $2"
}

run bybit  11-bybit-103pairs-600s-20260930-r2.json
sleep 10
run kraken 12-kraken-20pairs-600s-20260930-r2.json
sleep 10
run bybit  13-bybit-103pairs-600s-20260930-r3.json
sleep 10
run kraken 14-kraken-20pairs-600s-20260930-r3.json
echo "[$(date '+%F %T')] DONE"
