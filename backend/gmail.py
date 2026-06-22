from bs4 import BeautifulSoup

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import re
import base64
from google.auth.transport.requests import Request as GoogleAuthRequest
import os

# Advanced Gmail search query.

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "..", "token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


GMAIL_QUERY = (
    '('
    # Stage 1: application acknowledgement ("congrats for applying" etc.)
    '"thank you for applying" OR "thank you for your application" OR '
    '"thank you for your interest" OR "thanks for applying" OR '
    '"we have received your application" OR "your application has been received" OR '
    '"application received" OR "application submitted" OR '
    '"successfully submitted your application" OR "congratulations on submitting" OR '
    '"your application to" OR "your application for" OR "application confirmation" OR '

    # Stage 2: assessments / screening tests
    '"online assessment" OR "coding challenge" OR "coding test" OR '
    '"technical assessment" OR "skills assessment" OR "take-home assignment" OR '
    'hackerrank OR codesignal OR karat OR hirevue OR pymetrics OR '

    # Stage 3: interviews
    '"interview invitation" OR "schedule your interview" OR "schedule a call" OR '
    '"phone screen" OR "technical interview" OR "onsite interview" OR '
    '"virtual interview" OR "panel interview" OR "next round" OR "next steps in your application" OR '

    # Stage 4: offers
    '"offer letter" OR "job offer" OR "pleased to offer" OR "excited to offer you" OR '
    '"extend an offer" OR "offer of employment" OR '

    # Stage 5: rejections
    '"regret to inform" OR "not moving forward" OR "will not be moving forward" OR '
    '"decided to move forward with other candidates" OR "not selected" OR '
    '"pursue other candidates" OR "position has been filled" OR '

    # Trusted ATS sending domains as a fallback signal
    'from:(greenhouse.io OR lever.co OR myworkday.com OR workday.com OR myworkdayjobs.com OR '
    'icims.com OR smartrecruiters.com OR ashbyhq.com OR jobvite.com OR successfactors.com OR '
    'taleo.net OR bamboohr.com OR breezy.hr OR recruitee.com OR workable.com OR jazzhr.com OR oraclecloud.com)'
    ') '
    'newer_than:180d '
    # '-category:promotions -category:social -category:forums -category:updates '
    '-in:spam -in:trash '
    '-("job alert" OR "jobs for you" OR "new jobs" OR "recommended jobs" OR "weekly digest" OR '
    'newsletter OR webinar OR "career fair" OR "resume review" OR "linkedin learning" OR '
    '"% off" OR "limited time" OR "flash sale" OR "exclusive deal" OR "free trial" OR '
    'giveaway OR "click here to claim" OR "act now" OR "refer a friend")'
)


# Known ATS (Applicant Tracking System) sending domains. Used as a trusted
# fallback signal -- if mail comes from one of these AND mentions a generic
# job keyword, it's treated as application-related even without a strong
# phrase match.
TRUSTED_ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "myworkday.com",
    "workday.com",
    "myworkdayjobs.com",
    "icims.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "jobvite.com",
    "successfactors.com",
    "taleo.net",
    "bamboohr.com",
    "breezy.hr",
    "recruitee.com",
    "workable.com",
    "jazzhr.com",
    "oraclecloud.com",
]

# Phrases that strongly indicate marketing, digests, or content that isn't
# about your own application -- if any of these appear, the email is
# rejected outright regardless of other keyword matches. This is the main
# anti-spam layer on the Python side (the Gmail query already filters a lot
# of this out, but mailing-list mail can still slip past category labels).
EXCLUDE_PHRASES = [
    "job alert",
    "jobs for you",
    "new jobs",
    "recommended jobs",
    "weekly digest",
    "newsletter",
    "webinar",
    "% off",
    "limited time",
    "flash sale",
    "exclusive deal",
    "free trial",
    "giveaway",
    "click here to claim",
    "act now",
    "refer a friend",
    "register now",
    "course enrollment",
    "career fair",
    "resume review",
    "linkedin learning",
    "premium subscription",
    "upgrade your plan",
    "sponsored",
    "unsubscribe from this list",
]

# Phrases tied directly to an application's lifecycle (received, screened,
# interviewed, offered, rejected). A match here is treated as a strong
# positive signal on its own. Kept in sync with the GMAIL_QUERY phrasing
# above so the Python filter doesn't reject things the query already let
# through, plus a few extra variants for recall.
STRONG_SIGNAL_PHRASES = [
    "thank you for applying",
    "thank you for your application",
    "thank you for your interest",
    "thanks for applying",
    "we have received your application",
    "your application has been received",
    "application received",
    "application submitted",
    "successfully submitted your application",
    "congratulations on submitting",
    "application confirmation",
    "online assessment",
    "coding challenge",
    "coding test",
    "technical assessment",
    "skills assessment",
    "take-home assignment",
    "interview invitation",
    "schedule your interview",
    "schedule a call",
    "phone screen",
    "technical interview",
    "onsite interview",
    "virtual interview",
    "panel interview",
    "next round",
    "next steps in your application",
    "offer letter",
    "job offer",
    "pleased to offer",
    "excited to offer you",
    "extend an offer",
    "offer of employment",
    "regret to inform",
    "not moving forward",
    "will not be moving forward",
    "decided to move forward with other candidates",
    "not selected",
    "pursue other candidates",
    "position has been filled",
]

