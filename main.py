import pandas as pd
from datetime import datetime
from google_sheet import GoogleSheetManager
from data_processor import get_exchange_rate, process_asset_df
from report_generator import generate_reports
from telegram_bot import send_telegram_message

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    exchange_rate = get_exchange_rate()
    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. 각 탭 데이터 처리 및 업데이트
    df_us, ws_us = sheet_manager.get_sheet_data('해외주식')
    df_us, us_inv_usd, us_eval_usd = process_asset_df(df_us, '해외주식', is_usd=True)
    if ws_us: sheet_manager.update_sheet(ws_us, df_us)
    
    df_coin, ws_coin = sheet_manager.get_sheet_data('COIN')
    df_coin, coin_inv_krw, coin_eval_krw = process_asset_df(df_coin, '코인', is_usd=False)
    if ws_coin: sheet_manager.update_sheet(ws_coin, df_coin)

    df_pen, ws_pen = sheet_manager.get_sheet_data('개인연금')
    df_pen, pen_inv_krw, pen_eval_krw = process_asset_df(df_pen, '연금저축', is_usd=False)
    if ws_pen: sheet_manager.update_sheet(ws_pen, df_pen)

    # 2. History 누적용 전체 데이터 합치기
    # 모든 종목 데이터에 '기록일자' 컬럼 추가
    df_us['기록일자'] = now_str
    df_coin['기록일자'] = now_str
    df_pen['기록일자'] = now_str
    
    # 공통 컬럼만 뽑아서 합치기 (기록일자, 티커, 현재가, 수량, 평가금액, 수익률 등)
    history_cols = ['기록일자', '티커', '현재가', '수량', '수익률']
    df_all = pd.concat([df_us[history_cols], df_coin[history_cols], df_pen[history_cols]], ignore_index=True)
    
    # History 탭에 상세 데이터 뭉치 추가
    sheet_manager.append_rows_to_history(df_all)

    # 3. 요약 데이터 계산 (Today 탭용)
    us_eval_krw = us_eval_usd * exchange_rate
    us_inv_krw = us_inv_usd * exchange_rate
    
    # (변동폭 계산 로직 생략 - 기존과 동일)
    # ... 중략 (Today 데이터프레임 df_today 생성) ...

    # 4. 리포트 생성 및 전송
    generate_reports(df_today, exchange_rate)
    send_telegram_message(df_today, exchange_rate)
    
    print("🚀 모든 작업이 끝났어! 깃허브에서 확인해봐.")

if __name__ == "__main__":
    main()
