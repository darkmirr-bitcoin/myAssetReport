from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import pandas as pd
import requests
import yfinance as yf


@dataclass
class AssetSignal:
    ticker: str
    asset_type: str        # '해외주식', '코인', '연금저축'
    strategy: str          # '장기', '단기', '헷징'
    signal: str            # '[전량 매도]', '[분할 익절]', '[매수]', '[차익 실현]', '[홀딩]', '[주의/관망]'
    reasons: List[str]     # 기계적으로 발동된 사유 목록
    return_pct: float
    metrics: Dict[str, Any]


def fetch_ohlcv(ticker: str, asset_type: str, count: int = 120) -> Optional[pd.DataFrame]:
    """자산군에 맞춰 최소 60일 이상의 일봉 OHLCV(Close, Volume)를 수집한다."""
    clean_ticker = ticker.split(":")[-1].strip().upper()

    # 1) 코인: 업비트 원화 마켓 우선 조회 (키 불필요, 알트코인 누락 방지)
    if asset_type == "코인":
        try:
            url = "https://api.upbit.com/v1/candles/days"
            params = {"market": f"KRW-{clean_ticker}", "count": min(count, 200)}
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                rows = res.json()
                if len(rows) >= 35:
                    df = pd.DataFrame(rows)
                    df = df.iloc[::-1].reset_index(drop=True)  # 과거 -> 최신 정렬
                    df = df.rename(columns={
                        "trade_price": "Close",
                        "candle_acc_trade_volume": "Volume",
                    })
                    return df[["Close", "Volume"]].astype(float)
        except Exception as e:
            print(f"⚠️ 업비트 조회 실패 ({clean_ticker}), yfinance 폴백 시도: {e}")

        # 업비트 미상장 코인은 yfinance USD 페어 폴백
        clean_ticker = f"{clean_ticker}-USD"

    # 2) 해외주식 및 폴백 코인: yfinance 조회
    try:
        hist = yf.Ticker(clean_ticker).history(period="6mo", interval="1d")
        if hist is not None and len(hist) >= 35:
            return hist[["Close", "Volume"]].dropna().astype(float)
    except Exception as e:
        print(f"❌ OHLCV 조회 실패 ({ticker}): {e}")

    return None


