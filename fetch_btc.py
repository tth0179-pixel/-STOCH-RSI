"""
비트코인(KRW-BTC) Stoch RSI 계산 스크립트 (업비트 공개 API 사용, 무료/키 불필요)

- 코스피 스크립트(fetch_data.py)와 완전히 분리되어 있어, 주식 장중 스케줄과
  무관하게 24시간 365일 자주(예: 1시간마다) 실행할 수 있습니다.
- 결과를 btc.json 으로 저장합니다. index.html 이 이 파일을 읽어서
  "관심종목" 섹션에 표시합니다.
"""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_ta as ta
import requests

OUTPUT_FILE = "btc.json"
HISTORY_DAYS = 1650  # 월봉 Stoch RSI 계산에 필요한 최소 기간 확보 (약 4.5년치)
KST = timezone(timedelta(hours=9))


def calc_stochrsi(df, return_series=False):
    """OHLCV DataFrame(일/주/월봉 공용) -> 최근 %K, %D 값 (return_series=True면 전체 시계열도 함께 반환)"""
    if df is None or len(df) < 30:
        return (None, None) if return_series else None
    try:
        result = ta.stochrsi(df["종가"], length=14, rsi_length=14, k=3, d=3)
    except Exception:
        return (None, None) if return_series else None
    if result is None or result.empty:
        return (None, None) if return_series else None

    k_cols = [c for c in result.columns if c.startswith("STOCHRSIk")]
    d_cols = [c for c in result.columns if c.startswith("STOCHRSId")]
    if not k_cols or not d_cols:
        return (None, None) if return_series else None

    last = result.iloc[-1]
    k_val, d_val = last[k_cols[0]], last[d_cols[0]]
    if pd.isna(k_val) or pd.isna(d_val):
        return (None, None) if return_series else None

    latest = {"k": round(float(k_val), 2), "d": round(float(d_val), 2)}
    if not return_series:
        return latest
    return latest, result[[k_cols[0], d_cols[0]]].rename(columns={k_cols[0]: "k", d_cols[0]: "d"})


def build_history(df, stoch_series, n=90):
    """차트용: 최근 n개 봉의 OHLC + 거래량 + 이동평균(5/20/60/120) + Stoch %K/%D"""
    cols = ["시가", "고가", "저가", "종가"]
    has_volume = "거래량" in df.columns
    if has_volume:
        cols.append("거래량")
    merged = df[cols].copy()
    merged["ma5"] = df["종가"].rolling(5).mean()
    merged["ma20"] = df["종가"].rolling(20).mean()
    merged["ma60"] = df["종가"].rolling(60).mean()
    merged["ma120"] = df["종가"].rolling(120).mean()
    if stoch_series is not None:
        merged = merged.join(stoch_series)
    merged = merged.tail(n)

    history = []
    for idx, row in merged.iterrows():
        entry = {
            "date": idx.strftime("%Y-%m-%d"),
            "o": round(float(row["시가"])),
            "h": round(float(row["고가"])),
            "l": round(float(row["저가"])),
            "c": round(float(row["종가"])),
        }
        if has_volume and pd.notna(row.get("거래량")):
            entry["v"] = int(row["거래량"])
        for ma_key in ("ma5", "ma20", "ma60", "ma120"):
            if pd.notna(row.get(ma_key)):
                entry[ma_key] = round(float(row[ma_key]))
        if "k" in merged.columns and pd.notna(row.get("k")):
            entry["k"] = round(float(row["k"]), 2)
        if "d" in merged.columns and pd.notna(row.get("d")):
            entry["d"] = round(float(row["d"]), 2)
        history.append(entry)
    return history


def resample_ohlcv(df, rule):
    agg = {"시가": "first", "고가": "max", "저가": "min", "종가": "last", "거래량": "sum"}
    return df.resample(rule).agg(agg).dropna()


