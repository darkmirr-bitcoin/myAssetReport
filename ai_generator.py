import os
import json
import time 
from google import genai

def get_gemini_scoring_analysis(client, ticker, price, rsi, volume_ratio, obv_trend, macd_hist, ema5, bb_upper, bb_lower, news, max_retries=3):
    """제미니 API를 호출하여 기술적 지표와 뉴스를 종합 분석합니다."""
    
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    prompt = f"""
    당신은 월스트리트의 최고 주식 분석가이자, 나의 개인 자산 관리자입니다.
    다음 {ticker} 자산의 기술적 지표와 뉴스를 분석하되, 반드시 **[나의 투자 룰셋]**을 엄격하게 적용하여 투자 매력도(0~100점)와 분석 의견을 JSON 형태로 반환하세요.

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

    =========================================
    🔥 [나의 투자 룰셋 (가장 최우선으로 적용할 것)] 🔥
    1. 헷징 자산 (예: VIXY): 장기 보유의 위험성을 경고하고, 단기 변동성 급등 시 무조건 `[차익 실현]`을 권고할 것.
    2. 고위험 단기 자산 (코인, 해외주식):
       - `[분할 익절]`: 현재가가 볼린저밴드 상단을 터치하거나 돌파하면, 30~50% 물량 매도를 지시할 것 (과열 구간 수익 챙기기).
       - `[전량 매도]`: 현재가가 EMA5 또는 EMA20(유추)을 하향 돌파하거나, MACD 히스토그램이 음수(데드크로스)로 꺾이면 수익/손실 상관없이 전량 손절 및 엑시트 지시할 것.
       - `[매수]`: 현재가가 볼린저밴드 하단을 강하게 이탈한 낙폭과대 상태일 때만 역발상 매수 의견을 낼 것.
    3. 장기 안전 자산 (연금/ISA ETF): 단기 기술적 지표 노이즈는 무시하고, 거시 경제가 완전히 무너지지 않는 한 묵묵히 `[홀딩]` 의견을 유지할 것.

    [출력 형식 (오직 JSON만 출력할 것)]
    {{
        "score": 85,
        "newsScore": 80,
        "opinion": "[분할 익절] 볼린저밴드 상단을 터치하며 단기 과열 구간 진입. 물량의 50%를 덜어내어 수익을 챙길 것을 권장합니다.",
        "keywords": "AI 칩, 오버슈팅, 차익실현"
    }}
    """

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            raw_text = response.text.replace("```json", "").replace("```", "").strip()
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
    """매크로 지표, 금리, 시장 심리를 모두 받아 Gemini AI에게 한 줄 요약을 요청하는 함수"""
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
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"❌ AI 매크로 요약 에러: {e}")
        return "💡 [AI 진단 실패] 시장 상태를 분석하는 데 문제가 발생했습니다."

def generate_reports(news_text, sheet_data_text, yield_text, fng_text, indices_text, us_date_str):
    """종합 리포트 생성"""
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
    (이곳에 3대 지수, VIX, 공포탐욕 지수, 국채 금리 데이터를 하나의 깔끔한 표로 정리해)
    
    **💡 거시 경제 & 시장 심리 분석 ({us_date_str} 기준):**
    (표 바로 아래에 줄글로 상세하게 설명)

    ## 2. 주요 액션 타겟 및 보유 종목 분석
    (이곳에 AI 점수와 상관없이, 나의 '투자 룰셋'에 따라 당장 조치가 필요한 종목 위주로 표를 작성해 줘. 열: 종목명 | 티커 | 액션 시그널 | 핵심 요약)

    ---TELEGRAM_START---
    📊 **시장 요약 ({us_date_str})**
    - (핵심 수치 및 매크로 한 줄 평)
    
    🚨 **오늘의 액션 플랜 (매매 시그널)**
    - (나의 투자 룰셋에 따라 당장 액션이 필요한 보유 종목을 골라 [분할 익절], [전량 매도], [매수], [차익 실현] 태그를 달아 브리핑. 만약 오늘 당장 팔거나 살 종목이 없다면 "오늘은 포지션을 유지하며 관망합니다. [홀딩]" 이라고 출력)
    - 예시: [분할 익절] NVDA - 볼린저 상단 터치. 50% 덜어냅니다.
    - 예시: [전량 매도] SUI - EMA5 하향 이탈 및 MACD 데드크로스. 손절합니다.
    - 예시: [매수] MSTR - 밴드 하단 이탈 & 시장 극도의 공포. 분할 접근 가능.
    
    🛡️ **장기 투자 (연금/ETF)**
    - (단기 노이즈는 무시하고 묵묵히 들고 가는 연금/장기 자산의 흐름을 긍정적인 [홀딩] 관점으로 짧게 요약)
    """

    try:
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
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
