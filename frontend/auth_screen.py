import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("BACKEND_URL")

def otp_screen():
    if st.session_state.get("authenticated"):
        return True

    st.title("🔒 Job Tracker")
    st.caption("A one-time password will be sent to your Gmail")

    if st.button("📩 Send OTP to my Gmail"):
        with st.spinner("Sending..."):
            res = requests.post(f"{API_URL}/auth/request-otp")
            if res.ok:
                st.success("OTP sent! Check your Gmail.")
                st.session_state.otp_requested = True
            else:
                st.error(f"Failed: {res.json().get('detail', 'Unknown error')}")

    if st.session_state.get("otp_requested"):
        otp = st.text_input("Enter OTP", max_chars=8, placeholder="e.g. aB3xKm9Z")

        if st.button("✅ Submit"):
            res = requests.post(f"{API_URL}/auth/verify-otp", json={"otp": otp})

            if res.ok:
                st.session_state.authenticated = True
                st.session_state.otp_requested = False
                st.rerun()
            else:
                st.error(res.json().get("detail", "Wrong OTP"))

    return False