def calc_cycle_indicators(df):
    """반감기 사이클(장기 보유) 관점 지표.
    - Mayer Multiple = 종가 / 200일 이동평균 (2.4 이상=과열/고점권, 0.8 이하=저평가/저점권, 평균 약 1.31)
    - Pi Cycle Top = 111일 이동평균 vs 350일 이동평균×2 (111일선이 350일선×2를 상향 돌파하면 과거 주요 고점과 근접했던 이력)
    - history: Mayer Multiple 주간 추이(200일 이동평균이 계산 가능한 시점부터) — 시계열 그래프용
    데이터가 부족(최소 350일치 미만)하면 None을 반환한다."""
    if df is None or len(df) < 350:
        return None

    close = df["종가"]
    ma200 = close.rolling(200).mean()
    ma111 = close.rolling(111).mean()
    ma350 = close.rolling(350).mean()

    last_close = close.iloc[-1]
    last_ma200 = ma200.iloc[-1]
    last_ma111 = ma111.iloc[-1]
    last_ma350 = ma350.iloc[-1]

    if pd.isna(last_ma200) or pd.isna(last_ma111) or pd.isna(last_ma350):
        return None

    mayer_multiple = round(float(last_close / last_ma200), 3)
    pi_cycle_band = round(float(last_ma350 * 2), 0)
    pi_cross = bool(last_ma111 >= last_ma350 * 2)

    # 시계열: Mayer Multiple 주간 추이(200일 이동평균이 유효한 구간부터, 주 단위로 샘플링해 용량 절약)
    mayer_series = (close / ma200).dropna()
    weekly_mayer = mayer_series.resample("W").last().dropna()
    history = [
        {"date": idx.strftime("%Y-%m-%d"), "mayer_multiple": round(float(v), 3)}
        for idx, v in weekly_mayer.items()
    ]

    return {
        "mayer_multiple": mayer_multiple,
        "ma200": round(float(last_ma200)),
        "ma111": round(float(last_ma111)),
        "pi_cycle_band": pi_cycle_band,  # 350일선 x 2 (Pi Cycle Top 기준선)
        "pi_cross": pi_cross,  # True면 111일선이 기준선을 이미 상향 돌파(고점 확정 신호)
        "history": history,  # [{date, mayer_multiple}] 주간 추이
    }


def fetch_upbit_daily_df(market="KRW-BTC", total_days=HISTORY_DAYS):
    """업비트 공개 API(무료, 키 불필요)로 일봉 OHLCV를 최대 total_days만큼 페이징하여 수집"""
    all_rows = []
    to_param = None
    while len(all_rows) < total_days:
        params = {"market": market, "count": 200}
        if to_param:
            params["to"] = to_param
        resp = requests.get("https://api.upbit.com/v1/candles/days", params=params, timeout=10)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        to_param = batch[-1]["candle_date_time_utc"]
        if len(batch) < 200:
            break

    df = pd.DataFrame(all_rows).drop_duplicates(subset="candle_date_time_kst")
    df["date"] = pd.to_datetime(df["candle_date_time_kst"])
    df = df.set_index("date").sort_index()
    df = df.rename(columns={
        "opening_price": "시가",
        "high_price": "고가",
        "low_price": "저가",
        "trade_price": "종가",
        "candle_acc_trade_volume": "거래량",
    })
    return df[["시가", "고가", "저가", "종가", "거래량"]]


def main():
    end = datetime.now(KST)
    df = fetch_upbit_daily_df("KRW-BTC", HISTORY_DAYS)

    daily, daily_stoch_series = calc_stochrsi(df, return_series=True)
    weekly_df = resample_ohlcv(df, "W")
    weekly, weekly_stoch_series = calc_stochrsi(weekly_df, return_series=True)
    monthly_df = resample_ohlcv(df, "ME")
    monthly, monthly_stoch_series = calc_stochrsi(monthly_df, return_series=True)

    history_daily = build_history(df, daily_stoch_series, n=90)
    history_weekly = build_history(weekly_df, weekly_stoch_series, n=78)
    history_monthly = build_history(monthly_df, monthly_stoch_series, n=48)

    last_row = df.iloc[-1]
    prev_close = df.iloc[-2]["종가"] if len(df) > 1 else last_row["종가"]
    change_pct = round((last_row["종가"] - prev_close) / prev_close * 100, 2)

    cycle = calc_cycle_indicators(df)

    asset = {
        "code": "BTC-KRW",
        "name": "비트코인",
        "close": int(last_row["종가"]),
        "change_pct": change_pct,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "cycle": cycle,  # 반감기 사이클 지표 (Mayer Multiple, Pi Cycle Top) — 데이터 부족 시 null
        "history": {
            "daily": history_daily,
            "weekly": history_weekly,
            "monthly": history_monthly,
        },
    }

    output = {
        "updated_at": end.strftime("%Y-%m-%d %H:%M"),
        "assets": [asset],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    cycle_log = f", Mayer={cycle['mayer_multiple']}" if cycle else " (사이클 지표: 데이터 부족)"
    print(f"저장 완료: {OUTPUT_FILE} (BTC-KRW, 종가={asset['close']:,}{cycle_log})")


if __name__ == "__main__":
    main()
