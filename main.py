import html
import os
import re
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import pytz

from ai_commentator import generate_ai_commentary
from data_processor import check_market_open, get_exchange_rate, process_asset_df
from google_sheet import GoogleSheetManager
from macro_data import (
    fetch_telegram_macro,
    get_fear_and_greed,
    get_market_indices,
    get_treasury_yields,
)
from quant_engine import run_quant_scan
from report_generator import generate_reports
from telegram_bot import send_telegram_message


SIGNAL_STYLES = {
    "[전량 매도]": ("#ff4d4d", 1),
    "[차익 실현]": ("#9b59b6", 2),
    "[분할 익절]": ("#ff9933", 3),
    "[매수]": ("#3399ff", 4),
    "[주의/관망]": ("#6c757d", 5),
    "[홀딩]": ("#2eb82e", 6),
    "[데이터 없음]": ("#95a5a6", 7),
}


def extract_fng_score(fng_result: Any, default: int = 50) -> tuple[str, int]:
    """macro_data.py 수정 여부와 무관하게 (텍스트, 공포탐욕 정수)를 안전하게 추출한다."""
    if isinstance(fng_result, tuple) and len(fng_result) >= 2:
        return str(fng_result[0]), int(fng_result[1])

    fng_text = str(fng_result or "")
    match = re.search(r"CNN\s*공포탐욕\s*지수:\s*(\d+)\s*점", fng_text)
    score = int(match.group(1)) if match else default
    return fng_text, score


def make_badge(signal: str) -> str:
    color, _ = SIGNAL_STYLES.get(signal, ("#6c757d", 99))
    safe_signal = html.escape(signal)
    return (
        f'<span style="background-color: {color}; color: white; '
        f'padding: 3px 8px; border-radius: 5px; font-weight: bold; '
        f'font-size: 0.85em; margin-right: 6px;">{safe_signal}</span>'
    )


def render_action_board_html(
    signals: List[Dict[str, Any]],
    commentary: Dict[str, Any],
) -> str:
    """결정론적 시그널과 AI 해설을 안전한 HTML 리스트로 렌더링한다."""
    action_comments = commentary.get("action_comments", {}) or {}
    portfolio_brief = commentary.get("portfolio_brief", "")

    action_items = [s for s in signals if s["signal"] not in ("[홀딩]", "[데이터 없음]")]
    holding_items = [s for s in signals if s["signal"] == "[홀딩]"]
    error_items = [s for s in signals if s["signal"] == "[데이터 없음]"]

    # 방어 우선순위 순으로 정렬 (전량 매도 -> 차익 실현 -> 분할 익절 -> 매수 -> 주의/관망)
    action_items.sort(key=lambda x: SIGNAL_STYLES.get(x["signal"], ("#6c757d", 99))[1])

    blocks = []

    if portfolio_brief:
        blocks.append(
            f'<p style="margin-top: 0; margin-bottom: 14px; color: #2c3e50;">'
            f'<strong>🧭 오늘의 총평:</strong> {html.escape(str(portfolio_brief))}</p>'
        )

    if action_items:
        li_tags = []
        for item in action_items:
            ticker = item["ticker"]
            badge = make_badge(item["signal"])
            reasons_str = " / ".join(item.get("reasons", []))
            metrics = item.get("metrics", {}) or {}
            ai_comment = action_comments.get(ticker, "")

            metric_line = ""
            if metrics:
                metric_line = (
                    f"<div style='font-size: 0.85em; color: #666; margin-top: 3px;'>"
                    f"종가 {metrics.get('close')} | EMA5 {metrics.get('ema5')} | "
                    f"EMA20 {metrics.get('ema20')} | BB위치 {metrics.get('bb_pct_b')}% | "
                    f"RSI {metrics.get('rsi')} | MACD {metrics.get('macd_hist')}</div>"
                )

            comment_line = ""
            if ai_comment:
                comment_line = (
                    f"<div style='font-size: 0.92em; color: #333; margin-top: 4px;'>"
                    f"💬 {html.escape(str(ai_comment))}</div>"
                )

            li_tags.append(
                f"<li style='margin-bottom: 12px; list-style: none;'>"
                f"{badge}<strong>{html.escape(ticker)}</strong> "
                f"<span style='font-size: 0.85em; color: #888;'>({html.escape(item['asset_type'])} · {html.escape(item['strategy'])})</span>"
                f"<div style='font-size: 0.9em; color: #444; margin-top: 3px;'>📌 룰 근거: {html.escape(reasons_str)}</div>"
                f"{metric_line}"
                f"{comment_line}"
                f"</li>"
            )

        blocks.append(f"<ul style='padding-left: 0; margin: 0;'>{''.join(li_tags)}</ul>")
    else:
        blocks.append(
            "<p style='margin: 8px 0; color: #2eb82e; font-weight: bold;'>"
            "✅ 오늘 즉각 매매 액션이 필요한 종목이 없습니다. 전 종목 추세 유지 중입니다.</p>"
        )

    if holding_items:
        hold_tickers = ", ".join(html.escape(s["ticker"]) for s in holding_items)
        blocks.append(
            f"<div style='margin-top: 12px; padding-top: 10px; border-top: 1px dashed #ddd; "
            f"font-size: 0.9em; color: #555;'>"
            f"{make_badge('[홀딩]')} {hold_tickers}</div>"
        )

    if error_items:
        err_tickers = ", ".join(html.escape(s["ticker"]) for s in error_items)
        blocks.append(
            f"<div style='margin-top: 8px; font-size: 0.85em; color: #95a5a6;'>"
            f"⚠️ 시세 조회 실패(수동 확인 필요): {err_tickers}</div>"
        )

    return "\n".join(blocks)


