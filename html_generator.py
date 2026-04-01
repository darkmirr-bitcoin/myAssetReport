import pandas as pd

def generate_html_report(df_today, exchange_rate):
    """Today 요약 데이터프레임을 받아서 index.html 웹페이지로 렌더링하는 함수"""
    print("🌐 HTML 리포트 생성 중...")
    
    # 웹페이지 출력용 복사본 (원본 데이터 손상 방지)
    df_html = df_today.copy()

    # 금액 컬럼에 콤마(,)와 원화 기호(₩) 붙여주는 포맷터
    def format_krw(val):
        try:
            return f"₩{int(val):,}"
        except:
            return val

    # 금액 포맷팅 적용
    price_cols = ['투자원금(₩)', '평가금액(₩)', '평가손익(₩)', '전일대비 변동폭(₩)']
    for col in price_cols:
        if col in df_html.columns:
            df_html[col] = df_html[col].apply(format_krw)

    # 수익률 포맷팅 (플러스는 빨간색, 마이너스는 파란색 적용)
    if '수익률(%)' in df_html.columns:
        df_html['수익률(%)'] = df_html['수익률(%)'].apply(
            lambda x: f"<span style='color:red; font-weight:bold;'>+{(float(x) * 100):.2f}%</span>" if float(x) > 0 
            else f"<span style='color:blue; font-weight:bold;'>{(float(x) * 100):.2f}%</span>" if float(x) < 0 
            else "0.00%"
        )

    # HTML CSS 디자인 뼈대
    html_style = """
    <style>
        body { font-family: 'Malgun Gothic', sans-serif; padding: 20px; background-color: #f8f9fa; }
        h2 { color: #333; }
        .summary-box { background-color: #fff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        table { border-collapse: collapse; width: 100%; background-color: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: right; font-size: 15px; }
        th { background-color: #4CAF50; color: white; text-align: center; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        td:first-child { text-align: center; font-weight: bold; }
    </style>
    """
    
    # escape=False로 둬야 span 태그(수익률 색상)가 텍스트가 아닌 태그로 제대로 먹힘
    html_table = df_html.to_html(index=False, classes='asset-table', escape=False)
    
    # 최종 HTML 조합
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head><meta charset="UTF-8"><title>내 자산 자동 리포트</title>{html_style}</head>
    <body>
        <h2>📊 일일 자산 요약 리포트</h2>
        <div class="summary-box">
            <p>🕒 <strong>업데이트 시간:</strong> {pd.Timestamp.now('Asia/Seoul').strftime('%Y-%m-%d %H:%M:%S')} (KST)</p>
            <p>💵 <strong>적용 환율:</strong> 1달러 = {exchange_rate:,.2f}원</p>
        </div>
        {html_table}
    </body>
    </html>
    """
    
    # 파일 쓰기
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("✅ index.html 생성 완료! (GitHub Pages 배포 준비 끝)")
