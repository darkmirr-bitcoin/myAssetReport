import feedparser
import requests
import yfinance as yf

# [추가됨] 분리된 AI 제너레이터 파일에서 매크로 요약 함수 불러오기
from ai_generator import get_macro_ai_summary

def get_stock_news(ticker, limit=3):
    """yfinance를 활용해 해당 종목의 최신 영문 뉴스를 가져옵니다."""
    try:
        short_ticker = ticker.split(":")[1] if ":" in ticker else ticker
        stock = yf.Ticker(short_ticker)
        news_list = stock.news
        
        if not news_list:
            return "최신 뉴스가 없습니다."

        news_texts = []
        for article in news_list[:limit]:
            title = article.get('title', '')
            publisher = article.get('publisher', '')
            news_texts.append(f"[{publisher}] {title}")
            
        return "\n".join(news_texts)
    
    except Exception as e:
        print(f"❌ 뉴스 수집 에러 ({ticker}): {e}")
        return "뉴스 데이터를 가져오는 중 에러가 발생했습니다."


def get_news(limit=80):
    """야후 파이낸스 RSS에서 최신 글로벌 뉴스를 가져오는 함수"""
    print("글로벌 뉴스 데이터 가져오는 중...")
    rss_url = "https://finance.yahoo.com/news/rssindex"
    feed = feedparser.parse(rss_url)
    news_text = "오늘의 주요 뉴스:\n"
    for entry in feed.entries[:limit]:
        summary = entry.get('summary', entry.get('description', '요약 없음'))
        news_text += f"- {entry.title}\n  {summary}\n\n"
    return news_text

def get_treasury_yields():
    """미국 10년물, 30년물 국채 금리와 전일 대비 변동폭 및 변화율(%)을 가져오는 함수"""
    print("국채 금리 데이터(10년물, 30년물) 가져오는 중...")
    yield_text = ""
    try:
        tnx = yf.Ticker("^TNX")
        hist_10 = tnx.history(period="2d")
        if len(hist_10) >= 2:
            prev_10 = hist_10['Close'].iloc[0]
            curr_10 = hist_10['Close'].iloc[1]
            change_10 = curr_10 - prev_10
            pct_change_10 = (change_10 / prev_10) * 100
            sign_10 = "+" if change_10 > 0 else ""
            yield_text += f"- 미국 10년물 국채 금리: {curr_10:.3f}% (전일 대비 {sign_10}{change_10:.3f}%p, {sign_10}{pct_change_10:.2f}%)\n"
        elif len(hist_10) == 1:
            yield_text += f"- 미국 10년물 국채 금리: {hist_10['Close'].iloc[0]:.3f}% (전일 대비 변동폭 계산 불가)\n"

        tyx = yf.Ticker("^TYX")
        hist_30 = tyx.history(period="2d")
        if len(hist_30) >= 2:
            prev_30 = hist_30['Close'].iloc[0]
            curr_30 = hist_30['Close'].iloc[1]
            change_30 = curr_30 - prev_30
            pct_change_30 = (change_30 / prev_30) * 100
            sign_30 = "+" if change_30 > 0 else ""
            yield_text += f"- 미국 30년물 국채 금리: {curr_30:.3f}% (전일 대비 {sign_30}{change_30:.3f}%p, {sign_30}{pct_change_30:.2f}%)"
        elif len(hist_30) == 1:
            yield_text += f"- 미국 30년물 국채 금리: {hist_30['Close'].iloc[0]:.3f}% (전일 대비 변동폭 계산 불가)"

        if not yield_text:
            yield_text = "국채 금리 데이터를 불러오지 못했습니다. (데이터 없음)"
        print(f"✅ 금리 확인 완료:\n{yield_text}")
    except Exception as e:
        print(f"❌ 금리 데이터 가져오기 실패: {e}")
        yield_text = f"국채 금리 데이터를 불러오지 못했습니다. ({e})"
    return yield_text

# [핵심 업데이트] CNN 지수 3개(공포탐욕, 풋콜, 스프레드) + AI 연동!
# macro_data.py 내부의 get_fear_and_greed 함수 교체

