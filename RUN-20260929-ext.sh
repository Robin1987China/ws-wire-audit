#!/bin/sh
# 2026-09-29 同口径扩样本测量（bybit / okx / kraken）。
# 复现：在装有 measure_ws.py v1.4 的目录内、固定出口下按序执行。
# 单连接、无重连、无并发；每所之间 sleep 10，与既有 LBank/Binance 场次口径一致
# （业务消息=非控制/非心跳/非回执的入站数据帧；wire=帧字节；压缩默认 not_offered）。
# 出口：见随附报告的方法说明；本脚本需 HTTPS_PROXY=http://<proxy-host>:<port>（HTTP CONNECT）。
set -e
SF=symbols159-ext-20260929.json
echo "[$(date '+%F %T')] bybit 600s"
python3 measure_ws.py --venue bybit  --symbols-file $SF --duration 600 --out examples/04-bybit-103pairs-600s-20260929.json
sleep 10
echo "[$(date '+%F %T')] okx 600s"
python3 measure_ws.py --venue okx    --symbols-file $SF --duration 600 --out examples/05-okx-110pairs-600s-20260929.json
sleep 10
echo "[$(date '+%F %T')] kraken 600s"
python3 measure_ws.py --venue kraken --symbols-file $SF --duration 600 --out examples/06-kraken-20pairs-600s-20260929.json
sleep 10
echo "[$(date '+%F %T')] deflate ladder probes (60s each, 3 symbols)"
python3 measure_ws.py --venue bybit  --symbols BTC,ETH,SOL --duration 60 --deflate --deflate-ladder --out examples/07-bybit-deflate-ladder-20260929.json
python3 measure_ws.py --venue okx    --symbols BTC,ETH,SOL --duration 60 --deflate --deflate-ladder --out examples/08-okx-deflate-ladder-20260929.json
python3 measure_ws.py --venue kraken --symbols BTC,ETH,SOL --duration 60 --deflate --deflate-ladder --out examples/09-kraken-deflate-ladder-20260929.json
echo "[$(date '+%F %T')] DONE"
