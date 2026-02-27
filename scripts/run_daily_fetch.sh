#!/usr/bin/env bash
# 每日 0 点（或盘后）执行：采集「最近一个交易日」的数据并生成复盘草稿。
# 0 点跑时自动采上一交易日；盘中/收盘后跑则采当日。
# 用法：./scripts/run_daily_fetch.sh  或  bash scripts/run_daily_fetch.sh
# Cron 示例（每日 0 点）：0 0 * * * cd /path/to/trade && ./scripts/run_daily_fetch.sh

set -e
cd "$(dirname "$0")/.."

# 规避 macOS 上 NumPy 导入段错误（Accelerate 在 _mac_os_check 中的已知问题）
# 见：https://github.com/numpy/numpy/issues/15947 ；若仍出现 exit 139，见 scripts/TROUBLESHOOTING.md
[[ "$(uname -s)" = Darwin ]] && export NPY_DISABLE_CPU_FEATURES="${NPY_DISABLE_CPU_FEATURES:-AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL}"

# 优先使用项目虚拟环境（避免系统 Python 的 NumPy/Accelerate 段错误）
if [ -f .venv/bin/python3 ]; then
  exec .venv/bin/python3 scripts/fetch_daily_data.py "$@"
else
  exec python3 scripts/fetch_daily_data.py "$@"
fi
