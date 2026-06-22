# setup.py
from gmail import get_credentials

if __name__ == "__main__":
    print("Opening browser for Google authentication...")
    creds = get_credentials(allow_oauth_flow=True)
    print("Authentication successful. token.json saved.")
    print("You can now start the server with: uvicorn main:app --reload")
