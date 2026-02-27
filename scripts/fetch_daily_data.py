"""
A股每日复盘数据自动采集脚本

用法：
    python3 scripts/fetch_daily_data.py                          # 采集今天的数据
    python3 scripts/fetch_daily_data.py 20260225                 # 采集指定日期
    python3 scripts/fetch_daily_data.py --range 20260210 20260225            # 批量采集日期范围
    python3 scripts/fetch_daily_data.py --days 5                             # 采集最近5个交易日
    python3 scripts/fetch_daily_data.py --range 20260210 20260225 --summary  # 批量采集并生成汇总
    python3 scripts/fetch_daily_data.py --range 20260210 20260225 --force    # 强制重新采集（忽略缓存）
    python3 scripts/fetch_daily_data.py --print-only                         # 仅打印，不生成文件

数据源：AKShare（新浪 + 东方财富）
已验证可用接口（2026-02）：
  - stock_zh_index_spot_sina    指数实时（新浪源）
  - stock_zh_index_daily        指数历史日线
  - stock_zh_a_spot             全A实时行情（新浪源）
  - stock_zt_pool_em            涨停股池（东财涨停专题）
  - stock_zt_pool_zbgc_em       炸板股池
  - stock_zt_pool_dtgc_em       跌停股池
  - stock_zt_pool_previous_em   昨日涨停股池
"""

from __future__ import annotations

import argparse
import json
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd

warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# 交易日历
# ---------------------------------------------------------------------------

try:
    import exchange_calendars as xcals
    _XSHG = xcals.get_calendar("XSHG")
    _HAS_XCALS = True
except ImportError:
    _HAS_XCALS = False


def get_trading_days(start: str, end: str) -> list[str]:
    """返回 [start, end] 范围内的 A 股交易日列表（YYYYMMDD 字符串）。"""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    if _HAS_XCALS:
        try:
            sessions = _XSHG.sessions_in_range(s, e)
            return [d.strftime("%Y%m%d") for d in sessions]
        except Exception:
            pass
    if not _HAS_XCALS:
        print("  ⚠ exchange_calendars 未安装，仅按工作日过滤（节假日可能误判）")
    else:
        print("  ⚠ 日期超出 exchange_calendars 范围，回退为工作日过滤")
    days = pd.bdate_range(s, e)
    return [d.strftime("%Y%m%d") for d in days]


def get_recent_trading_days(n: int) -> list[str]:
    """返回距今最近的 N 个交易日。"""
    today = pd.Timestamp(datetime.now().date())
    lookback = today - pd.Timedelta(days=max(n * 3, 60))
    all_days = get_trading_days(lookback.strftime("%Y%m%d"), today.strftime("%Y%m%d"))
    return all_days[-n:]


# ---------------------------------------------------------------------------
# 情绪评分映射
# ---------------------------------------------------------------------------

def score_zt_count(n: int) -> float:
    if n < 20: return max(1, n / 10)
    if n < 40: return 3 + (n - 20) / 20 * 2
    if n < 70: return 5 + (n - 40) / 30 * 2
    if n < 100: return 7 + (n - 70) / 30 * 2
    return min(10, 9 + (n - 100) / 50)

def score_seal_rate(rate: float) -> float:
    if rate < 40: return max(1, rate / 40 * 3)
    if rate < 55: return 4 + (rate - 40) / 15
    if rate < 70: return 6 + (rate - 55) / 15
    if rate < 85: return 8 + (rate - 70) / 15
    return min(10, 9 + (rate - 85) / 15)

def score_premium(pct: float) -> float:
    if pct < -5: return 1
    if pct < -2: return 1 + (pct + 5) / 3 * 2
    if pct < 0: return 4 + (pct + 2) / 2
    if pct < 3: return 6 + pct / 3
    if pct < 6: return 8 + (pct - 3) / 3
    return min(10, 9 + (pct - 6) / 4)

def score_max_streak(n: int) -> float:
    mapping = {0: 1, 1: 2, 2: 3, 3: 5, 4: 7, 5: 7, 6: 8, 7: 8}
    if n in mapping: return mapping[n]
    return min(10, 9 + (n - 7) / 3)

def score_rise_fall_ratio(ratio: float) -> float:
    if ratio < 0.3: return 1
    if ratio < 0.6: return 2 + (ratio - 0.3) / 0.3
    if ratio < 1: return 4 + (ratio - 0.6) / 0.4 * 2
    if ratio < 2: return 6 + (ratio - 1)
    if ratio < 3: return 8 + (ratio - 2)
    return min(10, 9 + (ratio - 3) / 2)

def score_dt_count(n: int) -> float:
    if n == 0: return 10
    if n <= 5: return 8 + (5 - n) / 5
    if n <= 10: return 6 + (10 - n) / 5 * 2
    if n <= 20: return 4 + (20 - n) / 10 * 2
    if n <= 30: return 2 + (30 - n) / 10
    return 1

def calc_emotion_score(zt_count, seal_rate, premium, max_streak, rf_ratio, dt_count):
    scores = {
        "涨停家数": score_zt_count(zt_count),
        "封板率": score_seal_rate(seal_rate),
        "昨涨停溢价": score_premium(premium),
        "连板高度": score_max_streak(max_streak),
        "涨跌比": score_rise_fall_ratio(rf_ratio),
        "跌停反指": score_dt_count(dt_count),
    }
    weights = {"涨停家数": 0.15, "封板率": 0.15, "昨涨停溢价": 0.25,
               "连板高度": 0.15, "涨跌比": 0.15, "跌停反指": 0.15}
    total = sum(scores[k] * weights[k] for k in scores)
    return round(total, 2), {k: round(v, 1) for k, v in scores.items()}

def emotion_stage(score: float) -> str:
    if score < 3: return "冰点期"
    if score < 5: return "退潮期"
    if score < 7: return "回暖期"
    if score < 9: return "高潮期"
    return "亢奋期"

