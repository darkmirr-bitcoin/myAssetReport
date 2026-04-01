import pandas as pd
from datetime import datetime

# 분리한 공통 모듈들 불러오기
from google_sheet import GoogleSheetManager
from data_processor import get_exchange_rate, process_asset_df
from html_generator import generate_html_report
from telegram_bot import send_telegram_message

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    
    # 1. 환율 가져오기
    exchange_rate = float(get_exchange_rate())
    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    
    # 2. 각 탭별 데이터 처리 및 구글 시트 업데이트
    df_us, ws_us = sheet_manager.get_sheet_data('해외주식')
    df_us, us_invest_usd, us_eval_usd = process_asset_df(df_us, '해외주식', is_usd=True)
    if ws_us: sheet_manager.update_sheet(ws_us, df_us)
    
    df_coin, ws_coin = sheet_manager.get_sheet_data('COIN')
    df_coin, coin_invest_krw, coin_eval_krw = process_asset_df(df_coin, '코인', is_usd=False)
    if ws_coin: sheet_manager.update_sheet(ws_coin, df_coin)

    df_pen, ws_pen = sheet_manager.get_sheet_data('개인연금')
    df_pen, pen_invest_krw, pen_eval_krw = process_asset_df(df_pen, '연금저축', is_usd=False)
    if ws_pen: sheet_manager.update_sheet(ws_pen, df_pen)

    # 3. 통합 자산 원화(KRW) 환산
    us_invest_krw = float(us_invest_usd * exchange_rate)
    us_eval_krw = float(us_eval_usd * exchange_rate)
    total_invest_krw = float(us_invest_krw + coin_invest_krw + pen_invest_krw)
    total_eval_krw = float(us_eval_krw + coin_eval_krw + pen_eval_krw)
    
    # 4. 전일 대비 변동폭 계산 (History 탭과 비교)
    last_history = sheet_manager.get_latest_history()
    def get_diff(current_val, history_key):
        if last_history is not None and history_key in last_history:
            try:
                val = last_history[history_key]
                if isinstance(val, pd.Series): val = val.iloc[0]
                past_val = float(str(val).replace(',', ''))
                return float(current_val - past_val)
            except: pass
        return 0.0

    diff_us = get_diff(us_eval_krw, '해외주식(₩)')
    diff_coin = get_diff(coin_eval_krw, 'COIN(₩)')
    diff_pen = get_diff(pen_eval_krw, '개인연금(₩)')
    diff_total = get_diff(total_eval_krw, '총자산(₩)')

    # 5. Today 요약 데이터프레임 생성
    today_data = {
        '자산군': ['해외주식 (USD 변환)', 'COIN', '개인연금', '총 자산'],
        '투자원금(₩)': [int(us_invest_krw), int(coin_invest_krw), int(pen_invest_krw), int(total_invest_krw)],
        '평가금액(₩)': [int(us_eval_krw), int(coin_eval_krw), int(pen_eval_krw), int(total_eval_krw)],
        '평가손익(₩)': [int(us_eval_krw - us_invest_krw), int(coin_eval_krw - coin_invest_krw), int(pen_eval_krw - pen_invest_krw), int(total_eval_krw - total_invest_krw)],
        '수익률(%)': [
            float((us_eval_krw - us_invest_krw) / us_invest_krw) if us_invest_krw > 0 else 0.0,
            float((coin_eval_krw - coin_invest_krw) / coin_invest_krw) if coin_invest_krw > 0 else 0.0,
            float((pen_eval_krw - pen_invest_krw) / pen_invest_krw) if pen_invest_krw > 0 else 0.0,
            float((total_eval_krw - total_invest_krw) / total_invest_krw) if total_invest_krw > 0 else 0.0
        ],
        '전일대비 변동폭(₩)': [int(diff_us), int(diff_coin), int(diff_pen), int(diff_total)]
    }
    df_today = pd.DataFrame(today_data)
    
    # Today 탭 업데이트
    _, ws_today = sheet_manager.get_sheet_data('Today')
    if ws_today:
        sheet_manager.update_sheet(ws_today, df_today)
        print("✅ 구글 시트 Today 탭 업데이트 완료!")

    # 6. History 탭 데이터 한 줄 누적
    history_row = {
        '일자': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '적용환율': float(exchange_rate),
        '해외주식(₩)': int(us_eval_krw),
        'COIN(₩)': int(coin_eval_krw),
        '개인연금(₩)': int(pen_eval_krw),
        '총자산(₩)': int(total_eval_krw)
    }
    sheet_manager.append_to_history(history_row)

    # 7. HTML 리포트 생성 (GitHub Pages용)
    generate_html_report(df_today, exchange_rate)

    # 8. 텔레그램 메시지 발송
    send_telegram_message(df_today, exchange_rate)
    
    print("🚀 모든 파이프라인 작업이 성공적으로 끝났어!")

if __name__ == "__main__":
    main()
