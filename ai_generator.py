import os
import json
import time 
from google import genai

def get_gemini_scoring_analysis(client, ticker, price, rsi, volume_ratio, obv_trend, macd_hist, ema5, bb_upper, bb_lower, news, max_retries=3):
    """제미니 API를 호출하여 기술적 지표와 뉴스를 종합 분석합니다."""
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
                model='gemini-2.5-flash', # 👈 테스트 성공한 모델로 나중에 여기만 쓱 바꾸면 돼
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
            model='gemini-2.5-flash', # 👈 여기도
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
    
    (생략...)
    """
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash', # 👈 여기도
            contents="테스트 리포트입니다. 정상 통신 여부만 확인하세요." # 실제 프롬프트 생략 (테스트용)
        )
        return "리포트 테스트", "요약 테스트"
    except Exception as e:
        print(f"❌ AI 리포트 생성 에러: {e}")
        return "AI 리포트 생성에 실패했습니다.", "요약본 생성 실패"


# =====================================================================
# 🚀 단독 실행용 통신 테스트 유틸리티 🚀
# =====================================================================
def test_gemini_models():
    """여러 Gemini 모델에 간단한 핑(Ping)을 보내 응답이 오는지 확인합니다."""
    print("==================================================")
    print("🔍 Gemini API 모델 통신 테스트를 시작합니다...")
    print("==================================================\n")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ 에러: GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다.")
        print("   실행 전 터미널에 다음을 입력하세요:")
        print("   export GEMINI_API_KEY='당신의_API_키'")
        return

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"❌ Client 초기화 실패: {e}")
        return

    # 테스트해 볼 후보 모델들
    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-pro-exp",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]

    success_models = []

    for model_name in candidate_models:
        print(f"[{model_name}] 모델 통신 시도 중...", end=" ")
        try:
            # 아주 적은 토큰만 사용하도록 단순한 질문 던지기
            response = client.models.generate_content(
                model=model_name,
                contents="Hello, this is a ping test. Please reply with only the word 'OK'."
            )
            if response.text and "OK" in response.text.upper():
                print(f"✅ 성공! (응답: {response.text.strip()})")
                success_models.append(model_name)
            else:
                print(f"⚠️ 응답은 왔으나 예상과 다름 (응답: {response.text})")
                success_models.append(model_name)
                
        except Exception as e:
            # 에러 메시지를 한 줄로 깔끔하게 정리해서 출력
            error_msg = str(e).replace('\n', ' ')
            print(f"❌ 실패! ({error_msg})")
            
        time.sleep(1) # 연속 호출로 인한 Rate Limit 방지

    print("\n==================================================")
    print("🎯 [테스트 결과 요약]")
    if success_models:
        print(f"✅ 사용 가능한 모델: {', '.join(success_models)}")
        print(f"💡 추천: 위 모델 중 하나를 복사해서 함수들의 model='...' 부분에 넣으세요.")
    else:
        print("❌ 사용 가능한 모델이 하나도 없습니다. API 키 상태나 라이브러리 버전을 확인하세요.")
    print("==================================================")

# 이 파일을 직접 실행했을 때만 테스트가 작동함
if __name__ == "__main__":
    test_gemini_models()
