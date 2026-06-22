import streamlit as st

from auth_screen import otp_screen

if not otp_screen():
    st.stop()

import requests as req
import pandas as pd
import plotly.graph_objects as go
import re
import os
from dotenv import load_dotenv

load_dotenv()

def clean_date(date_str):
    if not date_str:
        return None
    # Remove trailing "(IST)", "(UTC)", "(GMT+5:30)" etc.
    return re.sub(r"\s*\([^)]*\)\s*$", "", date_str.strip())


API_URL = os.getenv('BACKEND_URL')

STATUS_ICONS = {
    "Applied": "🔵",
    "Assessment": "🟣",
    "Interview": "🟡",
    "Offer": "🟢",
    "Rejected": "🔴"
}

STATUS_OPTIONS = ["All", "Applied", "Assessment", "Interview", "Offer", "Rejected"]


def fetch(session, url):
    try:
        response = session.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


st.set_page_config(
    page_title="Job Application Tracker",
    page_icon="📧",
    layout="wide"
)

st.title("📧 Job Application Tracker")

# --------------------------------------------------
# Session State
# --------------------------------------------------

if "df" not in st.session_state:
    st.session_state.df = None

# --------------------------------------------------
# Refresh Data
# --------------------------------------------------

if st.button("🔄 Refresh Applications"):

    with st.spinner("Fetching applications..."):

        with req.Session() as session:
            data = fetch(session, API_URL)

        if not data:
            st.stop()

        applications = data.get("applications", [])

        rows = []

        for mail in applications:

            status = mail.get("status", "Unknown")

            if status == "Unknown":
                continue

            rows.append({
                "From": mail.get("from", ""),
                "Subject": mail.get("subject", ""),
                "Date": mail.get("date", ""),
                # Raw status kept around (and dropped before display)
                # so filtering/counting can match exactly -- the
                # display "Status" column has an emoji glued on, so
                # comparing against it directly never matched anything.
                "RawStatus": status,
                "Status": f"{status} {STATUS_ICONS.get(status, '')}",
                "Body": mail.get("body_preview", "")
            })

        if not rows:
            st.warning("No applications found.")
            st.stop()

        df = pd.DataFrame(rows)
        df["Date"] = df["Date"].apply(clean_date)
        df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce")
        df = df.sort_values("Date", ascending=False, na_position="last")
        df["Date"] = (
            df["Date"]
            .dt.tz_convert("Asia/Kolkata")
            .dt.strftime("%d %b %Y, %I:%M %p")
        )

        st.session_state.df = df

# --------------------------------------------------
# Display Dashboard
# --------------------------------------------------

if st.session_state.df is not None:

    df = st.session_state.df.copy()

    # ---------------- Metrics ----------------
    # Compare against RawStatus (exact match) instead of doing a
    # substring search against the emoji-suffixed "Status" column.

    applied_count = (df["RawStatus"] == "Applied").sum()
    assessment_count = (df["RawStatus"] == "Assessment").sum()
    interview_count = (df["RawStatus"] == "Interview").sum()
    offer_count = (df["RawStatus"] == "Offer").sum()
    rejection_count = (df["RawStatus"] == "Rejected").sum()

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    col1.metric("Total", len(df))
    col2.metric("Applied", applied_count)
    col3.metric("Assessment", assessment_count)
    col4.metric("Interview", interview_count)
    col5.metric("Offers", offer_count)
    col6.metric("Rejected", rejection_count)

    st.divider()

    # ---------------- Filters ----------------

    filter_col, search_col = st.columns([1, 2])

    with filter_col:
        status_filter = st.selectbox("Filter Status", STATUS_OPTIONS)

    with search_col:
        search_text = st.text_input(
            "Search",
            placeholder="Company, recruiter, subject..."
        )

    filtered_df = df.copy()

    if status_filter != "All":
        # Was comparing against "Status" (e.g. "Applied 🔵"), which
        # never equals the plain option string "Applied" -- the
        # filter was effectively dead code before.
        filtered_df = filtered_df[filtered_df["RawStatus"] == status_filter]

    if search_text:
        filtered_df = filtered_df[
            filtered_df["From"].str.contains(
                search_text,
                case=False,
                na=False
            )
            |
            filtered_df["Subject"].str.contains(
                search_text,
                case=False,
                na=False
            )
            |
            filtered_df["Body"].str.contains(
                search_text,
                case=False,
                na=False
            )
        ]

    st.subheader("Applications")

    # Hide internal columns
    table_df = filtered_df.drop(
        columns=["Body", "RawStatus"],
        errors="ignore"
    )

    event = st.dataframe(
        table_df,
        width = 'stretch',
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # ---------------- Selected Email ----------------

    if event.selection.rows:

        selected_row = event.selection.rows[0]
        selected_email = filtered_df.iloc[selected_row]

        st.divider()

        st.subheader("📨 Email Preview")

        info_col1, info_col2 = st.columns([3, 1])

        with info_col1:
            st.markdown(
                f"**Subject:** {selected_email['Subject']}"
            )
            st.markdown(
                f"**From:** {selected_email['From']}"
            )

        with info_col2:
            st.markdown(
                f"**Status:** {selected_email['Status']}"
            )

        st.markdown("### Body")

        st.text_area(
            "Email Content",
            value=selected_email["Body"],
            height=350,
            disabled=True,
            label_visibility="collapsed"
        )


    st.divider()

    # ---------------- Chart ----------------

    st.subheader("📊 Application Status Breakdown")

    chart_data = pd.DataFrame(
        {
            "Count": [
                applied_count,
                assessment_count,
                interview_count,
                offer_count,
                rejection_count
            ]
        },
        index=[
            "Applied",
            "Assessment",
            "Interview",
            "Offer",
            "Rejected"
        ]
    )


    labels = ["Applied", "Assessment", "Interview", "Offer", "Rejected"]
    values = [applied_count, assessment_count, interview_count, offer_count, rejection_count]
    colors = ["#3b82f6", "#a855f7", "#eab308", "#22c55e", "#ef4444"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        hole=0.4,                    # donut style, remove this line for a full pie
        textinfo="label+percent",
        hovertemplate="%{label}: %{value}<extra></extra>"
    )])

    fig.update_layout(
        showlegend=True,
        margin=dict(t=0, b=0, l=0, r=0),
        height=350
    )

    st.plotly_chart(fig, width="stretch")
    # ---------------- Download ----------------

    csv = filtered_df.drop(
        columns=["Body", "RawStatus"],
        errors="ignore"
    ).to_csv(index=False)

    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="applications.csv",
        mime="text/csv"
    )

else:
    st.info("Click 'Refresh Applications' to load your emails.")
