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

    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

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

    # 2. History 누적용 전체 데이터 합치기 (모든 종목 상세 누적)
    df_us['기록일자'] = now_str
    df_coin['기록일자'] = now_str
    df_pen['기록일자'] = now_str
    
    history_cols = ['기록일자', '티커', '현재가', '수량', '수익률']
    df_all = pd.concat([df_us[history_cols], df_coin[history_cols], df_pen[history_cols]], ignore_index=True)
    
    # History 탭에 상세 데이터 뭉치 추가
    sheet_manager.append_rows_to_history(df_all)

    # 3. 요약 데이터 계산 (Today 탭용)
    us_inv_krw = float(us_inv_usd * exchange_rate)
    us_eval_krw = float(us_eval_usd * exchange_rate)
    
    total_inv_krw = float(us_inv_krw + coin_inv_krw + pen_inv_krw)
    total_eval_krw = float(us_eval_krw + coin_eval_krw + pen_eval_krw)

    # 전일 대비 변동폭 계산 (업데이트 되기 전의 기존 'Today' 탭을 읽어와서 비교)
    last_today_summary = sheet_manager.get_latest_history_summary()
    
    def get_diff_from_today(current_val, asset_name):
        if last_today_summary is not None and not last_today_summary.empty:
            try:
                row = last_today_summary[last_today_summary['자산군'] == asset_name]
                if not row.empty:
                    # 콤마(,)와 원화(₩) 기호 제거 후 실수 변환
                    past_val_str = str(row.iloc[0]['평가금액(₩)']).replace(',', '').replace('₩', '')
                    past_val = float(past_val_str)
                    return float(current_val - past_val)
            except: pass
        return 0.0

    diff_us = get_diff_from_today(us_eval_krw, '해외주식 (USD 변환)')
    diff_coin = get_diff_from_today(coin_eval_krw, 'COIN')
    diff_pen = get_diff_from_today(pen_eval_krw, '개인연금')
    diff_total = get_diff_from_today(total_eval_krw, '총 자산')

    # df_today 완벽 생성
    today_data = {
        '자산군': ['해외주식 (USD 변환)', 'COIN', '개인연금', '총 자산'],
        '투자원금(₩)': [int(us_inv_krw), int(coin_inv_krw), int(pen_inv_krw), int(total_inv_krw)],
        '평가금액(₩)': [int(us_eval_krw), int(coin_eval_krw), int(pen_eval_krw), int(total_eval_krw)],
        '평가손익(₩)': [int(us_eval_krw - us_inv_krw), int(coin_eval_krw - coin_inv_krw), int(pen_eval_krw - pen_inv_krw), int(total_eval_krw - total_inv_krw)],
        '수익률(%)': [
            float((us_eval_krw - us_inv_krw) / us_inv_krw) if us_inv_krw > 0 else 0.0,
            float((coin_eval_krw - coin_inv_krw) / coin_inv_krw) if coin_inv_krw > 0 else 0.0,
            float((pen_eval_krw - pen_inv_krw) / pen_inv_krw) if pen_inv_krw > 0 else 0.0,
            float((total_eval_krw - total_inv_krw) / total_inv_krw) if total_inv_krw > 0 else 0.0
        ],
        '전일대비 변동폭(₩)': [int(diff_us), int(diff_coin), int(diff_pen), int(diff_total)]
    }
    
    df_today = pd.DataFrame(today_data)
    
    # 새 데이터로 Today 탭 덮어쓰기
    _, ws_today = sheet_manager.get_sheet_data('Today')
    if ws_today:
        sheet_manager.update_sheet(ws_today, df_today)
        print("✅ Today 탭 업데이트 완료!")

    # 4. 리포트 생성 및 전송 (이제 df_today 변수가 정상적으로 들어감!)
    generate_reports(df_today, exchange_rate)
    send_telegram_message(df_today, exchange_rate)
    
    print("🚀 모든 작업이 끝났어! 깃허브에서 확인해봐.")

if __name__ == "__main__":
    main()
