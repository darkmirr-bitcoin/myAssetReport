import pandas as pd
from google_sheet import GoogleSheetManager
from indicators import fetch_history_data, calculate_indicators
from telegram_bot import send_telegram_message

def main():
    SPREADSHEET_ID = '1tZMCE70ZKaSBbh5ls3MlrpQbzpIa278yFT4DPneva6o'
    pd.options.display.float_format = '{:.2f}'.format
    
    print("1. 구글 시트 데이터 로드 중...")
    sheet_manager = GoogleSheetManager(SPREADSHEET_ID)
    df = sheet_manager.get_data()
    
    print("2. 데이터 가공 및 보조지표 계산 중... (조금 걸릴 수 있어)")
    df['매수가($)'] = pd.to_numeric(df['매수가($)'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
    df['수량'] = pd.to_numeric(df['수량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    for index, row in df.iterrows():
        ticker = str(row['티커']).strip()
        category = str(row['구분']).strip()
        
        if not ticker or pd.isna(ticker) or ticker == '':
            continue
            
        # 1년치 히스토리 데이터 가져와서 지표 계산
        df_hist = fetch_history_data(category, ticker)
        ind_data = calculate_indicators(df_hist)
        
        if ind_data:
            # 계산된 지표들을 데이터프레임에 채워 넣기
            for col, val in ind_data.items():
                if col in df.columns: # 구글 시트에 해당 컬럼(이름)이 존재할 때만 넣기
                    df.at[index, col] = val

    # 기본 수익률 및 평가금액 계산
    df['현재가($)'] = pd.to_numeric(df['현재가($)'], errors='coerce').fillna(0)
    df['평가금액($)'] = df['현재가($)'] * df['수량']
    df['평가손익($)'] = (df['현재가($)'] - df['매수가($)']) * df['수량']
    df['수익률(%)'] = df.apply(lambda x: ((x['현재가($)'] - x['매수가($)']) / x['매수가($)'] * 100) if x['매수가($)'] > 0 else 0, axis=1)

    # 보기 좋게 소수점 반올림
    numeric_cols = ['현재가($)', '평가금액($)', '평가손익($)', '수익률(%)', 'RSI', 'EMA5', 'EMA20', 'EMA50', 'EMA100', 'BB상단', 'BB하단', 'MACD', 'OBV']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round(2)

    print("3. 구글 시트 업데이트 중...")
    sheet_manager.update_main_sheet(df)
    sheet_manager.append_history(df)

    print("4. HTML 리포트 생성 중...")
    html_style = """
    <style>
        body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background-color: #f8f9fa; }
        h2 { color: #333; }
        table { border-collapse: collapse; width: 100%; background-color: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: right; font-size: 13px; }
        th { background-color: #4CAF50; color: white; text-align: center; }
        tr:nth-child(even) { background-color: #f2f2f2; }
    </style>
    """
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head><meta charset="UTF-8"><title>일일 자산 리포트</title>{html_style}</head>
    <body>
        <h2>📊 일일 자산 리포트</h2>
        <p>업데이트: {pd.Timestamp.now('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S')}</p>
        {df.to_html(index=False, classes='asset-table')}
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("5. 텔레그램 알림 발송 중...")
    #--send_telegram_message(df)
    
    print("🚀 모든 작업이 성공적으로 끝났어!")

if __name__ == "__main__":
    main()