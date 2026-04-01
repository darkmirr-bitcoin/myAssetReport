import pandas as pd
import os

def generate_reports(df_today, exchange_rate):
    """HTML 리포트(index.html)와 일자별 마크다운(reports/날짜.md)을 생성"""
    
    now = pd.Timestamp.now('Asia/Seoul')
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # --- 1. 데이터 포맷팅 ---
    df_fmt = df_today.copy()
    for col in ['투자원금(₩)', '평가금액(₩)', '평가손익(₩)', '전일대비 변동폭(₩)']:
        df_fmt[col] = df_fmt[col].apply(lambda x: f"₩{int(x):,}")
    
    df_fmt['수익률(%)'] = df_fmt['수익률(%)'].apply(
        lambda x: f"<span style='color:red;'>+{(float(x)*100):.2f}%</span>" if x > 0 
        else f"<span style='color:blue;'>{(float(x)*100):.2f}%</span>" if x < 0 else "0.00%"
    )

    # --- 2. index.html 생성 (당일 요약용) ---
    html_style = "<style>body{font-family:sans-serif;padding:20px;} table{border-collapse:collapse;width:100%;} th,td{border:1px solid #ddd;padding:10px;text-align:right;} th{background:#4CAF50;color:white;text-align:center;}</style>"
    html_content = f"""
    <html><head><meta charset="UTF-8">{html_style}</head>
    <body>
        <h2>📊 당일 자산 요약 ({date_str})</h2>
        <p>업데이트: {time_str} | 환율: {exchange_rate:,.2f}원</p>
        {df_fmt.to_html(index=False, escape=False)}
    </body></html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # --- 3. 일자별 마크다운 생성 (기록 저장용) ---
    # reports 폴더가 없으면 생성
    if not os.path.exists('reports'):
        os.makedirs('reports')
    
    md_content = f"# 📅 자산 기록 ({date_str})\n\n"
    md_content += f"- **업데이트 시간:** {time_str}\n"
    md_content += f"- **적용 환율:** 1달러 = {exchange_rate:,.2f}원\n\n"
    md_content += "### 💰 자산 요약\n\n"
    
    # 마크다운 표 생성 (HTML 태그 제거 버전)
    df_md = df_today.copy()
    df_md['수익률(%)'] = (df_md['수익률(%)'] * 100).round(2).astype(str) + "%"
    md_content += df_md.to_markdown(index=False)
    
    with open(f"reports/{date_str}.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print(f"✅ 리포트 생성 완료 (index.html, reports/{date_str}.md)")
