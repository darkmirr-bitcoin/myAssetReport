import pandas as pd
import yfinance as yf
from google_sheet import GoogleSheetManager
from indicators import fetch_history_data, calculate_indicators
from telegram_bot import send_telegram_message

def get_exchange_rate():
    try:
        # 실시간 USD/KRW 환율 가져오기
        rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
        return rate
    except:
        return 1350.0 # 실패 시 기본 환율

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    pd.options.display.float_format = '{:.2f}'.format
    
    exchange_rate = get_exchange_rate()
    print(f"현재 환율: 1달러 = {exchange_rate:.2f}원")

    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    df = sheet_manager.get_data()
    
    # 1. 숫자 데이터 전처리
    df['매수가($)'] = pd.to_numeric(df['매수가($)'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    # 2. 종목별 루프 (가격 및 지표 업데이트)
    for index, row in df.iterrows():
        ticker = str(row['티커']).strip()
        category = str(row['구분']).strip()
        
        if not ticker or ticker == 'nan': continue
            
        df_hist = fetch_history_data(category, ticker)
        ind_data = calculate_indicators(df_hist)
        
        if ind_data:
            for col, val in ind_data.items():
                if col in df.columns:
                    df.at[index, col] = val

    # 3. 수익률 및 평가금액 계산 (통화 컬럼 반영)
    df['현재가($)'] = pd.to_numeric(df['현재가($)'], errors='coerce').fillna(0)
    
    # 평가금액 및 평가손익 계산 (해당 종목의 로컬 통화 기준)
    df['평가금액($)'] = df['현재가($)'] * df['수량']
    df['평가손익($)'] = (df['현재가($)'] - df['매수가($)']) * df['수량']
    
    # 수익률(%) 계산 (같은 통화끼리의 계산이므로 환율 무관하게 정확함)
    df['수익률(%)'] = df.apply(
        lambda x: ((x['현재가($)'] - x['매수가($)']) / x['매수가($)'] * 100) if x['매수가($)'] > 0 else 0, 
        axis=1
    )

    # 4. 시트 업데이트 및 저장
    sheet_manager.update_main_sheet(df)
    sheet_manager.append_history(df)

  # === (위쪽 시트 업데이트 로직은 그대로 유지) ===
    # sheet_manager.update_main_sheet(df)
    # sheet_manager.append_history(df)
    # ===============================================

    print("4. HTML 리포트 생성 중...")
    
    # 웹페이지 출력용으로 쓸 복사본 생성
    df_html = df.copy()

    # 금액에 단위 붙여주는 함수
    def format_currency(row, col):
        val = row[col]
        if pd.isna(val) or val == '': return val
        try:
            val = float(val)
            # 통화가 USD면 소수점 둘째자리까지 달러 기호
            if str(row.get('통화', '')).strip().upper() == 'USD':
                return f"${val:,.2f}"
            # 아니면 소수점 버리고 원화 기호
            else:
                return f"₩{val:,.0f}"
        except:
            return val

    # 가격 관련 컬럼 포맷팅 적용
    price_cols = ['매수가($)', '현재가($)', '평가금액($)', '평가손익($)']
    for col in price_cols:
        if col in df_html.columns:
            df_html[col] = df_html.apply(lambda r: format_currency(r, col), axis=1)

    # 수익률 컬럼 포맷팅 (플러스는 빨간색, 마이너스는 파란색 처리)
    if '수익률(%)' in df_html.columns:
        df_html['수익률(%)'] = df_html['수익률(%)'].apply(
            lambda x: f"<span style='color:red; font-weight:bold;'>+{float(x):.2f}%</span>" if float(x) > 0 
            else f"<span style='color:blue; font-weight:bold;'>{float(x):.2f}%</span>" if float(x) < 0 
            else "0.00%"
        )

    # HTML 뼈대 만들기
    html_style = """
    <style>
        body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background-color: #f8f9fa; }
        h2 { color: #333; }
        table { border-collapse: collapse; width: 100%; background-color: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: right; font-size: 14px; }
        th { background-color: #4CAF50; color: white; text-align: center; }
        tr:nth-child(even) { background-color: #f2f2f2; }
    </style>
    """
    
    # escape=False 로 둬야 span 태그(색상)가 제대로 먹힘
    html_table = df_html.to_html(index=False, classes='asset-table', escape=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head><meta charset="UTF-8"><title>일일 자산 리포트</title>{html_style}</head>
    <body>
        <h2>📊 일일 자산 리포트</h2>
        <p>업데이트: {pd.Timestamp.now('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>적용 환율: 1달러 = {exchange_rate:,.2f}원</p>
        {html_table}
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("5. 텔레그램 알림 발송 중...")
  #  send_telegram_message(df, exchange_rate)
    
    print("🚀 모든 작업이 성공적으로 끝났어!")

if __name__ == "__main__":
    main()
