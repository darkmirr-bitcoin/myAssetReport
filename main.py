from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yfinance as yf


# 구글 시트에 '전략' 컬럼이 비어 있을 때 사용하는 기본 티커 매핑
# 시트에 직접 '장기' / '추세단기' / '역발상우량' / '헷징'을 적으면 시트 값이 최우선 적용됨
VALID_STRATEGIES = ("장기", "추세단기", "역발상우량", "헷징")

DEFAULT_LONG_TERM_TICKERS = {
    "TLT", "TMF", "IEF", "SHY", "SGOV",
    "SPY", "VOO", "QQQ", "QQQM", "SCHD", "GLD",
}
DEFAULT_HEDGING_TICKERS = {"VIXY", "UVXY", "VXX", "SQQQ", "SPXS"}
DEFAULT_CONTRARIAN_TICKERS = {
    "BTC", "ETH",
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSM",
}


@dataclass
class AssetSignal:
    ticker: str
    asset_type: str        # '해외주식', '코인', '연금저축'
    strategy: str          # '장기', '추세단기', '역발상우량', '헷징'
    signal: str            # '[전량 매도]', '[차익 실현]', '[분할 익절]', '[매수]', '[주의/관망]', '[홀딩]', '[데이터 없음]'
    reasons: List[str]     # 기계적으로 발동된 사유 목록
    return_pct: float
    metrics: Dict[str, Any]


def normalize_ticker(ticker: str) -> str:
    """거래소 접두사(NASDAQ:, KRW-) 등을 제거해 순수 티커를 추출한다."""
    clean = str(ticker).strip().upper()
    if ":" in clean:
        clean = clean.split(":")[-1]
    if clean.startswith("KRW-"):
        clean = clean[4:]
    if clean.endswith("-USD"):
        clean = clean[:-4]
    return clean


def fetch_ohlcv(ticker: str, asset_type: str, count: int = 120) -> Optional[pd.DataFrame]:
    """자산군에 맞춰 최소 35일 이상의 일봉 OHLCV(Close, Volume)를 수집한다."""
    clean_ticker = normalize_ticker(ticker)

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
                    df = df.rename(
                        columns={
                            "trade_price": "Close",
                            "candle_acc_trade_volume": "Volume",
                        }
                    )
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

    # 코인은 미완성 당일봉 휩소 방지를 위해 직전 마감봉(-2) 사용
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


def resolve_strategy(
    ticker: str,
    asset_type: str,
    sheet_strategy: Optional[str] = None,
) -> str:
    """시트 전략 컬럼을 최우선 적용하고, 누락 시 자산군·티커 기본값으로 매핑한다."""
    if sheet_strategy is not None and pd.notna(sheet_strategy):
        raw = str(sheet_strategy).strip()
        if raw in VALID_STRATEGIES:
            return raw
        # 이전 버전 시트에 '단기'라고 적혀 있으면 보수적으로 '추세단기'로 취급
        if raw == "단기":
            return "추세단기"

    clean = normalize_ticker(ticker)
    if asset_type == "연금저축" or clean in DEFAULT_LONG_TERM_TICKERS:
        return "장기"
    if clean in DEFAULT_HEDGING_TICKERS:
        return "헷징"
    if clean in DEFAULT_CONTRARIAN_TICKERS:
        return "역발상우량"

    # 알트코인 및 고베타 개별주(MSTR, COIN, SOL, SUI, STX 등)는 기본 '추세단기'
    return "추세단기"