# Phrases that are job-related most of the time but are generic enough
# to show up in unrelated contexts too -- "your application to r/X"
# (Reddit subreddit/mod applications), "your application for a loan",
# a school or club application, etc. Trusted only when paired with an
# actual job-context keyword nearby, unlike STRONG_SIGNAL_PHRASES which
# are trusted unconditionally.
WEAK_SIGNAL_PHRASES = [
    "your application to",
    "your application for",
]

JOB_CONTEXT_KEYWORDS = [
    "position",
    "role",
    "job",
    "candidate",
    "hiring",
    "recruiter",
    "career",
    "employment",
]

# Sending domains that are essentially never going to email you about
# your own job application, no matter what phrases happen to appear in
# the notification text (e.g. a Reddit "your mod application to r/X
# has been received" email). Checked before any phrase matching so a
# generic phrase match can't override an obviously-wrong sender.
EXCLUDE_SENDER_DOMAINS = [
    "reddit.com",
    "redditmail.com",
    "facebook.com",
    "facebookmail.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "pinterest.com",
    "quora.com",
    "medium.com",
    "youtube.com",
    "tiktok.com",
    "discord.com",
    "nextdoor.com",
    "meetup.com",
]

NEGATION_TRIGGERS = [
    "not", "no", "n't", "without", "never", "unable", "fails", "failed",
    "cannot", "isn't", "wasn't", "aren't", "doesn't", "don't", "didn't",
    "won't", "shall not", "does not", "do not", "did not",
]


def extract_sender_domain(sender):
    """Pull the domain out of a From header like 'Name <user@domain.com>'."""
    match = re.search(r"@([\w.-]+)", sender)
    return match.group(1).lower() if match else ""