def emotion_stage_full(score: float) -> str:
    if score < 3: return "冰点期（1-3分）—— 极度低迷，空仓观望"
    if score < 5: return "退潮/修复期（3-5分）—— 亏钱效应为主，控仓关注转折"
    if score < 7: return "回暖/上升期（5-7分）—— 赚钱效应回归，跟随龙头"
    if score < 9: return "高潮期（7-9分）—— 赚钱效应强烈，注意见顶信号"
    return "极度亢奋（9-10分）—— 警惕退潮，开始防守"


# ---------------------------------------------------------------------------
# 数据采集
# ---------------------------------------------------------------------------

def _safe_fetch(name, fn):
    try:
        return fn()
    except Exception as e:
        print(f"  ⚠ {name} 获取失败: {e}")
        return pd.DataFrame()

def fetch_index_data() -> dict:
    """三大指数实时数据（新浪源）—— 仅单日模式使用"""
    df = ak.stock_zh_index_spot_sina()
    target = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
    result = {}
    for _, row in df.iterrows():
        code = str(row["代码"])
        if code in target:
            result[target[code]] = {
                "收盘": round(float(row["最新价"]), 2),
                "涨跌幅": round(float(row["涨跌幅"]), 2),
                "成交额_亿": round(float(row["成交额"]) / 1e8, 0),
            }
    return result

def fetch_index_hist(dates: list[str]) -> dict[str, dict]:
    """批量获取指数历史数据，返回 {date_str: {name: {close, pct, volume}}}"""
    result: dict[str, dict] = {}
    for code, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
            df = df.sort_values("date").reset_index(drop=True)
            df["pct"] = df["close"].pct_change() * 100
            df_filtered = df[df["date_str"].isin(dates)]
            for _, row in df_filtered.iterrows():
                d = row["date_str"]
                if d not in result:
                    result[d] = {}
                result[d][name] = {
                    "收盘": round(float(row["close"]), 2),
                    "涨跌幅": round(float(row["pct"]), 2) if pd.notna(row["pct"]) else 0.0,
                    "成交额_亿": round(float(row["volume"]) / 1e8, 0) if "volume" in row and row["volume"] else 0,
                }
        except Exception as e:
            print(f"  ⚠ {name} 历史数据获取失败: {e}")
    return result

def fetch_a_spot() -> pd.DataFrame:
    """全A实时行情（新浪源）—— 仅单日模式使用。返回清洗后的 DataFrame。"""
    df = ak.stock_zh_a_spot()
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df = df[~df["代码"].astype(str).str.startswith("bj")]
    df = df[~df["名称"].astype(str).str.contains("ST")]
    df = df[pd.notna(df["涨跌幅"])]
    df = df[pd.to_numeric(df["成交量"], errors="coerce") > 0]
    return df

def calc_rise_fall_stats(df: pd.DataFrame) -> dict:
    """从全A行情 DataFrame 计算涨跌家数统计。"""
    rise = int((df["涨跌幅"] > 0).sum())
    fall = int((df["涨跌幅"] < 0).sum())
    flat = int((df["涨跌幅"] == 0).sum())
    return {"上涨": rise, "下跌": fall, "平盘": flat, "涨跌比": round(rise / max(fall, 1), 2), "总数": len(df)}

def fetch_zt_pool(date_str): return _safe_fetch("涨停池", lambda: ak.stock_zt_pool_em(date=date_str))
def fetch_zb_pool(date_str): return _safe_fetch("炸板池", lambda: ak.stock_zt_pool_zbgc_em(date=date_str))
def fetch_dt_pool(date_str): return _safe_fetch("跌停池", lambda: ak.stock_zt_pool_dtgc_em(date=date_str))
def fetch_previous_zt(date_str): return _safe_fetch("昨日涨停池", lambda: ak.stock_zt_pool_previous_em(date=date_str))


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------

def analyze_streak_tiers(zt_df):
    if zt_df.empty or "连板数" not in zt_df.columns:
        return []
    tiers = []
    for streak, grp in zt_df.groupby("连板数"):
        tiers.append({"板数": int(streak), "家数": len(grp),
                       "代表个股": "、".join(grp["名称"].head(3).tolist())})
    tiers.sort(key=lambda x: x["板数"], reverse=True)
    return tiers

def analyze_top_industries(zt_df):
    if zt_df.empty or "所属行业" not in zt_df.columns:
        return []
    ic = zt_df.groupby("所属行业").agg(
        涨停家数=("代码", "count"),
        代表个股=("名称", lambda x: "、".join(x.head(2))),
    ).sort_values("涨停家数", ascending=False).head(5).reset_index()
    return ic.to_dict(orient="records")


def _time_to_seconds(t: str) -> int:
    """将封板时间字符串(HHMMSS)转换为当日秒数。"""
    s = str(t).replace(":", "").strip().ljust(6, "0")
    try:
        return int(s[:2]) * 3600 + int(s[2:4]) * 60 + int(s[4:6])
    except (ValueError, IndexError):
        return 0


def classify_board_type(first_seal, last_seal) -> str:
    """根据首次/最后封板时间推断板型。

    一字板: 竞价即封全天不开  |  T字板: 竞价封板盘中开板后回封
    秒板: 开盘数分钟内封死    |  换手板: 经充分换手后封板
    烂板: 多次炸开再封        |  尾盘板: 14:00后封板
    """
    if not first_seal or not last_seal:
        return "未知"
    fs = _time_to_seconds(first_seal)
    ls = _time_to_seconds(last_seal)
    if fs == 0:
        return "未知"
    gap = ls - fs
    auction_cutoff = 9 * 3600 + 25 * 60 + 2  # 09:25:02

    if fs <= auction_cutoff:
        return "一字板" if gap <= 2 else "T字板"
    if fs <= 9 * 3600 + 35 * 60:
        return "秒板" if gap <= 300 else "分歧板"
    if ls >= 14 * 3600:
        return "尾盘板" if fs >= 14 * 3600 else "烂板"
    return "换手板" if gap <= 600 else "分歧板"


