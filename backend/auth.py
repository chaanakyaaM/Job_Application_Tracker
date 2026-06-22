import hmac
import smtplib
import string
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import secrets
from dotenv import load_dotenv

load_dotenv()

GMAIL_SENDER = os.getenv("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# In-memory OTP store
otp_store = {
    "password": 0,
    "expires_at": 0
}

def generate_otp(length=8):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def send_otp_email(otp: str):
    msg = MIMEText(f"This is a message from the server to access your job application dashboard.\n\nYour Job Tracker OTP: {otp}\n\nExpires in 10 minutes.")
    msg["Subject"] = "Job Application Dashboard OTP"
    msg["From"] = GMAIL_SENDER
    msg["To"] = GMAIL_SENDER

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)

def create_otp():
    otp = generate_otp()
    otp_store["password"] = otp
    otp_store["expires_at"] = datetime.utcnow() + timedelta(minutes=10)
    send_otp_email(otp)

def verify_otp(user_otp: str):
    if not otp_store["password"] or not otp_store["expires_at"]:
        return False, "No OTP generated yet"

    if datetime.utcnow() > otp_store["expires_at"]:
        otp_store["password"] = None
        return False, "OTP expired, request a new one"

    if not hmac.compare_digest(user_otp, otp_store["password"]):
        return False, "Incorrect OTP"

    # clear after use — one time only
    otp_store["password"] = None
    otp_store["expires_at"] = None
    return True, "Authenticated"