def phrase_signal(phrase, text):
    """
    True if `phrase` appears in `text` within a sentence that doesn't
    also contain a negation word before it in that same sentence.

    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        idx = sentence.find(phrase)
        if idx == -1:
            continue
        preceding = sentence[:idx]
        if not any(neg in preceding for neg in NEGATION_TRIGGERS):
            return True
    return False


def extract_body(payload):
    """
    Extract email body from a Gmail message payload.

    """

    def find_part(parts, mime_type):
        for part in parts:
            if part.get("mimeType") == mime_type:
                return part
            nested = part.get("parts")
            if nested:
                found = find_part(nested, mime_type)
                if found:
                    return found
        return None

    parts = payload.get("parts")

    if parts:
        plain_part = find_part(parts, "text/plain")
        if plain_part:
            data = plain_part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        html_part = find_part(parts, "text/html")
        if html_part:
            data = html_part.get("body", {}).get("data")
            if data:
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

        return ""

    data = payload.get("body", {}).get("data")

    if not data:
        return ""

    decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    if payload.get("mimeType") == "text/html":
        return BeautifulSoup(decoded, "html.parser").get_text(" ", strip=True)

    return decoded


def detect_status(subject, body):
    """
    Detect application status.

    """
    text = (subject + " " + body).lower()

    rejected_phrases = [
        "unfortunately",
        "not moving forward",
        "will not be moving forward",
        "regret to inform",
        "rejected",
        "not selected",
        "pursue other candidates",
        "decided to move forward with other candidates",
        "position has been filled",
    ]
    if any(phrase_signal(phrase, text) for phrase in rejected_phrases):
        return "Rejected"

    offer_phrases = [
        "offer letter",
        "job offer",
        "pleased to offer",
        "excited to offer you",
        "extend an offer",
        "offer of employment",
    ]
    if any(phrase_signal(phrase, text) for phrase in offer_phrases):
        return "Offer"

    interview_phrases = [
        "interview invitation",
        "schedule a call",
        "schedule your interview",
        "technical round",
        "phone screen",
        "onsite",
        "panel interview",
        "next round",
        "next steps in your application",
    ]
    if any(phrase_signal(phrase, text) for phrase in interview_phrases):
        return "Interview"

    assessment_phrases = [
        "online assessment",
        "coding challenge",
        "coding test",
        "technical assessment",
        "skills assessment",
        "take-home assignment",
        "hackerrank",
        "codesignal",
        "hirevue",
    ]
    if any(phrase_signal(phrase, text) for phrase in assessment_phrases):
        return "Assessment"

    applied_phrases = [
        "thank you for applying",
        "thank you for your application",
        "thank you for your interest",
        "thanks for applying",
        "application received",
        "application submitted",
        "we have received your application",
        "your application has been received",
        "successfully submitted your application",
        "application confirmation",
    ]
    if any(phrase_signal(phrase, text) for phrase in applied_phrases):
        return "Applied"

    # Last-resort fallback: low-confidence generic single-word signals,
    # only used if nothing more specific matched anywhere above.
    if phrase_signal("offer", text):
        return "Offer"
    if phrase_signal("interview", text):
        return "Interview"
    if phrase_signal("assessment", text):
        return "Assessment"

    return "Unknown"


def is_job_email(subject, sender, body):
    """
    Determine if email is actually about one of your own applications,
    rather than just containing job-adjacent words.

    Order of checks matters:
    1. A sender-domain denylist rejects mail from platforms that never
       send real application correspondence (Reddit, social networks,
       etc.) outright, before any phrase matching even runs.
    2. Exclude phrases reject marketing/digest/newsletter mail outright,
       even if it also contains words like "job" or "interview"
       (e.g. "5 interview tips -- unsubscribe here").
    3. Strong signal phrases are specific enough to the application
       lifecycle (received, screened, interviewed, offered, rejected)
       that a single match is trusted on its own.
    4. Weak signal phrases ("your application to/for") are common
       outside job hunting too (a subreddit application, a loan
       application, a school application), so they only count when
       paired with an actual job-context keyword.
    5. Trusted ATS domains are only accepted as a fallback, and only if
       paired with at least one generic job keyword.
    """

    text = (subject + " " + body).lower()
    sender_lower = sender.lower()
    sender_domain = extract_sender_domain(sender_lower)

    if any(
        sender_domain == d or sender_domain.endswith("." + d)
        for d in EXCLUDE_SENDER_DOMAINS
    ):
        return False

    if any(phrase in text for phrase in EXCLUDE_PHRASES):
        return False

    if any(phrase_signal(phrase, text) for phrase in STRONG_SIGNAL_PHRASES):
        return True

    if any(phrase in text for phrase in WEAK_SIGNAL_PHRASES):
        if any(keyword in text for keyword in JOB_CONTEXT_KEYWORDS):
            return True

    if any(domain in sender_lower for domain in TRUSTED_ATS_DOMAINS):
        generic_keywords = [
            "application",
            "candidate",
            "position",
            "role",
            "hiring",
        ]
        if any(keyword in text for keyword in generic_keywords):
            return True

    return False


def list_all_messages(service, query, max_total=100):
    """
    Page through messages.list results instead of relying on a single
    page capped at 100 results. Requests pages sized to max_total (up
    to the API's own 100-per-page ceiling) rather than a fixed 20, so
    a larger max_total doesn't silently take 5x as many round trips.
    """

    messages = []
    page_token = None
    page_size = min(max_total, 100)

    while True:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=page_size,
                pageToken=page_token
            )
            .execute()
        )

        messages.extend(results.get("messages", []))

        page_token = results.get("nextPageToken")

        if not page_token or len(messages) >= max_total:
            break

    return messages[:max_total]

def get_credentials(allow_oauth_flow: bool = False):

    creds = None
    CREDENTIALS_PATH = os.path.join(BASE_DIR, "..", "credentials.json")

    print(f"TOKEN_PATH resolves to: {os.path.abspath(TOKEN_PATH)}")
    print(f"Token exists: {os.path.exists(TOKEN_PATH)}")

    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            print(f"Creds loaded. valid={creds.valid}, expired={creds.expired}, has_refresh={bool(creds.refresh_token)}")
        except Exception as e:
            print(f"Failed to load token: {e}")
            os.remove(TOKEN_PATH)
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            return creds
        except Exception:
            os.remove(TOKEN_PATH)
            creds = None          # ← fall through to OAuth flow below

    # No valid token — decide whether to open browser or fail cleanly
    if not allow_oauth_flow:
        raise RuntimeError(
            "No valid token.json found. Run `python setup.py` first to authenticate."
        )

    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"credentials.json not found at {os.path.abspath(CREDENTIALS_PATH)}"
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    return creds

def get_emails(max_total=100):

    creds = get_credentials()

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    messages = list_all_messages(
        service,
        GMAIL_QUERY,
        max_total=max_total
    )

    applications = []

    for msg in messages:

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=msg["id"],
                format="full"
            )
            .execute()
        )

        headers = message["payload"].get(
            "headers",
            []
        )

        subject = next(
            (
                h["value"]
                for h in headers
                if h["name"] == "Subject"
            ),
            ""
        )

        sender = next(
            (
                h["value"]
                for h in headers
                if h["name"] == "From"
            ),
            ""
        )

        date = next(
            (
                h["value"]
                for h in headers
                if h["name"] == "Date"
            ),
            ""
        )

        body = extract_body(
            message["payload"]
        )

        if not is_job_email(
            subject,
            sender,
            body
        ):
            continue

        status = detect_status(
            subject,
            body
        )

        applications.append(
            {
                "from": sender,
                "subject": subject,
                "date": date,
                "status": status,
                "body_preview": body
            }
        )

    return applications



