# fetch_daily_data.py 故障排查

## 一、Exit 139（段错误 / Segmentation fault）

### 现象

执行 `python3 scripts/fetch_daily_data.py --days 5 --summary` 时进程直接退出，退出码 **139**，控制台无报错信息。

### 原因

在 **macOS（尤其是 Apple Silicon）** 上，系统自带的 NumPy 或通过 `pip install` 安装的 NumPy 会链接到 Apple 的 **Accelerate** 库。NumPy 在导入时会执行 `_mac_os_check()`，内部调用 `polyfit`/线性代数，在部分 macOS + NumPy 组合下会触发 **Accelerate 的已知 bug**，导致段错误（而非抛出 Python 异常）。  
相关讨论： [numpy#15947](https://github.com/numpy/numpy/issues/15947)、[Apple 开发者论坛](https://developer.apple.com/forums/thread/772620)。

### 解决方案（任选其一）

1. **一键配置：使用项目提供的 macOS 脚本（推荐）**  
   在项目根目录执行（需已安装 [Homebrew](https://brew.sh)）：
   ```bash
   chmod +x scripts/setup_venv_macos.sh
   ./scripts/setup_venv_macos.sh
   ```
   脚本会：安装/检查 OpenBLAS、创建或使用 `.venv`、在 venv 内用 OpenBLAS 从源码编译安装 NumPy、再安装 `requirements.txt`。完成后用以下方式运行采集：
   ```bash
   .venv/bin/python scripts/fetch_daily_data.py --days 5 --summary
   # 或
   ./scripts/run_daily_fetch.sh
   ```
   若编译 NumPy 时报错，请先安装 Xcode Command Line Tools：`xcode-select --install`。

2. **仅用虚拟环境 + 默认依赖（可能仍 139）**  
   若尚未出现 139，可先尝试：
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python scripts/fetch_daily_data.py --days 5 --summary
   ```
   若虚拟环境中的 NumPy 仍为 pip 默认二进制（链到 Accelerate）且继续 139，请改用方案 1。

3. **手动在项目 venv 内用 OpenBLAS 安装 NumPy（进阶）**  
   已安装 Homebrew 与 OpenBLAS 时，在项目根目录：
   ```bash
   brew install openblas
   source .venv/bin/activate
   pip uninstall -y numpy 2>/dev/null || true
   pip cache remove numpy
   OPENBLAS="$(brew --prefix openblas)" pip install numpy --no-binary numpy --no-cache-dir
   pip install -r requirements.txt
   ```
   然后再运行脚本。编译需 Xcode Command Line Tools。

4. **脚本内已做的缓解（可能无效）**  
   脚本在导入 akshare/pandas 前已设置 `NPY_DISABLE_CPU_FEATURES`（针对 Intel AVX512）。在 Apple Silicon 上该变量通常无效，崩溃仍可能发生，此时请以方案 1 或 3 为准。

---

## 二、ModuleNotFoundError: No module named 'akshare'

### 现象

```
ModuleNotFoundError: No module named 'akshare'
```

### 原因

当前使用的 Python 解释器所在环境中未安装 akshare（或未激活安装了 akshare 的虚拟环境）。

### 解决方案

在项目根目录下使用虚拟环境并安装依赖：

```bash
source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_daily_data.py --days 5 --summary
```

或直接用该虚拟环境的 Python 运行：

```bash
.venv/bin/python scripts/fetch_daily_data.py --days 5 --summary
```

---

## 三、exchange_calendars 未安装 / 日期回退为工作日

### 现象

控制台出现：

```
⚠ exchange_calendars 未安装，仅按工作日过滤（节假日可能误判）
```
或：
```
⚠ 日期超出 exchange_calendars 范围，回退为工作日过滤
```

### 原因

- 未安装 `exchange_calendars`；或  
- 使用的交易所日历不包含指定日期范围，脚本回退为按「工作日」过滤，节假日可能被误判为交易日。

### 解决方案

安装依赖即可（已在 `requirements.txt` 中）：

```bash
pip install exchange_calendars>=4.5.0
```

安装后，脚本会优先用 A 股交易日历判断日期，避免节假日误判。

---

## 四、其他常见报错

| 报错类型 | 可能原因 | 建议 |
|----------|----------|------|
| 网络超时 / 连接错误 | 接口限流、网络不稳定 | 稍后重试；或分多天单日采集 |
| AKShare 接口返回空或报错 | 数据源临时不可用或接口变更 | 查看 AKShare 版本与文档，必要时升级：`pip install -U akshare` |
| 某日 JSON 已存在，跳过采集 | 默认行为为增量、不覆盖 | 需要重采时加 `--force`：`python scripts/fetch_daily_data.py --range 20260201 20260225 --force` |

---

## 五、推荐运行方式

- **日常使用**：在项目根目录使用包装脚本（会优先使用已配置的 `.venv`）：
  ```bash
  ./scripts/run_daily_fetch.sh
  ```
  或显式使用虚拟环境：
  ```bash
  .venv/bin/python scripts/fetch_daily_data.py --days 5 --summary
  ```