def get_fear_and_greed(indices_text="", yield_text=""):
    """CNN 실시간 지표 3개 수집 후, 지수/금리 데이터를 합쳐 AI 요약을 추가하는 함수"""
    print("시장 심리 및 AI 요약 데이터 가져오는 중...")
    fng_text_list = []
    
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            
            score = 50
            curr_pc = 1.0
            curr_hy = 2.0
            
            # 1. 메인 공포탐욕 지수
            score = round(data['fear_and_greed']['score']) 
            rating = data['fear_and_greed']['rating']      
            prev_close = round(data['fear_and_greed']['previous_close']) 
            
            change = score - prev_close
            pct_change = (change / prev_close) * 100 if prev_close != 0 else 0 
            sign = "+" if change > 0 else ""
            
            rating_ko = {
                "extreme fear": "극도의 공포 😱", "fear": "공포 😨",
                "neutral": "중립 😐", "greed": "탐욕 😎", "extreme greed": "극도의 탐욕 🤑"
            }.get(rating.lower(), rating) 
            
            fng_text_list.append(f"- CNN 공포탐욕 지수: {score}점 ({rating_ko}) / 전일 대비 {sign}{change}점 ({sign}{pct_change:.2f}%)")

            # 2. 풋/콜 비율
            if 'put_call_options' in data and 'data' in data['put_call_options']:
                pc_data = data['put_call_options']['data']
                curr_pc = float(pc_data[-1]['y'])
                prev_pc = float(pc_data[-2]['y']) if len(pc_data) > 1 else curr_pc
                pc_change = curr_pc - prev_pc
                pc_sign = "+" if pc_change > 0 else ""
                
                pc_status = "공포 (하락 베팅)" if curr_pc > 1.0 else "탐욕 (상승 베팅)" if curr_pc < 0.8 else "중립"
                fng_text_list.append(f"- 풋/콜 비율 (P/C Ratio): {curr_pc:.2f} [{pc_status}] / 전일 대비 {pc_sign}{pc_change:.2f}")

            # 3. 하이일드 스프레드
            if 'junk_bond_demand' in data and 'data' in data['junk_bond_demand']:
                jb_data = data['junk_bond_demand']['data']
                curr_hy = float(jb_data[-1]['y'])
                prev_hy = float(jb_data[-2]['y']) if len(jb_data) > 1 else curr_hy
                hy_change = curr_hy - prev_hy
                hy_sign = "+" if hy_change > 0 else ""
                
                hy_status = "위험 회피" if curr_hy > 3.0 else "위험 선호" if curr_hy < 2.0 else "중립"
                fng_text_list.append(f"- 하이일드 스프레드: {curr_hy:.2f}% [{hy_status}] / 전일 대비 {hy_sign}{hy_change:.2f}%p")

            # 🌟 [AI 로직 연동] 지수와 금리 텍스트를 함께 던져서 결과를 받아옴!
            ai_summary = get_macro_ai_summary(indices_text, yield_text, score, curr_pc, curr_hy)
            fng_text_list.append(f"<br><strong style='color:#d35400;'>{ai_summary}</strong>")

        else:
            fng_text_list.append("- 시장 심리 지표: 데이터를 불러올 수 없습니다.")
            print(f"❌ 공포탐욕 지수 API 응답 오류 (상태 코드: {res.status_code})")
            
    except Exception as e:
        print(f"❌ 시장 심리 데이터 가져오기 실패: {e}")
        fng_text_list.append("- 시장 심리 지표: 오류 발생")

    final_text = "\n".join(fng_text_list)
    print(f"✅ 시장 심리 확인 완료:\n{final_text}")
    return final_text

def get_market_indices():
    """S&P 500, 나스닥, 러셀 2000, VIX 지수를 가져오는 함수"""
    print("주요 시장 지수 데이터 가져오는 중...")
    indices = {
        "S&P 500": {"ticker": "^GSPC", "desc": "미국 대형주 500개 전반의 흐름"},
        "나스닥 (NASDAQ)": {"ticker": "^IXIC", "desc": "기술주 및 성장주 중심의 흐름"},
        "러셀 2000 (Russell 2000)": {"ticker": "^RUT", "desc": "미국 중소형주 흐름 (경기 민감도 반영)"},
        "VIX (공포지수)": {"ticker": "^VIX", "desc": "S&P 500 옵션 기반 향후 30일 변동성 기대치"}
    }
    
    indices_text = ""
    for name, info in indices.items():
        try:
            ticker = yf.Ticker(info["ticker"])
            hist = ticker.history(period="2d")
            
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[0]
                curr_close = hist['Close'].iloc[1]
                change = curr_close - prev_close
                pct_change = (change / prev_close) * 100
                sign = "+" if change > 0 else ""
                
                indices_text += f"- {name}: {curr_close:,.2f} (전일 대비 {sign}{change:,.2f}, {sign}{pct_change:.2f}%) [{info['desc']}]\n"
            elif len(hist) == 1:
                curr_close = hist['Close'].iloc[0]
                indices_text += f"- {name}: {curr_close:,.2f} (전일 대비 계산 불가) [{info['desc']}]\n"
                
        except Exception as e:
            print(f"❌ {name} 데이터 가져오기 실패: {e}")
            indices_text += f"- {name}: 데이터를 불러오지 못했습니다.\n"
            
    print(f"✅ 시장 지수 확인 완료:\n{indices_text}")
    return indices_text
