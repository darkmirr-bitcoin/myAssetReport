import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import pandas as pd

class GoogleSheetManager:
    """구글 시트 API와 통신하여 데이터를 읽고 쓰는 클래스"""
    
    def __init__(self, spreadsheet_id):
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_json = os.environ.get('GCP_CREDENTIALS')
        if not creds_json:
            raise ValueError("❌ GCP_CREDENTIALS 환경 변수가 없어!")
        
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        self.client = gspread.authorize(creds)
        self.doc = self.client.open_by_key(spreadsheet_id)

    def get_sheet_data(self, sheet_name):
        """특정 탭의 데이터를 읽어와서 데이터프레임으로 변환"""
        try:
            worksheet = self.doc.worksheet(sheet_name)
            values = worksheet.get_all_values()
            if not values: return pd.DataFrame(), worksheet
            df = pd.DataFrame(values[1:], columns=values[0])
            df.columns = [str(col).strip() if str(col).strip() != '' else f"Unnamed_{i}" for i, col in enumerate(df.columns)]
            return df, worksheet
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame(), None

    def update_sheet(self, worksheet, df):
        """데이터프레임을 특정 시트에 덮어쓰기"""
        if worksheet is None or df.empty: return
        df.fillna('', inplace=True)
        update_data = [df.columns.tolist()] + df.values.tolist()
        worksheet.clear()
        worksheet.update(values=update_data, range_name='A1')

    def get_latest_history_summary(self):
        """전일대비 변동폭 계산을 위해 'Today' 탭의 마지막 데이터를 읽어옴 (Today 탭 기준)"""
        df, _ = self.get_sheet_data('Today')
        if not df.empty: return df
        return None

    def append_rows_to_history(self, df_to_append):
        """History 탭 맨 밑에 여러 줄의 상세 데이터를 한꺼번에 추가"""
        try:
            worksheet = self.doc.worksheet('History')
            # 데이터프레임을 리스트 형태로 변환하여 한 번에 추가
            data_list = df_to_append.values.tolist()
            worksheet.append_rows(data_list)
            print(f"✅ History 탭에 {len(data_list)}개 종목 데이터 누적 완료!")
        except Exception as e:
            print(f"⚠️ History 탭 업데이트 실패: {e}")
