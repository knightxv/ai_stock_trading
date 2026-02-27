## ADDED Requirements

### Requirement: Batch collection by date range
The system SHALL support collecting data for a range of trading days via `--range START END` arguments, where START and END are dates in YYYYMMDD format.

#### Scenario: Collect data for a specific date range
- **WHEN** user runs `python3 scripts/fetch_daily_data.py --range 20260210 20260225`
- **THEN** the script collects data for all trading days between 20260210 and 20260225 inclusive, saving each day as `data/YYYYMMDD.json`

#### Scenario: Range with non-trading days
- **WHEN** user specifies a range that includes weekends or holidays (e.g., Spring Festival 2/14-2/23)
- **THEN** the script automatically skips non-trading days and only collects data for valid trading sessions

### Requirement: Batch collection by recent N days
The system SHALL support collecting the most recent N trading days via `--days N` argument.

#### Scenario: Collect last 5 trading days
- **WHEN** user runs `python3 scripts/fetch_daily_data.py --days 5`
- **THEN** the script identifies the 5 most recent trading days (relative to today) and collects data for each

#### Scenario: N exceeds available history
- **WHEN** user specifies `--days 500` but AKShare only retains ~6 months of涨停 pool data
- **THEN** the script collects as many days as available and prints a warning about the data coverage limit

### Requirement: Incremental update with cache
The system SHALL skip data collection for dates that already have a `data/YYYYMMDD.json` file, unless `--force` is specified.

#### Scenario: Skip already collected dates
- **WHEN** user runs `--range 20260210 20260225` and `data/20260210.json` already exists
- **THEN** the script skips 20260210 and only collects data for dates without existing JSON files

#### Scenario: Force re-collection
- **WHEN** user runs `--range 20260210 20260225 --force`
- **THEN** the script re-collects and overwrites data for ALL dates in the range, including those with existing JSON files

### Requirement: Trading calendar integration
The system SHALL use a reliable trading calendar to determine valid A-share trading days.

#### Scenario: Identify trading days correctly
- **WHEN** the system resolves trading days for February 2026
- **THEN** it correctly excludes weekends (Saturdays, Sundays) and Spring Festival holidays (2/14-2/23), returning only actual trading sessions

#### Scenario: Calendar library unavailable
- **WHEN** `exchange_calendars` is not installed
- **THEN** the script falls back to a basic weekday filter (Mon-Fri) and prints a warning that holiday detection is limited

### Requirement: Batch progress reporting
The system SHALL display progress during batch collection.

#### Scenario: Progress output during batch run
- **WHEN** collecting data for 10 trading days
- **THEN** the script prints progress like `[3/10] 采集 20260212... ✅` for each day, showing current position and status
