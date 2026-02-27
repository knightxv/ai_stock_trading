## ADDED Requirements

### Requirement: Generate period summary report
The system SHALL generate an aggregated summary report for a specified date range, combining data from individual daily JSON files.

#### Scenario: Generate summary for a date range
- **WHEN** user runs `python3 scripts/fetch_daily_data.py --range 20260210 20260225 --summary`
- **THEN** the script generates a Markdown summary report at `data/summary_20260210_20260225.md` and prints the summary to console

#### Scenario: Summary with missing daily data
- **WHEN** user requests a summary but some dates in the range have no JSON data
- **THEN** the script first collects missing dates, then generates the summary including all dates

### Requirement: Index trend summary
The period summary report SHALL include a table showing each trading day's index closing prices and percentage changes for the three major indices (上证指数, 深证成指, 创业板指).

#### Scenario: Index table in summary
- **WHEN** summary is generated for 20260210-20260225
- **THEN** the report contains a table with columns: 日期, 上证指数(涨跌幅), 深证成指(涨跌幅), 创业板指(涨跌幅), and a row for each trading day

### Requirement: Emotion trend summary
The period summary report SHALL include each day's emotion score, emotion stage, and a visual trend indicator (ASCII bar chart).

#### Scenario: Emotion curve in summary
- **WHEN** summary covers 6 trading days with scores [7.14, 6.33, 6.55, 5.56, 6.57, 7.24]
- **THEN** the report displays a bar chart showing the score progression and labels each day's emotion stage (高潮期/回暖期/退潮期 etc.)

### Requirement: Sentiment core data table
The period summary report SHALL include a daily sentiment breakdown table with columns: 日期, 涨停家数, 炸板家数, 封板率, 跌停家数, 昨涨停溢价率, 最高连板, 情绪得分, 阶段.

#### Scenario: Sentiment table completeness
- **WHEN** summary is generated for any date range
- **THEN** every trading day in the range has a complete row with all 8 sentiment metrics

### Requirement: Leader stock evolution tracking
The period summary report SHALL trace the evolution of leading stocks (龙头) across the period, showing how their streak counts progress day by day.

#### Scenario: Track a leader across multiple days
- **WHEN** 豫能控股 appears as 2板 on 2/12, 3板 on 2/13, 4板 on 2/24, 5板 on 2/25
- **THEN** the summary shows a leader evolution table: `豫能控股: 2/12(2板) → 2/13(3板) → 2/24(4板) → 2/25(5板)`

### Requirement: Theme sector rotation summary
The period summary report SHALL aggregate the top industries from涨停 pool data across all days, showing which sectors had the most涨停 stocks and how sector leadership rotated.

#### Scenario: Sector rotation across the period
- **WHEN** 影视院线 led on 2/10, 通用设备 on 2/12, 农化制品 on 2/24-2/25
- **THEN** the summary identifies the main theme rotation: `影视院线 → 通用设备 → 农化制品` with涨停 counts per day

### Requirement: Period statistics summary
The period summary report SHALL include aggregate statistics: total trading days, average daily涨停 count, average emotion score, period high/low emotion scores, index period return.

#### Scenario: Aggregate stats
- **WHEN** summary covers 6 trading days
- **THEN** the report shows: 交易天数=6, 日均涨停=61.7家, 平均情绪=6.56分, 最高=7.24(02/25), 最低=5.56(02/13), 上证区间涨幅=+0.46%
