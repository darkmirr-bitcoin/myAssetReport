import os
import json
from typing import List, Dict, Any
from google import genai
from google.genai import types


def generate_ai_commentary(
    signals: List[Dict[str, Any]],
    telegram_raw: str,
    macro_summary: str,
    us_date_str: str,
) -> Dict[str, Any]:
    """확정된 시그널 리스트를 받아 텔레그램 3줄 요약과 종목별 실행 해설만 JSON으로 생성한다."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "telegram_summary": telegram_raw,
            "action_comments": {},
            "portfolio_brief": "GEMINI_API_KEY 누락으로 AI 해설 생략",
        }

    # 홀딩만 있는 경우에도 전체 맥락을 주되, 실제 액션 대상 종목을 강조
    action_targets = [s for s in signals if s["signal"] not in ("[홀딩]", "[데이터 없음]")]
    holding_tickers = [s["ticker"] for s in signals if s["signal"] == "[홀딩]"]

    prompt = f"""
    기준일: {us_date_str}
    너는 퀀트 시스템의 '해설 담당 애널리스트'다.
    매매 시그널은 이미 파이썬 룰 엔진이 확정했다. 너는 시그널을 절대 변경하거나 뒤집지 말고,
    확정된 시그널 + 수치 + 매크로 브리핑을 연결해 짧고 건조한 실행 해설만 작성하라.

    [1. 매크로 지표 요약]
    {macro_summary}

    [2. 텔레그램 마감 브리핑 원문]
    {telegram_raw}

    [3. 시스템 확정 액션 대상 종목 (JSON)]
    {json.dumps(action_targets, ensure_ascii=False, indent=2)}

    [4. 시스템 확정 홀딩 종목]
    {holding_tickers}

    아래 JSON 스키마로만 응답하라:
    {{
      "telegram_summary": "마감 브리핑 핵심 3~4줄 요약 (불릿 - 형식, 줄바꿈 \\n 포함)",
      "portfolio_brief": "오늘 포트폴리오 전반에 대한 1~2문장 총평",
      "action_comments": {{
        "티커명": "확정된 시그널과 지표 수치(EMA/BB/MACD 등)를 근거로 한 1~2문장 행동 가이드"
      }}
    }}
    """

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,  # 사실 기반의 일관된 톤 유지
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ AI 해설 생성 실패 (기계적 시그널만 단독 표시): {e}")
        return {
            "telegram_summary": telegram_raw,
            "portfolio_brief": "AI 해설 생성 중 오류가 발생해 기계적 지표 사유만 표시합니다.",
            "action_comments": {},
        }
