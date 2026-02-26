import os
import sys
import base64
import json
import requests
from datetime import datetime, timedelta, time
from time import sleep
from dotenv import load_dotenv

load_dotenv()

# ==============================
# CONFIG
# ==============================

SUPABASE_URL = "https://aibdnbgbsrqhefelcgtb.supabase.co"
LOGIN_URL = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
SLOTS_URL = f"{SUPABASE_URL}/rest/v1/rpc/get_facility_time_slots"
RESERVATION_URL = "https://sportinclujnapoca.ro/api/reservations"

API_KEY = "sb_publishable_jUOeK9gZS9vffHcOslwd9Q_NV8HvFTH"

USERNAME = os.getenv("FOTBAL_USERNAME")
PASSWORD = os.getenv("FOTBAL_PASSWORD")

SPORTS_COMPLEX_ID = "211fdc7a-166e-43c8-9c5a-75094878b63a"
FACILITY_ID = "742f59e9-0bd9-427a-8982-9d6fc1b62b1a"

TARGET_HOUR = 12
WEEKS_AHEAD = 2

MAX_RETRIES = 60
RETRY_DELAY = 5


# ==============================
# LOGIN
# ==============================

def login(session):
    payload = {
        "email": USERNAME,
        "password": PASSWORD,
        "gotrue_meta_security": {}
    }

    headers = {
        "apikey": API_KEY,
        "authorization": f"Bearer {API_KEY}",
        "content-type": "application/json",
        "x-client-info": "supabase-ssr/0.7.0 createBrowserClient",
        "x-supabase-api-version": "2024-01-01"
    }

    r = session.post(LOGIN_URL, json=payload, headers=headers)

    if r.status_code != 200:
        print("Login failed:", r.text)
        sys.exit(1)

    data = r.json()

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    user_id = data["user"]["id"]

    # ✅ cookie Supabase EXACT ca browserul
    cookie_payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": data.get("expires_in", 3600),
        "user": data["user"],
    }

    encoded = base64.b64encode(
        json.dumps(cookie_payload, separators=(",", ":")).encode()
    ).decode()

    session.cookies.set(
        "sb-aibdnbgbsrqhefelcgtb-auth-token.0",
        f"base64-{encoded}",
        domain="sportinclujnapoca.ro",
    )

    # ✅ headers globale corecte
    session.headers.update({
        "apikey": API_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36"
        ),
    })

    print("Login successful.")
    print("Cookies after login:", session.cookies.get_dict())

    return user_id


# ==============================
# HELPERS
# ==============================

def get_target_date():
    today = datetime.now().date()
    return today + timedelta(weeks=WEEKS_AHEAD)


def get_slots(session, target_date):
    payload = {
        "complexID": SPORTS_COMPLEX_ID,
        "facilityID": FACILITY_ID,
        "selectedDate": target_date.isoformat()
    }

    r = session.post(SLOTS_URL, json=payload)

    if r.status_code != 200:
        print("Failed to fetch slots:", r.text)
        return []

    return r.json()


def find_target_slot(slots, target_date):
    target_string = f"{target_date.isoformat()}T{TARGET_HOUR:02d}:00:00"

    for slot in slots:
        if (
            slot["slot"] == target_string
            and not slot["is_Blocked"]
            and slot["courtId"] is not None
        ):
            print("Found available slot:", slot)
            return slot

    return None


# ==============================
# RESERVATION
# ==============================

def create_reservation(session, user_id, slot):
    start_dt = datetime.fromisoformat(slot["slot"])
    end_dt = start_dt + timedelta(hours=1)

    payload = {
        "sportsComplexId": SPORTS_COMPLEX_ID,
        "courtId": slot["courtId"],
        "facilityId": FACILITY_ID,
        "startTime": start_dt.isoformat() + ".000Z",
        "endTime": end_dt.isoformat() + ".000Z",
        "type": "team",
        "createdBy": user_id,
        "ownerId": user_id,
        "groupId": None
    }

    r = session.post(RESERVATION_URL, json=payload)

    print("Reservation status:", r.status_code)
    print(r.text)

    if r.status_code not in (200, 201):
        sys.exit(1)

    print("Reservation successful!")


# ==============================
# MAIN
# ==============================

if __name__ == "__main__":

    if not USERNAME or not PASSWORD:
        print("Missing credentials.")
        sys.exit(1)

    session = requests.Session()

    user_id = login(session)

    target_date = get_target_date()
    print("Target booking date:", target_date)

    for attempt in range(MAX_RETRIES):
        print(f"Attempt {attempt + 1}/{MAX_RETRIES}")

        slots = get_slots(session, target_date)
        slot = find_target_slot(slots, target_date)

        if slot:
            create_reservation(session, user_id, slot)
            sys.exit(0)

        sleep(RETRY_DELAY)

    print("No slot found after retries.")
    sys.exit(1)
