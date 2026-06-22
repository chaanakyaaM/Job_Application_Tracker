import hmac
import string
import os
import base64
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import secrets
from dotenv import load_dotenv

# Gmail API imports
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

GMAIL_SENDER = os.getenv("GMAIL_SENDER")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "..", "token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.send"]

otp_store = {
    "password": None,
    "expires_at": None
}

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError("Gmail credentials missing or expired. Re-run OAuth flow.")
    return build("gmail", "v1", credentials=creds)

def generate_otp(length=8):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def send_otp_email(otp: str):
    service = get_gmail_service()

    body = (
        f"This is a message from the server to access your job application dashboard.\n\n"
        f"Your Job Tracker OTP: {otp}\n\nExpires in 10 minutes."
    )
    msg = MIMEText(body)
    msg["Subject"] = "Job Application Dashboard OTP"
    msg["From"] = GMAIL_SENDER
    msg["To"] = GMAIL_SENDER

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print("OTP sent via Gmail API")

def create_otp():
    otp = generate_otp()
    otp_store["password"] = otp
    otp_store["expires_at"] = datetime.utcnow() + timedelta(minutes=10)
    send_otp_email(otp)
    print("OTP stored on server")

def verify_otp(user_otp: str):
    if not otp_store["password"] or not otp_store["expires_at"]:
        return False, "No OTP generated yet"
    if datetime.utcnow() > otp_store["expires_at"]:
        otp_store["password"] = None
        return False, "OTP expired, request a new one"
    if not hmac.compare_digest(user_otp, otp_store["password"]):
        return False, "Incorrect OTP"
    otp_store["password"] = None
    otp_store["expires_at"] = None
    print("OTP verified")
    return True, "Authenticated"