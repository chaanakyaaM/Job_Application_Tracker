
import os
import re
import base64
from dotenv import load_dotenv
from backend.gmail import  get_emails
from fastapi import FastAPI, HTTPException, Query, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from backend.auth import create_otp, verify_otp
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request as GoogleAuthRequest

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


load_dotenv()

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "..", "token.json")

frontend_url = os.getenv('FRONTEND_URL')

if not frontend_url:
    raise RuntimeError("FRONTEND_URL is not set")

origins = [frontend_url]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/")
def root(request: Request, max_total: int = Query(50, ge=1, le=200)):
    try:
        return {"applications": get_emails(max_total=max_total)}
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))   # not authed yet
    except FileNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e))   # no credentials.json
    except HttpError as e:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {e}")

@app.get("/health")
def health(request: Request):
    return {"status": "ok"}

@app.post("/auth/request-otp")
@limiter.limit("3/minute")
def request_otp(request: Request):
    try:
        create_otp()
        return {"message": "OTP sent to your email"}
    except Exception as e:
        print('Error:', str(e))
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {e}")


@app.post("/auth/verify-otp")
@limiter.limit("5/minute")
def verify_otp_route(request: Request, payload: dict = Body(...)):
    user_otp = payload.get("otp", "")
    success, message = verify_otp(user_otp)

    if not success:
        raise HTTPException(status_code=401, detail=message)

    return {"authenticated": True}
