## 1. 交易日历模块

- [x] 1.1 在 `requirements.txt` 中添加 `exchange_calendars` 依赖并安装
- [x] 1.2 在 `scripts/fetch_daily_data.py` 中新增 `get_trading_days(start, end)` 函数，使用 `exchange_calendars` 的 XSHG 日历返回指定范围内的交易日列表
- [x] 1.3 添加 fallback 逻辑：当 `exchange_calendars` 未安装时，回退为简单的工作日过滤（Mon-Fri）并打印警告

## 2. CLI 参数扩展

- [x] 2.1 新增 `--range START END` 参数解析（YYYYMMDD 格式），用于指定采集的起止日期
- [x] 2.2 新增 `--days N` 参数解析，用于采集最近 N 个交易日
- [x] 2.3 新增 `--force` 参数，允许强制覆盖已有的 JSON 缓存文件
- [x] 2.4 新增 `--summary` 参数，在批量采集完成后自动生成周期汇总报告
- [x] 2.5 更新脚本顶部的 `__doc__` 文档字符串，反映所有新增参数用法

## 3. 批量采集逻辑

- [x] 3.1 将现有 `collect_all(date_str)` 重构为内部函数，新增 `collect_batch(dates, force=False)` 函数在外层循环调用
- [x] 3.2 在 `collect_batch` 中实现增量检查：跳过 `data/YYYYMMDD.json` 已存在的日期（`--force` 时跳过此检查）
- [x] 3.3 批量模式使用 `stock_zh_index_daily` 一次获取全量指数历史数据，替代逐日调用实时接口
- [x] 3.4 批量模式跳过 `stock_zh_a_spot()`（全A行情），涨跌比从涨停/跌停数据近似推算，避免 40 秒/日的耗时
- [x] 3.5 添加批量进度输出：`[3/10] 采集 20260212... ✅`（含当前位置、日期、状态）

## 4. 周期汇总报告生成

- [x] 4.1 新增 `generate_summary(dates, data_dir)` 函数，读取指定日期列表的 JSON 文件并聚合分析
- [x] 4.2 实现指数走势表：每日三大指数收盘价和涨跌幅表格
- [x] 4.3 实现情绪数据表：每日涨停/炸板/封板率/跌停/溢价率/连板/得分/阶段
- [x] 4.4 实现情绪走势曲线：ASCII 柱状图显示每日情绪得分变化
- [x] 4.5 实现龙头演进追踪：从每日涨停池的连板数据中提取同一股票的多日轨迹，输出演进路线
- [x] 4.6 实现题材轮动汇总：聚合每日涨停行业 TOP，识别主线题材的切换节点
- [x] 4.7 实现区间统计：交易天数、日均涨停、平均情绪得分、最高/最低得分、指数区间涨幅
- [x] 4.8 将汇总报告输出为 Markdown 文件保存至 `data/summary_START_END.md`，同时打印到控制台

## 5. 测试与文档

- [x] 5.1 测试单日模式不受影响：`python3 scripts/fetch_daily_data.py 20260225` 行为不变
- [x] 5.2 测试批量模式：`python3 scripts/fetch_daily_data.py --range 20260210 20260225` 正确采集 6 个交易日
- [x] 5.3 测试增量跳过：重复运行 `--range` 确认已采集日期被跳过
- [x] 5.4 测试 `--force` 覆盖：确认强制模式下重新采集所有日期
- [x] 5.5 测试 `--days 5`：确认正确识别最近 5 个交易日
- [x] 5.6 测试 `--summary`：确认生成的 Markdown 汇总包含所有必需章节
- [x] 5.7 更新 `project.md` 中数据采集脚本的用法说明