def calc_volume_analysis(current_vol: float, date_str: str) -> dict:
    """与历史缓存对比，计算量能分析数据。"""
    result: dict = {}
    if not DATA_DIR.exists() or current_vol <= 0:
        return result
    recent_vols: list[tuple[str, float]] = []
    for f in sorted(DATA_DIR.glob("*.json"), reverse=True):
        d = f.stem
        if not d.isdigit() or d >= date_str:
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                vol = json.load(fh).get("两市成交额_亿", 0)
            if vol > 0:
                recent_vols.append((d, vol))
        except Exception:
            pass
        if len(recent_vols) >= 5:
            break
    if recent_vols:
        prev_vol = recent_vols[0][1]
        result["昨日成交额_亿"] = prev_vol
        result["日环比%"] = round((current_vol / prev_vol - 1) * 100, 1)
    if len(recent_vols) >= 5:
        avg5 = sum(v for _, v in recent_vols[:5]) / 5
        result["5日均量_亿"] = round(avg5, 0)
        result["vs_5日均量%"] = round((current_vol / avg5 - 1) * 100, 1)
    return result


def enrich_details_with_spot(details: list[dict], spot_df: pd.DataFrame) -> list[dict]:
    """用全A实时行情数据补充涨停明细的换手率/振幅/量比。"""
    if spot_df.empty or not details:
        return details
    spot_map: dict[str, dict] = {}
    for col in ["换手率", "振幅", "量比"]:
        if col not in spot_df.columns:
            return details
    for _, row in spot_df.iterrows():
        code = str(row.get("代码", ""))
        spot_map[code] = {
            "换手率": round(float(row.get("换手率", 0)), 2),
            "振幅": round(float(row.get("振幅", 0)), 2),
            "量比": round(float(row.get("量比", 0)), 2),
        }
    for d in details:
        code = str(d.get("代码", ""))
        if code in spot_map:
            d.update(spot_map[code])
    return details


# 量能异动：未涨停但量比>=该阈值视为异常放量
VOLUME_ANOMALY_LIANGBI_MIN = 2.0
VOLUME_ANOMALY_TOP_N = 50


def get_volume_anomaly_non_zt(spot_df: pd.DataFrame, zt_codes: set[str]) -> list[dict]:
    """从全A行情中筛出未涨停但量能异常的个股（量比降序，取前 N）。"""
    if spot_df.empty or "量比" not in spot_df.columns:
        return []
    need_cols = ["代码", "名称", "涨跌幅", "量比", "换手率", "成交额"]
    missing = [c for c in need_cols if c not in spot_df.columns]
    if missing:
        return []
    df = spot_df.copy()
    df["量比"] = pd.to_numeric(df["量比"], errors="coerce").fillna(0)
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce").fillna(0)
    # 排除涨停：涨跌幅 < 9.5 或 代码不在涨停池
    df = df[df["涨跌幅"] < 9.5]
    df = df[~df["代码"].astype(str).isin(zt_codes)]
    df = df[df["量比"] >= VOLUME_ANOMALY_LIANGBI_MIN]
    df = df.sort_values("量比", ascending=False).head(VOLUME_ANOMALY_TOP_N)
    out = []
    for _, row in df.iterrows():
        try:
            vol = row.get("成交额", 0)
            if hasattr(vol, "item"):
                vol = vol.item()
            vol = round(float(vol), 0) if vol else 0
        except (TypeError, ValueError):
            vol = 0
        out.append({
            "代码": str(row["代码"]),
            "名称": str(row["名称"]),
            "涨跌幅": round(float(row["涨跌幅"]), 2),
            "量比": round(float(row["量比"]), 2),
            "换手率": round(float(row.get("换手率", 0)), 2),
            "成交额": vol,
        })
    return out


# ---------------------------------------------------------------------------
# 单日采集
# ---------------------------------------------------------------------------

