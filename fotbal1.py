import os
import sys
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
APP_TOKEN_URL = "https://sportinclujnapoca.ro/api/auth/session"

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
# TIME WINDOW
# ==============================

def ensure_correct_time_window():
    now = datetime.now()

    if now.weekday() != 3:
        print("Not Thursday. Exiting.")
        sys.exit(0)

    if not (time(20, 0) <= now.time() <= time(21, 30)):
        print("Outside booking window. Exiting.")
        sys.exit(0)

    print("Inside booking window.")


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
    r.raise_for_status()

    data = r.json()

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    user_id = data["user"]["id"]

    # 🔥 CRITIC — setăm cookie exact ca browserul
    cookie_value = f'base64-{{"access_token":"{access_token}","refresh_token":"{refresh_token}"}}'

    session.cookies.set(
        "sb-aibdnbgbsrqhefelcgtb-auth-token.0",
        cookie_value,
        domain="sportinclujnapoca.ro",
    )

    print("Login OK")
    return user_id, access_token


# ==============================
# GET APP TOKEN (FULL AUTO)
# ==============================

def get_app_token(session, access_token):
    """
    Forțează backendul să emită tokenul scurt.
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/",
        "Accept": "application/json, text/plain, */*",
    }

    r = session.get(APP_TOKEN_URL, headers=headers)

    if r.status_code != 200:
        print("WARNING: could not fetch app token, using fallback")
        print(r.text)
        return None

    data = r.json()

    # ⚠️ posibilă structură
    return data.get("accessToken") or data.get("token")


# ==============================
# SLOT LOGIC
# ==============================

def get_target_date():
    return datetime.now().date() + timedelta(weeks=WEEKS_AHEAD)


def get_slots(session, target_date):
    payload = {
        "complexID": SPORTS_COMPLEX_ID,
        "facilityID": FACILITY_ID,
        "selectedDate": target_date.isoformat()
    }

    r = session.post(SLOTS_URL, json=payload)
    r.raise_for_status()
    return r.json()


def find_target_slot(slots, target_date):
    target_string = f"{target_date.isoformat()}T{TARGET_HOUR:02d}:00:00"

    for slot in slots:
        if (
            slot["slot"] == target_string
            and not slot["is_Blocked"]
            and slot["courtId"] is not None
        ):
            return slot

    return None


# ==============================
# RESERVATION
# ==============================

def create_reservation(session, user_id, slot, app_token):
    start_dt = datetime.fromisoformat(slot["slot"])
    end_dt = start_dt + timedelta(hours=1)

    payload = {
        "sportsComplexId": SPORTS_COMPLEX_ID,
        "courtId": None,
        "facilityId": FACILITY_ID,
        "startTime": start_dt.isoformat() + ".000Z",
        "endTime": end_dt.isoformat() + ".000Z",
        "type": "team",
        "createdBy": user_id,
        "ownerId": user_id,
        "groupId": None
    }

    headers = {
        "Authorization": f"Bearer {app_token}",
        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/reservations/football",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }

    r = session.post(RESERVATION_URL, json=payload, headers=headers)

    print("Reservation status:", r.status_code)
    print(r.text)

    r.raise_for_status()


# ==============================
# MAIN
# ==============================

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Missing credentials.")
        sys.exit(1)

#    ensure_correct_time_window()

    session = requests.Session()

    user_id, access_token = login(session)

    app_token = get_app_token(session, access_token)
    print("App token:", app_token)

    if not app_token:
        print("FAILED to obtain app token")
        sys.exit(1)

    target_date = get_target_date()

    for attempt in range(MAX_RETRIES):
        print(f"Attempt {attempt + 1}")

        slots = get_slots(session, target_date)
        slot = find_target_slot(slots, target_date)

        if slot:
            create_reservation(session, user_id, slot, app_token)
            sys.exit(0)

        sleep(RETRY_DELAY)

    print("No slot found.")
    sys.exit(1)

