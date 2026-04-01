import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import pandas as pd

class GoogleSheetManager:
    """구글 시트 API와 통신하여 데이터를 읽고 쓰는 클래스"""
    
    def __init__(self, spreadsheet_id):
        # 구글 드라이브/시트 접근 권한 스코프 설정
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # 깃허브 시크릿에 등록된 인증키 JSON 불러오기
        creds_json = os.environ.get('GCP_CREDENTIALS')
        if not creds_json:
            raise ValueError("❌ GCP_CREDENTIALS 환경 변수가 없어!")
        
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        self.client = gspread.authorize(creds)
        self.doc = self.client.open_by_key(spreadsheet_id) # 스프레드시트 문서 열기

    def get_sheet_data(self, sheet_name):
        """특정 탭(시트명)의 데이터를 읽어와서 Pandas 데이터프레임으로 변환하는 함수"""
        try:
            worksheet = self.doc.worksheet(sheet_name)
            values = worksheet.get_all_values()
            
            if not values: # 시트가 텅 비었을 때
                return pd.DataFrame(), worksheet
                
            df = pd.DataFrame(values[1:], columns=values[0])
            # 빈 칸인 헤더는 Unnamed로 덮어씌워서 판다스 에러 방지
            df.columns = [str(col).strip() if str(col).strip() != '' else f"Unnamed_{i}" for i, col in enumerate(df.columns)]
            return df, worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️ '{sheet_name}' 탭을 찾을 수 없어.")
            return pd.DataFrame(), None

    def update_sheet(self, worksheet, df):
        """계산이 끝난 데이터프레임을 특정 시트에 통째로 덮어쓰는 함수"""
        if worksheet is None or df.empty: return
        df.fillna('', inplace=True) # NaN 값을 빈칸으로 처리
        update_data = [df.columns.tolist()] + df.values.tolist()
        worksheet.clear() # 기존 데이터 싹 날리기
        worksheet.update(values=update_data, range_name='A1') # A1셀부터 새 데이터 덮어쓰기

    def get_latest_history(self):
        """History 탭의 맨 마지막 줄(어제 데이터)을 읽어오는 함수 (전일대비 계산용)"""
        df, _ = self.get_sheet_data('History')
        if not df.empty:
            return df.iloc[-1]
        return None

    def append_to_history(self, row_data_dict):
        """History 탭 맨 밑에 오늘자 요약 데이터를 한 줄 추가하는 함수"""
        try:
            worksheet = self.doc.worksheet('History')
            # 텅 빈 시트면 맨 윗줄에 헤더명부터 적어줌
            if len(worksheet.get_all_values()) == 0:
                worksheet.append_row(list(row_data_dict.keys()))
            # 오늘 데이터 한 줄 띡 추가
            worksheet.append_row(list(row_data_dict.values()))
            print("✅ History 탭 데이터 누적 완료!")
        except Exception as e:
            print(f"⚠️ History 탭 업데이트 실패: {e}")