def collect_single(date_str: str, *, use_realtime: bool = True, index_hist: Optional[dict] = None) -> dict:
    """采集单日数据。use_realtime=True 时使用实时接口（适合当日），否则用历史接口。"""
    spot_df = pd.DataFrame()
    if use_realtime:
        index_data = fetch_index_data()
        spot_df = _safe_fetch("全A行情", fetch_a_spot)
        rf = calc_rise_fall_stats(spot_df) if not spot_df.empty else {
            "上涨": 0, "下跌": 0, "平盘": 0, "涨跌比": 1.0, "总数": 0}
    else:
        index_data = (index_hist or {}).get(date_str, {})
        rf = {"上涨": 0, "下跌": 0, "平盘": 0, "涨跌比": 1.0, "总数": 0}

    zt_df = fetch_zt_pool(date_str)
    zt_count = len(zt_df)
    zb_df = fetch_zb_pool(date_str)
    zb_count = len(zb_df)
    seal_rate = round(zt_count / max(zt_count + zb_count, 1) * 100, 1)

    dt_df = fetch_dt_pool(date_str)
    dt_count = len(dt_df)

    prev_df = fetch_previous_zt(date_str)
    if not prev_df.empty and "涨跌幅" in prev_df.columns:
        premium = round(prev_df["涨跌幅"].astype(float).mean(), 2)
    else:
        premium = 0.0

    max_streak = 0
    if not zt_df.empty and "连板数" in zt_df.columns:
        max_streak = int(zt_df["连板数"].max())

    tiers = analyze_streak_tiers(zt_df)
    top_industries = analyze_top_industries(zt_df)

    if not use_realtime:
        rf["涨跌比"] = round(zt_count / max(dt_count, 1), 2) if dt_count > 0 else 5.0

    total_score, dim_scores = calc_emotion_score(
        zt_count, seal_rate, premium, max_streak, rf["涨跌比"], dt_count)

    total_vol = 0
    if isinstance(index_data, dict):
        for name in ["上证指数", "深证成指"]:
            v = index_data.get(name, {})
            total_vol += v.get("成交额_亿", 0)

    # 涨停明细（前20 + 全部连板股）+ 板型推断
    zt_details = []
    lianban_details = []
    if not zt_df.empty:
        cols = ["代码", "名称", "涨跌幅", "连板数", "首次封板时间", "最后封板时间", "封板资金", "所属行业"]
        available = [c for c in cols if c in zt_df.columns]
        for _, row in zt_df[available].head(20).iterrows():
            d = row.to_dict()
            d["板型"] = classify_board_type(d.get("首次封板时间"), d.get("最后封板时间"))
            zt_details.append(d)
        if "连板数" in zt_df.columns:
            lb_df = zt_df[zt_df["连板数"] >= 2].sort_values("连板数", ascending=False)
            for _, row in lb_df[available].iterrows():
                d = row.to_dict()
                d["板型"] = classify_board_type(d.get("首次封板时间"), d.get("最后封板时间"))
                lianban_details.append(d)

    # 用全A行情补充连板股的换手率/振幅/量比（仅实时模式）
    if use_realtime and not spot_df.empty:
        enrich_details_with_spot(zt_details, spot_df)
        enrich_details_with_spot(lianban_details, spot_df)

    # 量能异动：未涨停但量比>=阈值的个股列表（仅单日/实时模式）
    zt_codes = set(zt_df["代码"].astype(str)) if not zt_df.empty and "代码" in zt_df.columns else set()
    volume_anomaly = get_volume_anomaly_non_zt(spot_df, zt_codes) if use_realtime and not spot_df.empty else []

    # 量能分析
    vol_analysis = calc_volume_analysis(total_vol, date_str) if total_vol > 0 else {}

    return {
        "日期": date_str, "指数": index_data, "两市成交额_亿": total_vol,
        "量能分析": vol_analysis, "涨跌统计": rf,
        "涨停家数": zt_count, "炸板家数": zb_count,
        "封板率": seal_rate, "跌停家数": dt_count, "昨涨停溢价率": premium,
        "最高连板": max_streak, "连板梯队": tiers, "涨停行业TOP5": top_industries,
        "涨停明细_前20": zt_details, "连板股明细": lianban_details,
        "量能异动_未涨停": volume_anomaly,
        "情绪各维度": dim_scores,
        "情绪综合得分": total_score, "情绪阶段": emotion_stage_full(total_score),
    }


# ---------------------------------------------------------------------------
# 批量采集
# ---------------------------------------------------------------------------