def calculate_indicators(df: pd.DataFrame, use_prev_closed: bool = False) -> Dict[str, float]:
    """EMA5/20, 볼린저밴드(20, 2), MACD(12, 26, 9), RSI(14), 거래량 강도를 계산한다."""
    close = df["Close"]
    volume = df["Volume"]

    # EMA
    ema5 = close.ewm(span=5, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()

    # Bollinger Bands (20, 2)
    sma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std(ddof=0)
    bb_upper = sma20 + (2 * std20)
    bb_lower = sma20 - (2 * std20)
    bb_width = bb_upper - bb_lower
    bb_pct_b = (close - bb_lower) / bb_width.replace(0, pd.NA)

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # RSI (14, Wilder 방식)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    # 거래량 강도 (20일 평균 대비 %)
    vol_ma20 = volume.rolling(window=20).mean()
    vol_ratio = (volume / vol_ma20.replace(0, pd.NA)) * 100

    # 코인은 미완성 당일봉 휩소 방지를 위해 직전 마감봉(-2) 선택 가능
    idx = -2 if (use_prev_closed and len(df) >= 2) else -1
    prev_idx = idx - 1

    return {
        "close": round(float(close.iloc[idx]), 4),
        "ema5": round(float(ema5.iloc[idx]), 4),
        "ema20": round(float(ema20.iloc[idx]), 4),
        "bb_upper": round(float(bb_upper.iloc[idx]), 4),
        "bb_mid": round(float(sma20.iloc[idx]), 4),
        "bb_lower": round(float(bb_lower.iloc[idx]), 4),
        "bb_pct_b": round(float(bb_pct_b.iloc[idx]) * 100, 1) if pd.notna(bb_pct_b.iloc[idx]) else 50.0,
        "macd_hist": round(float(macd_hist.iloc[idx]), 4),
        "prev_macd_hist": round(float(macd_hist.iloc[prev_idx]), 4),
        "rsi": round(float(rsi.iloc[idx]), 1) if pd.notna(rsi.iloc[idx]) else 50.0,
        "vol_ratio": round(float(vol_ratio.iloc[idx]), 1) if pd.notna(vol_ratio.iloc[idx]) else 100.0,
    }


def resolve_strategy(ticker: str, asset_type: str, sheet_strategy: Optional[str] = None) -> str:
    """시트 전략 컬럼이 있으면 우선 사용, 없으면 자산군·티커 기준 기본값 매핑."""
    if sheet_strategy and str(sheet_strategy).strip() in ("장기", "단기", "헷징"):
        return str(sheet_strategy).strip()
    if asset_type == "연금저축":
        return "장기"
    if ticker.upper() in ("VIXY", "UVXY", "SQQQ"):
        return "헷징"
    return "단기"


def evaluate_signal(
    ticker: str,
    asset_type: str,
    strategy: str,
    return_pct: float,
    metrics: Dict[str, float],
    fng_score: int,
    fng_buy_threshold: int = 30,
) -> AssetSignal:
    """100% 결정론적 규칙으로 최종 매매 시그널을 확정한다."""
    # 1. 장기 트랙
    if strategy == "장기":
        return AssetSignal(
            ticker=ticker,
            asset_type=asset_type,
            strategy=strategy,
            signal="[홀딩]",
            reasons=["장기 적립 트랙: 단기 기술적 노이즈 무시"],
            return_pct=return_pct,
            metrics=metrics,
        )

    close = metrics["close"]
    ema5 = metrics["ema5"]
    ema20 = metrics["ema20"]
    bb_upper = metrics["bb_upper"]
    bb_lower = metrics["bb_lower"]
    macd_hist = metrics["macd_hist"]
    prev_macd_hist = metrics["prev_macd_hist"]
    rsi = metrics["rsi"]

    # 2. 헷징 트랙
    if strategy == "헷징":
        reasons = []
        if close >= bb_upper:
            reasons.append(f"볼린저 상단({bb_upper}) 돌파")
        if rsi >= 70:
            reasons.append(f"RSI 과열({rsi})")

        if reasons:
            return AssetSignal(ticker, asset_type, strategy, "[차익 실현]", reasons, return_pct, metrics)
        return AssetSignal(
            ticker, asset_type, strategy, "[주의/관망]",
            ["헷징 자산 장기 보유 시 음의 복리 위험, 급등 시 즉시 청산 대기"],
            return_pct, metrics,
        )

    # 3. 단기 고위험 트랙 (방어 우선순위 적용)
    sell_reasons = []
    if close < ema5:
        sell_reasons.append(f"EMA5({ema5}) 하향 이탈")
    if close < ema20:
        sell_reasons.append(f"EMA20({ema20}) 하향 이탈")
    if macd_hist < 0:
        tag = "MACD 데드크로스 신규 발생" if prev_macd_hist >= 0 else "MACD 음수 추세 지속"
        sell_reasons.append(f"{tag}({macd_hist})")

    if sell_reasons:
        return AssetSignal(ticker, asset_type, strategy, "[전량 매도]", sell_reasons, return_pct, metrics)

    if close >= bb_upper:
        return AssetSignal(
            ticker, asset_type, strategy, "[분할 익절]",
            [f"볼린저 상단({bb_upper}) 터치/돌파 (BB 위치 {metrics['bb_pct_b']}%) → 30~50% 분할 매도"],
            return_pct, metrics,
        )

    if fng_score <= fng_buy_threshold and close <= bb_lower:
        return AssetSignal(
            ticker, asset_type, strategy, "[매수]",
            [f"공포탐욕 {fng_score}점(<= {fng_buy_threshold}) + 볼린저 하단({bb_lower}) 이탈"],
            return_pct, metrics,
        )

    return AssetSignal(
        ticker, asset_type, strategy, "[홀딩]",
        [f"EMA5/20 상단 유지 & MACD 양수({macd_hist})"],
        return_pct, metrics,
    )


def run_quant_scan(
    df_assets: pd.DataFrame,
    asset_type: str,
    fng_score: int,
) -> List[Dict[str, Any]]:
    """시트 DataFrame을 순회하며 전 종목의 결정론적 시그널을 산출한다."""
    results = []
    if df_assets is None or df_assets.empty:
        return results

    for _, row in df_assets.iterrows():
        ticker = str(row.get("티커", "")).strip()
        if not ticker or ticker == "nan":
            continue

        # 수익률 문자열/실수 안전 파싱
        raw_ret = str(row.get("수익률(%)", 0)).replace("%", "").replace(",", "").strip()
        try:
            return_pct = float(raw_ret)
        except ValueError:
            return_pct = 0.0

        strategy = resolve_strategy(ticker, asset_type, row.get("전략"))

        # 장기 자산은 불필요한 시세 API 호출 생략
        if strategy == "장기":
            sig = evaluate_signal(ticker, asset_type, strategy, return_pct, {}, fng_score)
            results.append(asdict(sig))
            continue

        ohlcv = fetch_ohlcv(ticker, asset_type)
        if ohlcv is None:
            results.append(asdict(AssetSignal(
                ticker=ticker, asset_type=asset_type, strategy=strategy,
                signal="[데이터 없음]", reasons=["차트 시세 조회 실패"],
                return_pct=return_pct, metrics={},
            )))
            continue

        metrics = calculate_indicators(ohlcv, use_prev_closed=(asset_type == "코인"))
        sig = evaluate_signal(ticker, asset_type, strategy, return_pct, metrics, fng_score)
        results.append(asdict(sig))

    return results