def main():
    SPREADSHEET_ID = os.environ.get(
        "SPREADSHEET_ID", "1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o"
    )
    exchange_rate = get_exchange_rate()
    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)

    # 1. 기준 시각 세팅 (History 기록은 KST, 미국장 리포트 기준일은 NY)
    tz_kst = pytz.timezone("Asia/Seoul")
    tz_ny = pytz.timezone("America/New_York")
    now_str = datetime.now(tz_kst).strftime("%Y-%m-%d %H:%M:%S")
    us_date_str = datetime.now(tz_ny).strftime("%Y-%m-%d")

    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")
    print(f"🚀 시즌2 퀀트 파이프라인 가동 시작 (US: {us_date_str} / KST: {now_str})")

    # ------------------------------------
    # 2. 매크로 데이터 수집
    # ------------------------------------
    print("📊 매크로 데이터 및 텔레그램 마감 브리핑 수집 중...")
    indices_data = get_market_indices()
    yields_data = get_treasury_yields()
    fng_raw = get_fear_and_greed(indices_data, yields_data)
    fng_text, fng_score = extract_fng_score(fng_raw)
    telegram_raw = fetch_telegram_macro()

    print(f"🧭 추출된 공포탐욕 지수: {fng_score}점")

    macro_data = {
        "indices": indices_data,
        "yields": yields_data,
        "fng": fng_text,
        "fng_score": fng_score,
        "telegram": telegram_raw,
    }

    # 휴장일 체크
    is_us_open = check_market_open("해외주식")
    is_kr_open = check_market_open("연금저축")

    # ------------------------------------
    # 3. 각 탭 데이터 처리 및 구글 시트 업데이트
    # ------------------------------------
    df_us, ws_us = sheet_manager.get_sheet_data("해외주식")
    df_us, us_inv_usd, us_eval_usd = process_asset_df(
        df_us, "해외주식", is_usd=True, is_open=is_us_open
    )
    if ws_us:
        sheet_manager.update_sheet(ws_us, df_us)

    df_coin, ws_coin = sheet_manager.get_sheet_data("COIN")
    df_coin, coin_inv_krw, coin_eval_krw = process_asset_df(
        df_coin, "코인", is_usd=False, is_open=True
    )
    if ws_coin:
        sheet_manager.update_sheet(ws_coin, df_coin)

    df_pen, ws_pen = sheet_manager.get_sheet_data("개인연금")
    df_pen, pen_inv_krw, pen_eval_krw = process_asset_df(
        df_pen, "연금저축", is_usd=False, is_open=is_kr_open
    )
    if ws_pen:
        sheet_manager.update_sheet(ws_pen, df_pen)

    # ------------------------------------
    # 4. History 누적 적재
    # ------------------------------------
    history_cols = ["기록일자", "티커", "현재가", "수량", "수익률(%)"]
    history_frames = []
    for df in (df_us, df_coin, df_pen):
        if df is not None and not df.empty:
            df["기록일자"] = now_str
            valid_cols = [c for c in history_cols if c in df.columns]
            history_frames.append(df[valid_cols])

    if history_frames:
        df_all = pd.concat(history_frames, ignore_index=True)
        sheet_manager.append_rows_to_history(df_all)

    # ------------------------------------
    # 5. 요약 데이터 계산 (Today 탭 업데이트)
    # ------------------------------------
    us_inv_krw = float(us_inv_usd * exchange_rate)
    us_eval_krw = float(us_eval_usd * exchange_rate)
    total_inv_krw = float(us_inv_krw + coin_inv_krw + pen_inv_krw)
    total_eval_krw = float(us_eval_krw + coin_eval_krw + pen_eval_krw)

    last_today_summary = sheet_manager.get_latest_history_summary()

    def get_diff_from_today(current_val: float, asset_name: str) -> float:
        if last_today_summary is not None and not last_today_summary.empty:
            try:
                row = last_today_summary[last_today_summary["자산군"] == asset_name]
                if not row.empty:
                    past_val_str = (
                        str(row.iloc[0]["평가금액(₩)"]).replace(",", "").replace("₩", "")
                    )
                    return float(current_val - float(past_val_str))
            except Exception:
                pass
        return 0.0

    diff_us = get_diff_from_today(us_eval_krw, "해외주식 (USD 변환)")
    diff_coin = get_diff_from_today(coin_eval_krw, "COIN")
    diff_pen = get_diff_from_today(pen_eval_krw, "개인연금")
    diff_total = get_diff_from_today(total_eval_krw, "총 자산")

    today_data = {
        "자산군": ["해외주식 (USD 변환)", "COIN", "개인연금", "총 자산"],
        "투자원금(₩)": [
            int(us_inv_krw),
            int(coin_inv_krw),
            int(pen_inv_krw),
            int(total_inv_krw),
        ],
        "평가금액(₩)": [
            int(us_eval_krw),
            int(coin_eval_krw),
            int(pen_eval_krw),
            int(total_eval_krw),
        ],
        "평가손익(₩)": [
            int(us_eval_krw - us_inv_krw),
            int(coin_eval_krw - coin_inv_krw),
            int(pen_eval_krw - pen_inv_krw),
            int(total_eval_krw - total_inv_krw),
        ],
        "수익률(%)": [
            float((us_eval_krw - us_inv_krw) / us_inv_krw) if us_inv_krw > 0 else 0.0,
            float((coin_eval_krw - coin_inv_krw) / coin_inv_krw)
            if coin_inv_krw > 0
            else 0.0,
            float((pen_eval_krw - pen_inv_krw) / pen_inv_krw)
            if pen_inv_krw > 0
            else 0.0,
            float((total_eval_krw - total_inv_krw) / total_inv_krw)
            if total_inv_krw > 0
            else 0.0,
        ],
        "전일대비 변동폭(₩)": [
            int(diff_us),
            int(diff_coin),
            int(diff_pen),
            int(diff_total),
        ],
    }
    df_today = pd.DataFrame(today_data)

    _, ws_today = sheet_manager.get_sheet_data("Today")
    if ws_today:
        sheet_manager.update_sheet(ws_today, df_today)
        print("✅ Today 탭 업데이트 완료!")

    # ------------------------------------
    # 6. 시즌2 코어: 결정론적 지표 스캔 + AI 해설
    # ------------------------------------
    print("📐 전 종목 차트 지표 계산 및 룰 엔진 판정 중...")
    all_signals = []
    all_signals.extend(run_quant_scan(df_us, "해외주식", fng_score))
    all_signals.extend(run_quant_scan(df_coin, "코인", fng_score))
    all_signals.extend(run_quant_scan(df_pen, "연금저축", fng_score))

    action_cnt = sum(
        1 for s in all_signals if s["signal"] not in ("[홀딩]", "[데이터 없음]")
    )
    print(f"✅ 룰 엔진 스캔 완료: 전체 {len(all_signals)}종목 중 액션 대상 {action_cnt}건")

    print("🧠 Gemini AI 시황 3줄 요약 및 실행 해설 생성 중...")
    macro_summary_text = f"{indices_data}\n{yields_data}\n{fng_text}"
    commentary = generate_ai_commentary(
        signals=all_signals,
        telegram_raw=telegram_raw,
        macro_summary=macro_summary_text,
        us_date_str=us_date_str,
    )

    # AI가 요약한 텔레그램 브리핑으로 교체
    if commentary.get("telegram_summary"):
        macro_data["telegram"] = commentary["telegram_summary"]

    ai_action_html = render_action_board_html(all_signals, commentary)

    # ------------------------------------
    # 7. HTML/MD 리포트 렌더링 및 텔레그램 전송
    # ------------------------------------
    print("🎨 HTML 웹 리포트 렌더링 중...")
    generate_reports(
        df_today,
        exchange_rate,
        macro_data=macro_data,
        us_date_str=us_date_str,
        ai_action_html=ai_action_html,
    )

    print("📨 텔레그램 메시지 발송 중...")
    send_telegram_message(df_today, exchange_rate)

    print("🎯 시즌2 파이프라인 정상 종료!")


if __name__ == "__main__":
    main()
