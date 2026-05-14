import pandas as pd
import os
import re

def format_macro_text(text):
    """단순 텍스트를 HTML 리스트(li) 태그로 예쁘게 감싸주는 함수 (태그 충돌 방지)"""
    if not text: return "<li>데이터 없음</li>"
    
    # 텍스트를 줄 단위로 분리
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    html_out = ""
    
    for line in lines:
        # [핵심] AI 요약처럼 이미 HTML 태그(<br>, <strong> 등)가 들어간 줄은 <li>로 감싸지 않음!
        if '<br>' in line or '<strong>' in line:
            html_out += f"<div class='ai-summary-line'>{line}</div>"
            continue
            
        # --- (이하 기존 로직 완벽 유지) ---
        if line.startswith('- '): 
            line = line[2:] # 앞의 빼기 기호 제거
            
        # 상승/하락 기호에 색상 입히기 (정규식)
        line = re.sub(r'(\+[0-9.,]+%?p?)', r'<span class="pos">\1</span>', line)
        line = re.sub(r'(-[0-9.,]+%?p?)', r'<span class="neg">\1</span>', line)
        
        html_out += f"<li>{line}</li>"
        
    return html_out

def generate_reports(df_today, exchange_rate, macro_data=None):
    """HTML 리포트와 일자별 마크다운을 생성 (매크로 데이터 포함)"""
    
    now = pd.Timestamp.now('Asia/Seoul')
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%Y-%m-%d %H:%M:%S')

    df_html = df_today.copy()
    for col in ['투자원금(₩)', '평가금액(₩)', '평가손익(₩)', '전일대비 변동폭(₩)']:
        df_html[col] = df_html[col].apply(lambda x: f"₩{int(x):,}")
    
    df_html['수익률(%)'] = df_html['수익률(%)'].apply(
        lambda x: f"<span class='pos'>+{(float(x)*100):.2f}%</span>" if x > 0 
        else f"<span class='neg'>{(float(x)*100):.2f}%</span>" if x < 0 else "0.00%"
    )

    html_table = df_html.to_html(index=False, classes='asset-table', escape=False)
    
    # 매크로 데이터 HTML 조립
    macro_html = ""
    if macro_data:
        macro_html = f"""
        <div class="macro-dashboard">
            <h3>🌍 글로벌 매크로 지표</h3>
            <div class="macro-cards">
                <div class="macro-card">
                    <h4>📈 주요 시장 지수</h4>
                    <ul>{format_macro_text(macro_data.get('indices', ''))}</ul>
                </div>
                <div class="macro-card">
                    <h4>🏦 국채 금리</h4>
                    <ul>{format_macro_text(macro_data.get('yields', ''))}</ul>
                </div>
                <div class="macro-card">
                    <h4>🧭 시장 심리</h4>
                    <ul>{format_macro_text(macro_data.get('fng', ''))}</ul>
                </div>
            </div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>일일 자산 리포트 ({date_str})</title>
        <link rel="stylesheet" href="style.css">
    </head>
    <body>
        <h2>📊 일일 자산 리포트</h2>
        <div class="summary-header">
            <p>🕒 <strong>업데이트:</strong> {time_str} (KST)</p>
            <p>💵 <strong>적용 환율:</strong> 1달러 = <strong>{exchange_rate:,.2f}원</strong></p>
        </div>
        
        <!-- 매크로 대시보드 삽입 -->
        {macro_html}

        <!-- 자산 요약 테이블 -->
        <h3 style="text-align: center; color: #2c3e50; margin-top: 40px;">💰 내 자산 현황</h3>
        {html_table}

        <div class="report-links">
            <h3>🔗 연관 시황 리포트 바로가기</h3>
            <div class="link-cards">
                <a href="https://darkmirr-bitcoin.github.io/NasdoqNewsReport/latest.html" target="_blank" class="link-card">
                    <span class="icon">📈</span><span class="text">미증시 시황 리포트</span>
                </a>
                <a href="https://darkmirr-bitcoin.github.io/CryptoReport/" target="_blank" class="link-card">
                    <span class="icon">🪙</span><span class="text">암호화폐 시황 리포트</span>
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # 마크다운은 생략 (기존 로직 유지)
    if not os.path.exists('reports'): os.makedirs('reports')
    md_content = f"# 📅 자산 기록 ({date_str})\n\n"
    df_md = df_today.copy()
    df_md['수익률(%)'] = (df_md['수익률(%)'] * 100).round(2).astype(str) + "%"
    md_content += df_md.to_markdown(index=False)
    with open(f"reports/{date_str}.md", "w", encoding="utf-8") as f: f.write(md_content)
    
    print(f"✅ 리포트 생성 완료 (index.html, reports/{date_str}.md)")
