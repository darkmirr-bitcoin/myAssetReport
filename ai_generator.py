import os
import json
import time 
from google import genai

def get_gemini_scoring_analysis(client, ticker, price, rsi, volume_ratio, obv_trend, macd_hist, ema5, bb_upper, bb_lower, news, max_retries=3):
    """제미니 API를 호출하여 기술적 지표와 뉴스를 종합 분석합니다. (최신 SDK 방식)"""
    
    # 🚨 전달받은 client가 혹시 구버전일 수 있으니, 내부에서 최신 방식으로 무조건 새로 생성
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    prompt = f"""
    당신은 월스트리트의 최고 주식 분석가입니다.
    다음 {ticker} 주식의 기술적 지표와 최신 뉴스를 바탕으로 투자 매력도(0~100점)와 분석 의견을 JSON 형태로 정확히 반환하세요.

    [기술적 지표]
    - 현재가: {price}
    - RSI: {rsi}
    - 거래량강도: {volume_ratio}%
    - OBV추세: {obv_trend}
    - MACD히스토그램: {macd_hist}
    - EMA5: {ema5}
    - 볼린저밴드: 상단 {bb_upper}, 하단 {bb_lower}

    [최신 뉴스]
    {news}

    [출력 형식 (오직 JSON만 출력할 것)]
    {{
        "score": 85,
        "newsScore": 80,
        "opinion": "AI 수요 증가와 함께 견조한 상승세 유지 중. RSI가 다소 높으나 MACD 및 OBV 추세가 긍정적임. (한국어로 작성)",
        "keywords": "AI 칩, 데이터센터, 실적 호조 (한국어로 작성)"
    }}
    """

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            
            raw_text = response.text.replace("```json", "").replace("
```", "").strip()
            result = json.loads(raw_text)
            return result
            
        except json.JSONDecodeError:
            print(f"❌ JSON 파싱 에러 ({ticker}): 제미니가 형식을 어겼습니다.")
            return {"score": 0, "newsScore": 0, "opinion": "AI 분석 형식 오류", "keywords": "-"}
            
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ API 호출 에러 ({ticker}): {e}")
                return {"score": 0, "newsScore": 0, "opinion": "AI 연동 실패", "keywords": "-"}

def get_macro_ai_summary(indices_text, yield_text, score, pc_ratio, hy_spread):
    """매크로 지표, 금리, 시장 심리를 모두 받아 Gemini AI에게 한 줄 요약을 요청하는 함수 (최신 SDK 방식)"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "💡 [AI 진단] 깃허브 시크릿에 GEMINI_API_KEY가 등록되지 않았습니다."

    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        너는 월스트리트의 수석 매크로 분석가야. 
        아래의 '주요 시장 지수', '국채 금리', 그리고 '시장 심리 지표'를 모두 종합하여 
        현재 시장 참여자들의 '심리 상태'와 '리스크 선호도(방어적인지 공격적인지)'를 딱 한 줄(50~60자 이내)로 명확하고 전문적으로 요약해줘.
        
        [1. 주요 시장 지수 흐름]
        {indices_text}
        
        [2. 국채 금리 동향]
        {yield_text}
        
        [3. 시장 심리 지표]
        - CNN 공포탐욕 지수: {score}점
        - 풋/콜 비율(P/C Ratio): {pc_ratio}
        - 하이일드 스프레드: {hy_spread}%
        
        출력 예시: "💡 금리 하락과 기술주 중심의 상승세 속에서 위험 선호 심리가 강하게 회복되는 장세입니다."
        """
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"❌ AI 매크로 요약 에러: {e}")
        return "💡 [AI 진단 실패] 시장 상태를 분석하는 데 문제가 발생했습니다."

def generate_reports(news_text, sheet_data_text, yield_text, fng_text, indices_text, us_date_str):
    """종합 리포트 생성 (최신 SDK 방식)"""
    api_key = os.environ.get("GEMINI_API_KEY")

    prompt = f"""
    [SYSTEM CRITICAL INSTRUCTION]
    당신의 유일한 기준 날짜는 오직 무조건 **{us_date_str}** 입니다. 
    제공되는 뉴스나 지표 데이터에 다른 날짜가 섞여 있더라도 전부 무시하고, 리포트의 모든 제목과 요약에는 반드시 **{us_date_str}** 하나만 사용해야 합니다.

    [데이터 1: 수집 뉴스]
    {news_text}
    [데이터 2: 종목 분석]
    {sheet_data_text}
    [데이터 3: 거시 지표]
    {indices_text} {yield_text} {fng_text}

    =========================================
    [출력 양식]

    # 📈 오늘의 미국 증시 상세 분석 리포트 ({us_date_str})
    
    ## 1. 시장 지수 및 거시 경제 분석
    (이곳에 3대 지수, VIX, 공포탐욕 지수, 국채 금리 데이터를 하나의 깔끔한 표(Table)로 정리해)
    
    **💡 거시 경제 & 시장 심리 분석 ({us_date_str} 기준):**
    (표 바로 아래에 줄글로 상세하게 설명해 줘!)

    ## 2. 주요 종목 하이라이트 (AI 점수 80점 이상)
    (이곳에 점수가 높은 순서대로 표를 작성해 줘. 열: 종목명 | 티커 | AI 점수 | 뉴스 점수 | 추세 상태 | 핵심 요약)

    ## 3. 핵심 테마 및 뉴스 분석
    (주요 테마를 마크다운 리스트 형태로 분석해)

    ---TELEGRAM_START---
    📊 **증시 및 거시 지표 요약 ({us_date_str})**
    - (핵심 수치 및 한 줄 평. 표 사용 금지)
    
    🚀 **오늘의 강세 종목 (80점 이상)**
    - (종목명(티커) / 점수 / 추세 상태 요약. 표 사용 금지)

    🌍 **핵심 거시 & 테마 요약**
    - (가장 중요한 이슈 2~3가지만 간결하게. 표 사용 금지)
    """

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        full_text = response.text.strip()
        
        if "---TELEGRAM_START---" in full_text:
            parts = full_text.split("---TELEGRAM_START---")
            return parts[0].strip(), parts[1].strip()
        return full_text, "요약본 생성 실패"
        
    except Exception as e:
        print(f"❌ AI 리포트 생성 에러: {e}")
        return "AI 리포트 생성에 실패했습니다.", "요약본 생성 실패"
