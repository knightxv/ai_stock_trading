#!/usr/bin/env bash
# 在 macOS 上配置项目 venv，使 NumPy 链接 OpenBLAS 以规避 Accelerate 导致的 exit 139。
# 用法：在项目根目录执行  ./scripts/setup_venv_macos.sh
# 依赖：Homebrew（brew）、Xcode Command Line Tools（编译 NumPy 需用）

set -e
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != Darwin ]]; then
  echo "本脚本仅适用于 macOS，当前系统无需运行。"
  exit 0
fi

echo "=== 1. 检查 Homebrew 与 OpenBLAS ==="
if ! command -v brew &>/dev/null; then
  echo "未检测到 Homebrew，请先安装：https://brew.sh"
  exit 1
fi
brew list openblas &>/dev/null || brew install openblas
OPENBLAS_PREFIX="$(brew --prefix openblas)"
echo "OpenBLAS: $OPENBLAS_PREFIX"

echo ""
echo "=== 2. 创建/使用虚拟环境 .venv ==="
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  echo "已创建 .venv"
else
  echo "已存在 .venv"
fi
# 使用 venv 内的 pip/python
PIP=".venv/bin/pip"
PYTHON=".venv/bin/python"

echo ""
echo "=== 3. 升级 pip 并安装构建依赖 ==="
"$PIP" install -U pip setuptools wheel

echo ""
echo "=== 4. 卸载现有 numpy 并用 OpenBLAS 从源码安装 NumPy ==="
"$PIP" uninstall -y numpy 2>/dev/null || true
"$PIP" cache remove numpy 2>/dev/null || true

export OPENBLAS="$OPENBLAS_PREFIX"
echo "正在从源码编译 NumPy（链接 OpenBLAS），可能需要数分钟…"
if ! "$PIP" install numpy --no-binary numpy --no-cache-dir; then
  echo ""
  echo "⚠ 自动构建失败。请确保已安装 Xcode Command Line Tools： xcode-select --install"
  echo "若仍失败，可参考 scripts/TROUBLESHOOTING.md 中的「手动用 OpenBLAS 安装 NumPy」步骤。"
  exit 1
fi

echo ""
echo "=== 5. 安装项目依赖 ==="
"$PIP" install -r requirements.txt

echo ""
echo "=== 6. 验证 NumPy 与脚本 ==="
if ! "$PYTHON" -c "import numpy; import pandas; import akshare; print('numpy:', numpy.__version__, '| 导入正常')"; then
  echo "验证失败，请检查上方报错。"
  exit 1
fi
if "$PYTHON" scripts/fetch_daily_data.py --print-only 2>&1 | head -5; then
  echo ""
  echo "✅ 配置完成。以后请使用以下方式运行采集脚本："
  echo "   .venv/bin/python scripts/fetch_daily_data.py --days 5 --summary"
  echo "   或:  ./scripts/run_daily_fetch.sh"
else
  echo "脚本试运行未完整执行（可能仅因无网络或接口限制），若本地曾出现 exit 139，请再执行一次："
  echo "   .venv/bin/python scripts/fetch_daily_data.py --days 5 --summary"
fi