def evaluate_signal(
    ticker: str,
    asset_type: str,
    strategy: str,
    return_pct: float,
    metrics: Dict[str, float],
    fng_score: int,
    fng_buy_threshold: int = 30,
) -> AssetSignal:
    """4개 전략 트랙별 결정론적 규칙으로 최종 매매 시그널을 확정한다."""
    # -------------------------------------------------
    # 1. 장기 트랙 (연금/ISA ETF, 국채 등)
    # -------------------------------------------------
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
    bb_pct_b = metrics["bb_pct_b"]
    macd_hist = metrics["macd_hist"]
    prev_macd_hist = metrics["prev_macd_hist"]
    rsi = metrics["rsi"]

    # -------------------------------------------------
    # 2. 헷징 트랙 (VIXY 등 변동성 상품)
    # -------------------------------------------------
    if strategy == "헷징":
        reasons = []
        if close >= bb_upper:
            reasons.append(f"볼린저 상단({bb_upper}) 돌파")
        if rsi >= 70:
            reasons.append(f"RSI 과열({rsi})")

        if reasons:
            return AssetSignal(ticker, asset_type, strategy, "[차익 실현]", reasons, return_pct, metrics)
        return AssetSignal(
            ticker,
            asset_type,
            strategy,
            "[주의/관망]",
            ["헷징 자산 장기 보유 시 음의 복리 위험, 급등 시 즉시 청산 대기"],
            return_pct,
            metrics,
        )

    # -------------------------------------------------
    # 3. 추세단기 트랙 (알트코인, 고베타 개별주)
    #    - 역발상 [매수] 분기 없음 (추세 이탈 종목 물타기 원천 차단)
    #    - EMA20 이탈 + MACD 음수가 동시에 충족될 때만 [전량 매도]
    # -------------------------------------------------
    if strategy == "추세단기":
        if close < ema20 and macd_hist < 0:
            macd_tag = "MACD 데드크로스 신규" if prev_macd_hist >= 0 else "MACD 음수 추세"
            return AssetSignal(
                ticker,
                asset_type,
                strategy,
                "[전량 매도]",
                [f"중기 추세 붕괴: EMA20({ema20}) 하향 이탈 + {macd_tag}({macd_hist})"],
                return_pct,
                metrics,
            )

        take_profit_reasons = []
        if close >= bb_upper:
            take_profit_reasons.append(f"볼린저 상단({bb_upper}) 돌파 (BB {bb_pct_b}%)")
        if rsi >= 75:
            take_profit_reasons.append(f"RSI 과열({rsi})")
        if take_profit_reasons:
            take_profit_reasons.append("30~50% 분할 익절 구간")
            return AssetSignal(
                ticker, asset_type, strategy, "[분할 익절]", take_profit_reasons, return_pct, metrics
            )

        warn_reasons = []
        if close < ema5:
            warn_reasons.append(f"단기 EMA5({ema5}) 이탈")
        if prev_macd_hist >= 0 and macd_hist < 0:
            warn_reasons.append(f"MACD 데드크로스 신규 발생({macd_hist})")
        if close < ema20:
            warn_reasons.append(f"EMA20({ema20}) 단독 하회 (MACD 아직 양수)")
        if warn_reasons:
            return AssetSignal(
                ticker, asset_type, strategy, "[주의/관망]", warn_reasons, return_pct, metrics
            )

        return AssetSignal(
            ticker,
            asset_type,
            strategy,
            "[홀딩]",
            [f"단기·중기 추세 정상 유지 (EMA5 {ema5} / EMA20 {ema20} 상단)"],
            return_pct,
            metrics,
        )

    # -------------------------------------------------
    # 4. 역발상우량 트랙 (BTC, 핵심 빅테크 등)
    #    - 공포 구간 + 과매도 시 [매수]를 최우선 평가
    #    - 일반 하락 추세에서는 손절 대신 물타기 대기([주의/관망])
    # -------------------------------------------------
    if strategy == "역발상우량":
        oversold_reasons = []
        if close <= bb_lower:
            oversold_reasons.append(f"볼린저 하단({bb_lower}) 이탈 (BB {bb_pct_b}%)")
        if rsi <= 30:
            oversold_reasons.append(f"RSI 과매도({rsi})")

        if fng_score <= fng_buy_threshold and oversold_reasons:
            buy_reasons = [f"CNN 공포탐욕 {fng_score}점(<= {fng_buy_threshold})"] + oversold_reasons
            return AssetSignal(ticker, asset_type, strategy, "[매수]", buy_reasons, return_pct, metrics)

        take_profit_reasons = []
        if close >= bb_upper:
            take_profit_reasons.append(f"볼린저 상단({bb_upper}) 돌파 (BB {bb_pct_b}%)")
        if rsi >= 75:
            take_profit_reasons.append(f"RSI 과열({rsi})")
        if take_profit_reasons:
            take_profit_reasons.append("과열 구간 일부 분할 익절 고려")
            return AssetSignal(
                ticker, asset_type, strategy, "[분할 익절]", take_profit_reasons, return_pct, metrics
            )

        if close < ema20 and macd_hist < 0:
            return AssetSignal(
                ticker,
                asset_type,
                strategy,
                "[주의/관망]",
                [
                    f"중기 추세 약화(EMA20 {ema20} 하회 + MACD {macd_hist}) — "
                    f"공포지수 {fng_buy_threshold} 이하(현재 {fng_score}점) 도달 전 추격 물타기 금지"
                ],
                return_pct,
                metrics,
            )

        return AssetSignal(
            ticker,
            asset_type,
            strategy,
            "[홀딩]",
            [f"우량 자산 추세 안정 유지 (BB {bb_pct_b}% / RSI {rsi})"],
            return_pct,
            metrics,
        )

    return AssetSignal(ticker, asset_type, strategy, "[홀딩]", ["기본 홀딩"], return_pct, metrics)


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
        if not ticker or ticker.lower() == "nan":
            continue

        raw_ret = str(row.get("수익률(%)", 0)).replace("%", "").replace(",", "").strip()
        try:
            return_pct = float(raw_ret)
        except ValueError:
            return_pct = 0.0

        strategy = resolve_strategy(ticker, asset_type, row.get("전략"))

        # 장기 트랙은 차트 API 호출 생략
        if strategy == "장기":
            sig = evaluate_signal(ticker, asset_type, strategy, return_pct, {}, fng_score)
            results.append(asdict(sig))
            continue

        ohlcv = fetch_ohlcv(ticker, asset_type)
        if ohlcv is None:
            results.append(
                asdict(
                    AssetSignal(
                        ticker=ticker,
                        asset_type=asset_type,
                        strategy=strategy,
                        signal="[데이터 없음]",
                        reasons=["차트 시세 조회 실패"],
                        return_pct=return_pct,
                        metrics={},
                    )
                )
            )
            continue

        metrics = calculate_indicators(ohlcv, use_prev_closed=(asset_type == "코인"))
        sig = evaluate_signal(ticker, asset_type, strategy, return_pct, metrics, fng_score)
        results.append(asdict(sig))

    return results
