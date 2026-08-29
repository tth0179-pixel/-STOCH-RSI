"""
코스피 시가총액 상위 30개 종목 Stoch RSI 계산 스크립트

- 최초 실행 시 시총 상위 30개 종목을 확정하여 top30_codes.json 에 저장합니다.
  (이후에는 이 파일이 있으면 재계산하지 않고 그대로 사용 -> "고정 리스트")
  리스트를 다시 뽑고 싶으면 top30_codes.json 을 삭제하고 재실행하세요.
- 종목별 일봉 데이터를 받아 주봉/월봉으로 리샘플링합니다.
- Stoch RSI(14,14,3,3) 를 일봉/주봉/월봉 기준으로 각각 계산합니다.
- 결과를 data.json 으로 저장합니다. index.html 이 이 파일을 읽어서 화면에 표시합니다.
"""

import json
import os
from datetime import datetime, timedelta

import pandas as pd
import pandas_ta as ta
from pykrx import stock

CODES_FILE = "top30_codes.json"
OUTPUT_FILE = "data.json"
HISTORY_DAYS = 450  # 월봉 지표 계산까지 안정적으로 나오려면 넉넉한 기간이 필요


def get_top30_codes():
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # 장중에 실행되면 당일 시가총액이 아직 확정되지 않아 빈 데이터가 올 수 있으므로,
    # 데이터가 나올 때까지 하루씩 뒤로 가며 재시도 (최대 10일)
    cap_df = None
    for i in range(10):
        try_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            candidate = stock.get_market_cap(try_date, market="KOSPI")
        except Exception:
            candidate = None
        if candidate is not None and not candidate.empty and "시가총액" in candidate.columns:
            cap_df = candidate
            break

    if cap_df is None:
        raise RuntimeError("최근 10일 내 시가총액 데이터를 찾지 못했습니다.")

    cap_df = cap_df.sort_values("시가총액", ascending=False).head(30)

    codes = []
    for code in cap_df.index:
        name = stock.get_market_ticker_name(code)
        codes.append({"code": code, "name": name})

    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)

    return codes


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
    """차트용: 최근 n개 봉(일/주 공용)의 OHLC + 이동평균(5/20/60) + Stoch %K/%D"""
    merged = df[["시가", "고가", "저가", "종가"]].copy()
    merged["ma5"] = df["종가"].rolling(5).mean()
    merged["ma20"] = df["종가"].rolling(20).mean()
    merged["ma60"] = df["종가"].rolling(60).mean()
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
        for ma_key in ("ma5", "ma20", "ma60"):
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


def main():
    codes = get_top30_codes()

    end = datetime.now()
    start = end - timedelta(days=HISTORY_DAYS)
    start_str, end_str = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    results = []
    for item in codes:
        code, name = item["code"], item["name"]
        try:
            df = stock.get_market_ohlcv(start_str, end_str, code)
            df.index = pd.to_datetime(df.index)
            df = df[df["종가"] > 0]

            daily, daily_stoch_series = calc_stochrsi(df, return_series=True)
            weekly_df = resample_ohlcv(df, "W")
            weekly, weekly_stoch_series = calc_stochrsi(weekly_df, return_series=True)
            monthly = calc_stochrsi(resample_ohlcv(df, "ME"))

            history_daily = build_history(df, daily_stoch_series, n=90)
            history_weekly = build_history(weekly_df, weekly_stoch_series, n=78)  # 약 1.5년치

            last_row = df.iloc[-1]
            prev_close = df.iloc[-2]["종가"] if len(df) > 1 else last_row["종가"]
            change_pct = round((last_row["종가"] - prev_close) / prev_close * 100, 2)

            results.append({
                "code": code,
                "name": name,
                "close": int(last_row["종가"]),
                "change_pct": change_pct,
                "daily": daily,
                "weekly": weekly,
                "monthly": monthly,
                "history": {
                    "daily": history_daily,
                    "weekly": history_weekly,
                },
            })
            print(f"OK  {name}({code})")
        except Exception as e:
            results.append({"code": code, "name": name, "error": str(e)})
            print(f"FAIL {name}({code}): {e}")

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stocks": results,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료: {OUTPUT_FILE} ({len(results)}개 종목)")


if __name__ == "__main__":
    main()
