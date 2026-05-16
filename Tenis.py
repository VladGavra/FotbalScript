import os
import sys
import json
import base64
import requests

from datetime import datetime, timedelta
from time import sleep
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = "https://aibdnbgbsrqhefelcgtb.supabase.co"
LOGIN_URL = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"

SLOTS_URL = "https://sportinclujnapoca.ro/api/calendar/facility-time-slots"
RESERVATION_URL = "https://sportinclujnapoca.ro/api/reservations"

API_KEY = "sb_publishable_jUOeK9gZS9vffHcOslwd9Q_NV8HvFTH"

USERNAME = os.getenv("FOTBAL_USERNAME")
PASSWORD = os.getenv("FOTBAL_PASSWORD")

SPORTS_COMPLEX_ID = "211fdc7a-166e-43c8-9c5a-75094878b63a"
FACILITY_ID = "1daabab3-899f-441c-b203-5ed29eb6662e"

TARGET_HOUR = 11

MAX_RETRIES = 1000
RETRY_DELAY = 5

DEBUG = True


# =========================================================
# COOKIE REBUILD (IMPORTANT FIX)
# =========================================================

def set_auth_cookies(session, data):

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": data.get("expires_in"),
        "expires_at": data.get("expires_at"),
        "user": data["user"]
    }

    encoded = base64.b64encode(
        json.dumps(payload).encode()
    ).decode()

    cookie_name = "sb-aibdnbgbsrqhefelcgtb-auth-token"

    session.cookies.set(
        f"{cookie_name}.0",
        f"base64-{encoded}",
        domain="sportinclujnapoca.ro",
        path="/"
    )

    session.cookies.set(
        f"{cookie_name}.1",
        "",
        domain="sportinclujnapoca.ro",
        path="/"
    )

    session.cookies.set(
        "terenuriCookieConsent",
        "true",
        domain="sportinclujnapoca.ro",
        path="/"
    )


# =========================================================
# LOGIN
# =========================================================

def login(session):

    payload = {
        "email": USERNAME,
        "password": PASSWORD,
        "gotrue_meta_security": {}
    }

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "apikey": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/"
    }

    r = session.post(LOGIN_URL, headers=headers, json=payload)

    print("LOGIN:", r.status_code)

    if r.status_code != 200:
        print(r.text)
        sys.exit("Login failed")

    data = r.json()

    access_token = data["access_token"]
    user_id = data["user"]["id"]

    session.headers.update({
        "apikey": API_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "x-client-info": "supabase-ssr/0.7.0 createBrowserClient",
        "x-supabase-api-version": "2024-01-01"
    })

    # 🔥 IMPORTANT FIX
    set_auth_cookies(session, data)

    return user_id


# =========================================================
# TARGET DATE (2 WEEKS AHEAD)
# =========================================================

def get_target_date():
    return datetime.now().date() + timedelta(weeks=2)


# =========================================================
# GET SLOTS (BROWSER-ACCURATE)
# =========================================================

def get_slots(session, target_date):

    params = {
        "complexId": SPORTS_COMPLEX_ID,
        "facilityId": FACILITY_ID,
        "date": target_date.isoformat()
    }

    headers = {
        "Accept": "application/json",
        "Referer": "https://sportinclujnapoca.ro/",
        "Origin": "https://sportinclujnapoca.ro"
    }

    r = session.get(
        SLOTS_URL,
        params=params,
        headers=headers,
        timeout=30
    )

    print("\nSLOTS STATUS:", r.status_code)

    if r.status_code != 200:
        print(r.text)
        return []

    try:
        return r.json()
    except Exception as e:
        print("JSON error:", e)
        return []


# =========================================================
# FIND SLOT
# =========================================================

def find_slot(slots, target_date):

    target_prefix = f"{target_date.isoformat()} {TARGET_HOUR:02d}:00:00"

    for s in slots:
        if s.get("slot", "").startswith(target_prefix):
            if not s.get("is_Blocked"):
                print("\nFOUND SLOT:", s)
                return s

    return None


# =========================================================
# RESERVATION
# =========================================================

def reserve(session, slot, user_id):

    # 🔥 FIX timezone mismatch (CET/CEST vs UTC)
    start = datetime.fromisoformat(slot["slot"]) - timedelta(hours=2)
    end = start + timedelta(hours=1)

    payload = {
        "sportsComplexId": SPORTS_COMPLEX_ID,
        "courtId": None,
        "facilityId": FACILITY_ID,
        "startTime": start.isoformat() + ".000Z",
        "endTime": end.isoformat() + ".000Z",
        "type": "team",
        "createdBy": user_id,
        "ownerId": user_id,
        "groupId": None
    }

    r = session.post(RESERVATION_URL, json=payload)

    print("RESERVATION:", r.status_code, r.text)

    return r.status_code in (200, 201)
    print("RAW SLOT:", slot["slot"])
    print("SENDING START:", start)
    print("SENDING END:", end)
# =========================================================
# MAIN LOOP
# =========================================================

if __name__ == "__main__":

    if not USERNAME or not PASSWORD:
        sys.exit("Missing credentials")

    session = requests.Session()

    user_id = login(session)

    target_date = get_target_date()

    print("TARGET DATE:", target_date)

    for i in range(MAX_RETRIES):

        print(f"TRY {i+1}/{MAX_RETRIES}")

        slots = get_slots(session, target_date)

        slot = find_slot(slots, target_date)

        if slot:
            if reserve(session, slot, user_id):
                print("SUCCESS")
                sys.exit(0)

        sleep(RETRY_DELAY)

    print("FAILED")