def collect_batch(dates: list[str], *, force: bool = False) -> list[dict]:
    """批量采集多个交易日数据，支持增量更新。"""
    DATA_DIR.mkdir(exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")

    to_collect = []
    cached = []
    for d in dates:
        json_path = DATA_DIR / f"{d}.json"
        if not force and json_path.exists():
            cached.append(d)
        else:
            to_collect.append(d)

    if cached:
        print(f"📦 已缓存 {len(cached)} 天（跳过）: {', '.join(cached[:5])}{'...' if len(cached) > 5 else ''}")
    if not to_collect:
        print("✅ 所有日期已有缓存，无需采集")
        return _load_cached(dates)

    print(f"📊 需采集 {len(to_collect)} 个交易日\n")

    hist_dates = [d for d in to_collect if d != today_str]
    is_today_in_list = today_str in to_collect

    index_hist = {}
    if hist_dates:
        print("  获取指数历史数据...")
        index_hist = fetch_index_hist(hist_dates)

    results = []
    total = len(to_collect)
    for i, d in enumerate(to_collect, 1):
        print(f"  [{i}/{total}] 采集 {d}...", end=" ", flush=True)
        use_rt = (d == today_str)
        try:
            data = collect_single(d, use_realtime=use_rt, index_hist=index_hist)
            if data["涨停家数"] == 0 and data["跌停家数"] == 0:
                print("⏭ 无数据（非交易日？）")
                continue
            _save_json(data, d)
            print("✅")
            results.append(data)
        except Exception as e:
            print(f"❌ {e}")

    for d in cached:
        loaded = _load_single(d)
        if loaded:
            results.append(loaded)

    results.sort(key=lambda x: x["日期"])
    return results


def _load_cached(dates: list[str]) -> list[dict]:
    results = []
    for d in dates:
        data = _load_single(d)
        if data:
            results.append(data)
    results.sort(key=lambda x: x["日期"])
    return results


def _load_single(date_str: str) -> dict | None:
    path = DATA_DIR / f"{date_str}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# 周期汇总报告
# ---------------------------------------------------------------------------

def _compat(r: dict) -> dict:
    """兼容新旧 JSON 格式的 key 差异。"""
    if "情绪综合得分" not in r and "情绪得分" in r:
        r["情绪综合得分"] = r["情绪得分"]
    if "情绪各维度" not in r and "维度" in r:
        r["情绪各维度"] = r["维度"]
    for key in ["涨停家数", "炸板家数", "封板率", "跌停家数", "昨涨停溢价率", "最高连板", "情绪综合得分"]:
        r.setdefault(key, 0)
    r.setdefault("情绪阶段", emotion_stage_full(r.get("情绪综合得分", 0)))
    # 兼容旧格式指数: {name: {close, pct, volume}} → {name: {收盘, 涨跌幅, 成交额_亿}}
    idx = r.get("指数", {})
    if isinstance(idx, dict):
        for name, v in idx.items():
            if isinstance(v, dict) and "close" in v and "收盘" not in v:
                v["收盘"] = v.pop("close")
                v["涨跌幅"] = v.pop("pct", 0)
                vol = v.pop("volume", 0)
                if vol and "成交额_亿" not in v:
                    v["成交额_亿"] = round(vol / 1e8, 0) if vol > 1e6 else vol
    r.setdefault("指数", {})
    # 旧格式涨停行业TOP5: dict {行业: 数量} → 新格式: list of {所属行业, 涨停家数, 代表个股}
    ind = r.get("涨停行业TOP5", [])
    if isinstance(ind, dict):
        new_ind = [{"所属行业": k, "涨停家数": v, "代表个股": ""} for k, v in ind.items()]
        new_ind.sort(key=lambda x: x["涨停家数"], reverse=True)
        r["涨停行业TOP5"] = new_ind
    elif not isinstance(ind, list):
        r["涨停行业TOP5"] = []
    # 旧格式连板梯队: dict {str_板数: {家数, 代表}} → 新格式: list of {板数, 家数, 代表个股}
    tiers = r.get("连板梯队", [])
    if isinstance(tiers, dict):
        new_tiers = []
        for k, v in tiers.items():
            new_tiers.append({
                "板数": int(k),
                "家数": v.get("家数", 0),
                "代表个股": v.get("代表", v.get("代表个股", "")),
            })
        new_tiers.sort(key=lambda x: x["板数"], reverse=True)
        r["连板梯队"] = new_tiers
    elif not isinstance(tiers, list):
        r["连板梯队"] = []
    return r


def generate_summary(dates: list[str], data_dir: Path) -> str:
    """生成周期汇总报告（Markdown 格式），同时打印到控制台并保存文件。"""
    records = []
    for d in dates:
        data = _load_single(d)
        if data:
            records.append(_compat(data))
    if not records:
        return "无可用数据"

    records.sort(key=lambda x: x["日期"])
    start = records[0]["日期"]
    end = records[-1]["日期"]
    lines = []

    lines.append(f"# A股周期复盘汇总 —— {start[:4]}/{start[4:6]}/{start[6:]} ~ {end[:4]}/{end[4:6]}/{end[6:]}")
    lines.append("")

    # 区间统计
    zt_counts = [r["涨停家数"] for r in records]
    scores = [r["情绪综合得分"] for r in records]
    avg_zt = sum(zt_counts) / len(zt_counts)
    avg_score = sum(scores) / len(scores)
    max_s = max(scores)
    min_s = min(scores)
    max_d = next(r["日期"] for r in records if r["情绪综合得分"] == max_s)
    min_d = next(r["日期"] for r in records if r["情绪综合得分"] == min_s)

    idx_first = records[0].get("指数", {}).get("上证指数", {})
    idx_last = records[-1].get("指数", {}).get("上证指数", {})
    first_close = idx_first.get("收盘", 0)
    last_close = idx_last.get("收盘", 0)
    period_ret = round((last_close / first_close - 1) * 100, 2) if first_close else 0

    lines.append("## 区间统计")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 交易天数 | {len(records)} 天 |")
    lines.append(f"| 日均涨停 | {avg_zt:.1f} 家 |")
    lines.append(f"| 平均情绪得分 | {avg_score:.2f} 分 |")
    lines.append(f"| 最高情绪 | {max_s:.2f}（{max_d}） |")
    lines.append(f"| 最低情绪 | {min_s:.2f}（{min_d}） |")
    lines.append(f"| 上证区间涨幅 | {period_ret:+.2f}%（{first_close} → {last_close}） |")
    lines.append("")

    # 指数走势表
    lines.append("## 三大指数走势")
    lines.append("")
    lines.append("| 日期 | 上证指数 | 深证成指 | 创业板指 |")
    lines.append("|------|----------|----------|----------|")
    for r in records:
        d = r["日期"]
        idx = r.get("指数", {})
        cells = []
        for name in ["上证指数", "深证成指", "创业板指"]:
            v = idx.get(name, {})
            c = v.get("收盘", "--")
            p = v.get("涨跌幅", 0)
            cells.append(f"{c}（{p:+.2f}%）" if c != "--" else "--")
        lines.append(f"| {d} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines.append("")

    # 情绪核心数据表
    lines.append("## 每日情绪核心数据")
    lines.append("")
    lines.append("| 日期 | 涨停 | 炸板 | 封板率 | 跌停 | 溢价率 | 最高连板 | 得分 | 阶段 |")
    lines.append("|------|------|------|--------|------|--------|---------|------|------|")
    for r in records:
        stage = emotion_stage(r["情绪综合得分"])
        lines.append(
            f"| {r['日期']} | {r['涨停家数']} | {r['炸板家数']} | {r['封板率']}% "
            f"| {r['跌停家数']} | {r['昨涨停溢价率']:+.2f}% | {r['最高连板']}板 "
            f"| {r['情绪综合得分']:.2f} | {stage} |"
        )
    lines.append("")

    # 情绪走势曲线
    lines.append("## 情绪走势曲线")
    lines.append("")
    lines.append("```")
    for r in records:
        s = r["情绪综合得分"]
        bar_len = int(s / 10 * 40)
        bar = "█" * bar_len + "░" * (40 - bar_len)
        stage = emotion_stage(s)
        lines.append(f"  {r['日期']} {bar} {s:.2f} {stage}")
    lines.append("```")
    lines.append("")

    # 龙头演进追踪
    lines.append("## 龙头演进追踪")
    lines.append("")
    stock_history = defaultdict(list)
    for r in records:
        for tier in r.get("连板梯队", []):
            if tier["板数"] >= 2:
                for name in tier["代表个股"].split("、"):
                    name = name.strip()
                    if name:
                        stock_history[name].append((r["日期"], tier["板数"]))

    leaders = {name: hist for name, hist in stock_history.items() if len(hist) >= 2}
    if leaders:
        leaders_sorted = sorted(leaders.items(), key=lambda x: max(b for _, b in x[1]), reverse=True)
        lines.append("| 龙头 | 演进轨迹 | 最高板数 |")
        lines.append("|------|----------|---------|")
        for name, hist in leaders_sorted[:10]:
            trail = " → ".join(f"{d[4:6]}/{d[6:]}({b}板)" for d, b in hist)
            max_b = max(b for _, b in hist)
            lines.append(f"| {name} | {trail} | {max_b}板 |")
    else:
        lines.append("_本周期内无跨日连板龙头_")
    lines.append("")

    # 题材轮动汇总
    lines.append("## 题材轮动")
    lines.append("")
    lines.append("| 日期 | TOP1 行业 | TOP2 行业 | TOP3 行业 |")
    lines.append("|------|-----------|-----------|-----------|")
    for r in records:
        tops = r.get("涨停行业TOP5", [])
        cells = []
        for i in range(3):
            if i < len(tops):
                t = tops[i]
                cells.append(f"{t['所属行业']}({t['涨停家数']})")
            else:
                cells.append("--")
        lines.append(f"| {r['日期']} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines.append("")

    md = "\n".join(lines)

    # 保存文件
    data_dir.mkdir(exist_ok=True)
    out_path = data_dir / f"summary_{start}_{end}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 打印到控制台
    print(f"\n{'=' * 80}")
    print(md)
    print(f"{'=' * 80}")
    print(f"\n✅ 汇总报告已保存至: {out_path}")

    return md


# ---------------------------------------------------------------------------
# 复盘草稿生成
# ---------------------------------------------------------------------------

REVIEW_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "复盘模板"
DAILY_REVIEW_DIR = Path(__file__).resolve().parent.parent / "每日复盘"
WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _get_prev_trading_days(date_str: str, n: int) -> list[str]:
    """返回 date_str 及之前共 n 个交易日的列表（含 date_str），按时间正序。"""
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return []
    start = (dt - timedelta(days=max(n * 3, 60))).strftime("%Y%m%d")
    all_days = get_trading_days(start, date_str)
    return all_days[-n:] if len(all_days) >= n else all_days


def generate_draft_review(
    date_str: str,
    data_dict: dict,
    template_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
) -> Path:
    """根据当日采集数据生成复盘总结草稿 Markdown，写入 每日复盘/YYYYMM/YYYY-MM-DD_draft.md。"""
    out_dir = out_dir or DAILY_REVIEW_DIR
    yyyymm = f"{date_str[:4]}{date_str[4:6]}"
    day_slug = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    try:
        wd = datetime.strptime(date_str, "%Y%m%d").weekday()
        week_cn = WEEKDAY_CN[wd]
    except ValueError:
        week_cn = "X"
    out_path = out_dir / yyyymm / f"{day_slug}_draft.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 前两日数据（用于 3 日趋势）
    prev3 = _get_prev_trading_days(date_str, 3)
    scores_3d = []
    for d in prev3:
        if d == date_str:
            scores_3d.append(data_dict.get("情绪综合得分", data_dict.get("情绪得分", 0)))
        else:
            loaded = _load_single(d)
            if loaded:
                loaded = _compat(loaded)
                scores_3d.append(loaded.get("情绪综合得分", 0))
            else:
                scores_3d.append(0)
    if len(scores_3d) == 3:
        s0, s1, s2 = scores_3d
        if s0 < s1 < s2:
            trend_3d = "连续升温"
        elif s0 > s1 > s2:
            trend_3d = "连续降温"
        elif s0 > s1 and s1 < s2:
            trend_3d = "先降后升"
        elif s0 < s1 and s1 > s2:
            trend_3d = "先升后降"
        else:
            trend_3d = "持平或震荡"
    else:
        trend_3d = "____（不足3日数据）"
    score_prev2 = scores_3d[0] if len(scores_3d) >= 3 else "____"
    score_prev1 = scores_3d[1] if len(scores_3d) >= 2 else "____"
    score_today = data_dict.get("情绪综合得分", "____")

    idx = data_dict.get("指数", {})
    vol = data_dict.get("量能分析", {})
    rf = data_dict.get("涨跌统计", {})

    def idx_cell(name: str) -> str:
        v = idx.get(name, {})
        c = v.get("收盘", "____")
        p = v.get("涨跌幅", 0)
        if c == "____":
            return "____ 点（____%）"
        return f"{c} 点（{p:+.2f}%）"

    vol_note = "____"
    if vol.get("日环比%") is not None:
        vol_note = f"较昨日 {'放量' if vol['日环比%'] > 0 else '缩量'} {vol['日环比%']:+.1f}%"
    vol_5 = "____"
    if vol.get("vs_5日均量%") is not None:
        vol_5 = "放量" if vol["vs_5日均量%"] > 5 else ("缩量" if vol["vs_5日均量%"] < -5 else "持平")

    lines = [
        f"# 每日情绪复盘 - {day_slug[:4]}/{day_slug[5:7]}/{day_slug[8:10]}（星期{week_cn}）",
        "",
        "---",
        "",
        "## 一、大盘概览",
        "",
        "| 指标 | 数值 | 备注 |",
        "|------|------|------|",
        f"| 上证指数 | {idx_cell('上证指数')} | 5日线上方 / 下方 |",
        f"| 深成指 | {idx_cell('深证成指')} | 5日线上方 / 下方 |",
        f"| 创业板指 | {idx_cell('创业板指')} | 5日线上方 / 下方 |",
        f"| 两市成交额 | {data_dict.get('两市成交额_亿', '____')} 亿 | {vol_note} |",
        f"| 5日均量 | {vol.get('5日均量_亿', '____')} 亿 | 今日成交额 vs 5日均量：{vol_5} |",
        f"| 上涨家数 | {rf.get('上涨', '____')} 家 | |",
        f"| 下跌家数 | {rf.get('下跌', '____')} 家 | |",
        f"| 涨跌比 | {rf.get('涨跌比', '____')} | >2 普涨 / 1-2 偏强 / 0.5-1 偏弱 / <0.5 普跌 |",
        "",
        "**大盘技术位置**：",
        "- 上证：__日均线附近（支撑/压力位 ____ 点）",
        "- 创业板：__日均线附近（支撑/压力位 ____ 点）",
        "- 大盘周期判断：上升趋势 / 震荡 / 下降趋势",
        "",
        "---",
        "",
        "## 二、竞价复盘",
        "",
        "（请根据盘面补充：核心股竞价表现、竞价整体氛围）",
        "",
        "---",
        "",
        "## 三、情绪核心数据",
        "",
    ]

    dim = data_dict.get("情绪各维度", {})
    lines.extend([
        "| 指标 | 原始值 | 评分(1-10) | 评分参考 |",
        "|------|--------|-----------|----------|",
        f"| 涨停家数 | {data_dict.get('涨停家数', '____')} 家 | {dim.get('涨停家数', '____')} | <20→1-2 / 20-40→3-4 / ... |",
        f"| 封板率 | {data_dict.get('封板率', '____')}% | {dim.get('封板率', '____')} | <40%→1-3 / ... |",
        f"| 昨涨停今日溢价率 | {data_dict.get('昨涨停溢价率', '____')}% | {dim.get('昨涨停溢价', '____')} | <-5%→1 / ... |",
        f"| 最高连板 | {data_dict.get('最高连板', '____')} 板 | {dim.get('连板高度', '____')} | 无→1 / 2板→3 / ... |",
        f"| 涨跌比 | {rf.get('涨跌比', '____')} | {dim.get('涨跌比', '____')} | <0.3→1 / ... |",
        f"| 跌停家数 | {data_dict.get('跌停家数', '____')} 家 | {dim.get('跌停反指', '____')} | >30→1 / ... |",
        "",
        "### 亏钱效应追踪",
        "",
        "| 指标 | 数值 | 说明 |",
        "|------|------|------|",
        "| 大面股数量 | ____ 家 | 昨日涨停/连板今日跌幅 > 5% 的个股 |",
        "| 昨涨停大面比例 | ____% | 大面股 / 昨日涨停总数 |",
        f"| 炸板股数量 | {data_dict.get('炸板家数', '____')} 家 | 盘中触及涨停但未封住 |",
        "",
        "### 情绪综合得分",
        "",
        f"**今日情绪得分：{score_today} 分**",
        "",
        "### 连板梯队分布",
        "",
        "| 板数 | 家数 | 代表个股 |",
        "|------|------|----------|",
    ])

    for t in data_dict.get("连板梯队", []):
        lines.append(f"| {t.get('板数', '')}板 | {t.get('家数', '')} 家 | {t.get('代表个股', '')} |")
    if not data_dict.get("连板梯队"):
        lines.append("| ____ | ____ 家 | |")

    lines.extend([
        "",
        "---",
        "",
        "## 四、情绪周期定位",
        "",
        "### 得分走势",
        "",
        f"- **前日情绪得分**：{score_prev2} 分",
        f"- **昨日情绪得分**：{score_prev1} 分",
        f"- **今日情绪得分**：{score_today} 分",
        f"- **3日趋势**：{trend_3d}",
        "",
        "### 当前所处周期阶段",
        "",
        f"- 当前阶段：{data_dict.get('情绪阶段', '____')}",
        "",
        "---",
        "",
        "## 五、龙头梳理",
        "",
        "（请根据盘面补充：总龙头、补涨龙、前排助攻、龙头演进判断）",
        "",
        "---",
        "",
        "## 六、题材板块分析",
        "",
        "### 当日最强题材 TOP3",
        "",
        "| 排名 | 题材名称 | 涨停家数 | 代表个股 |",
        "|------|----------|----------|----------|",
    ])

    for i, ind in enumerate(data_dict.get("涨停行业TOP5", [])[:3], 1):
        lines.append(f"| {i} | {ind.get('所属行业', '')} | {ind.get('涨停家数', '')} | {ind.get('代表个股', '')} |")
    for _ in range(3 - len(data_dict.get("涨停行业TOP5", [])[:3])):
        lines.append("| ____ | | | |")

    # 量能异动未涨停
    anomaly = data_dict.get("量能异动_未涨停", [])
    if anomaly:
        lines.extend([
            "",
            "### 量能异动（未涨停）",
            "",
            "| 名称 | 涨跌幅 | 量比 | 换手率 |",
            "|------|--------|------|--------|",
        ])
        for s in anomaly[:20]:
            lines.append(f"| {s.get('名称', '')} | {s.get('涨跌幅', 0):+.2f}% | {s.get('量比', '')} | {s.get('换手率', '')}% |")
        if len(anomaly) > 20:
            lines.append(f"| ... 共 {len(anomaly)} 只 | | | |")

    lines.extend([
        "",
        "---",
        "",
        "## 七、五日线低吸跟踪",
        "",
        "（请根据盘面补充：低吸候选池）",
        "",
        "---",
        "",
        "## 八、持仓管理",
        "",
        "（请补充：当前持仓、明日操作计划）",
        "",
        "---",
        "",
        "## 九、明日策略",
        "",
        "（请根据复盘结论补充：情景预案、竞价策略、仓位计划、关注方向、风险提示）",
        "",
        "---",
        "",
        "## 十、交易纪律自检",
        "",
        "（请补充：今日操作回顾、纪律检查）",
        "",
        "---",
        "",
        "> **本稿由脚本自动生成，请在此基础上补充主观判断与操作计划。**",
        "",
    ])

    md = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    return out_path

def print_report(data: dict):
    d = data["日期"]
    print(f"\n{'='*60}")
    print(f"  A股每日复盘数据 —— {d[:4]}/{d[4:6]}/{d[6:]}")
    print(f"{'='*60}\n")

    print("【一、大盘概览】")
    idx = data.get("指数", {})
    if isinstance(idx, dict):
        for name, v in idx.items():
            if isinstance(v, dict) and "收盘" in v:
                print(f"  {name}: {v['收盘']} 点（{v['涨跌幅']:+.2f}%）")
    print(f"  两市成交额: {data['两市成交额_亿']:.0f} 亿")
    va = data.get("量能分析", {})
    if va.get("日环比%") is not None:
        label = "放量" if va["日环比%"] > 0 else "缩量"
        print(f"  量能: 较昨日{label} {va['日环比%']:+.1f}%", end="")
        if va.get("vs_5日均量%") is not None:
            print(f" | vs 5日均量 {va['vs_5日均量%']:+.1f}%", end="")
        print()
    rf = data.get("涨跌统计", {})
    if rf.get("上涨"):
        print(f"  上涨 {rf['上涨']} 家 / 下跌 {rf['下跌']} 家 / 平盘 {rf['平盘']} 家")
        print(f"  涨跌比: {rf['涨跌比']}")

    print("\n【二、情绪核心数据】")
    print(f"  涨停: {data['涨停家数']} 家 | 炸板: {data['炸板家数']} 家 | 封板率: {data['封板率']}%")
    print(f"  跌停: {data['跌停家数']} 家")
    print(f"  昨涨停溢价率: {data['昨涨停溢价率']:+.2f}%")
    print(f"  最高连板: {data['最高连板']} 板")
    print(f"  ★ 情绪综合得分: {data['情绪综合得分']} 分")
    print(f"  ★ 当前阶段: {data['情绪阶段']}")

    if data.get("连板梯队"):
        print("\n【三、连板梯队】")
        for t in data["连板梯队"]:
            print(f"  {t['板数']}板: {t['家数']}家 → {t['代表个股']}")

    if data.get("连板股明细"):
        print("\n【四、连板股盘口明细】")
        for s in data["连板股明细"]:
            name = s.get("名称", "?")
            streak = s.get("连板数", "?")
            btype = s.get("板型", "?")
            fs = s.get("首次封板时间", "")
            ls = s.get("最后封板时间", "")
            seal_money = s.get("封板资金", 0)
            seal_yi = round(seal_money / 1e8, 1) if seal_money else 0
            turnover = s.get("换手率", "")
            amplitude = s.get("振幅", "")
            line = f"  {name}({streak}板) [{btype}] 首封{fs} 末封{ls} 封单{seal_yi}亿"
            if turnover:
                line += f" 换手{turnover}%"
            if amplitude:
                line += f" 振幅{amplitude}%"
            print(line)

    if data.get("涨停行业TOP5"):
        print("\n【五、涨停行业 TOP5】")
        for i, ind in enumerate(data["涨停行业TOP5"], 1):
            print(f"  {i}. {ind['所属行业']}（{ind['涨停家数']}家涨停）→ {ind['代表个股']}")

    if data.get("量能异动_未涨停"):
        print("\n【六、量能异动（未涨停）】")
        for s in data["量能异动_未涨停"][:15]:
            print(f"  {s.get('名称', '?')} 涨跌幅{s.get('涨跌幅', 0):+.2f}% 量比{s.get('量比', 0)} 换手{s.get('换手率', 0)}%")
        if len(data["量能异动_未涨停"]) > 15:
            print(f"  ... 共 {len(data['量能异动_未涨停'])} 只（量比≥{VOLUME_ANOMALY_LIANGBI_MIN}）")

    print(f"\n{'='*60}\n")


def _save_json(data: dict, date_str: str):
    DATA_DIR.mkdir(exist_ok=True)
    out_file = DATA_DIR / f"{date_str}.json"
    def ser(obj):
        if isinstance(obj, pd.DataFrame): return obj.to_dict(orient="records")
        if isinstance(obj, (pd.Timestamp, datetime)): return str(obj)
        if hasattr(obj, "item"): return obj.item()
        return obj
    clean = json.loads(json.dumps(data, default=ser, ensure_ascii=False))
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="A股每日复盘数据自动采集脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("date", nargs="?", help="单日采集日期（YYYYMMDD）")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"), help="批量采集日期范围")
    parser.add_argument("--days", type=int, help="采集最近 N 个交易日")
    parser.add_argument("--force", action="store_true", help="强制重新采集（忽略缓存）")
    parser.add_argument("--summary", action="store_true", help="生成周期汇总报告")
    parser.add_argument("--no-draft", dest="draft", action="store_false", default=True,
                        help="不生成复盘草稿（单日/批量均可生成草稿时默认生成）")
    parser.add_argument("--print-only", action="store_true", help="仅打印，不保存文件")
    return parser.parse_args()


def main():
    args = parse_args()

    # 批量模式: --range
    if args.range:
        start, end = args.range
        dates = get_trading_days(start, end)
        if not dates:
            print(f"❌ {start} ~ {end} 范围内无交易日")
            return
        print(f"📅 日期范围 {start} ~ {end}，共 {len(dates)} 个交易日\n")
        collect_batch(dates, force=args.force)
        if args.summary:
            generate_summary(dates, DATA_DIR)
        if args.draft:
            for d in dates:
                loaded = _load_single(d)
                if loaded:
                    p = generate_draft_review(d, loaded)
                    print(f"  草稿: {p}")
        return

    # 批量模式: --days
    if args.days:
        dates = get_recent_trading_days(args.days)
        if not dates:
            print(f"❌ 无法确定最近 {args.days} 个交易日")
            return
        print(f"📅 最近 {args.days} 个交易日: {dates[0]} ~ {dates[-1]}\n")
        collect_batch(dates, force=args.force)
        if args.summary:
            generate_summary(dates, DATA_DIR)
        if args.draft:
            for d in dates:
                loaded = _load_single(d)
                if loaded:
                    p = generate_draft_review(d, loaded)
                    print(f"  草稿: {p}")
        return

    # 单日模式
    # 无参数时：取「最近一个交易日」（0 点跑则为上一交易日，盘中/收盘后跑则为当日）
    if args.date:
        date_str = args.date
    else:
        date_str = get_recent_trading_days(1)[0]
    print(f"📊 正在采集 {date_str} 的复盘数据...\n")
    data = collect_single(date_str, use_realtime=True)
    print_report(data)
    if not args.print_only:
        _save_json(data, date_str)
        print(f"✅ 原始数据已保存至: {DATA_DIR / f'{date_str}.json'}")
        if args.draft:
            out_path = generate_draft_review(date_str, data)
            print(f"✅ 复盘草稿已生成: {out_path}")


if __name__ == "__main__":
    main()
