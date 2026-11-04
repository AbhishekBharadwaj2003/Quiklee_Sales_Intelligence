import os
import gspread

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()


class GoogleSheetsClient:

    def __init__(self):

        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.credentials_file = os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE"
        )

        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is missing.")

        if not self.credentials_file:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_FILE is missing."
            )

        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}"
            )

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        credentials = Credentials.from_service_account_file(
            self.credentials_file,
            scopes=scopes
        )

        self.client = gspread.authorize(credentials)

        self.spreadsheet = self.client.open_by_key(self.sheet_id)

    def get_worksheet(self, worksheet_name):

        return self.spreadsheet.worksheet(worksheet_name)

    def append_company(self, worksheet_name, company_data):

        worksheet = self.get_worksheet(worksheet_name)

        worksheet.append_row(
            company_data,
            value_input_option="USER_ENTERED"
        )

        print("Company successfully added to Google Sheets.")


if __name__ == "__main__":

    try:
        sheets = GoogleSheetsClient()
        print("Google Sheets connection successful.")

    except Exception as error:
        print("Google Sheets connection not configured:", error)