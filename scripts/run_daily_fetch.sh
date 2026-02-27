#!/usr/bin/env bash
# 每日 0 点（或盘后）执行：采集「最近一个交易日」的数据并生成复盘草稿。
# 0 点跑时自动采上一交易日；盘中/收盘后跑则采当日。
# 用法：./scripts/run_daily_fetch.sh  或  bash scripts/run_daily_fetch.sh
# Cron 示例（每日 0 点）：0 0 * * * cd /path/to/trade && ./scripts/run_daily_fetch.sh

set -e
cd "$(dirname "$0")/.."
exec python3 scripts/fetch_daily_data.py
