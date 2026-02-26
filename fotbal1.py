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
APP_TOKEN_URL = "https://sportinclujnapoca.ro/api/auth/session"

API_KEY = "sb_publishable_jUOeK9gZS9vffHcOslwd9Q_NV8HvFTH"

USERNAME = os.getenv("FOTBAL_USERNAME")
PASSWORD = os.getenv("FOTBAL_PASSWORD")

SPORTS_COMPLEX_ID = "211fdc7a-166e-43c8-9c5a-75094878b63a"
FACILITY_ID = "742f59e9-0bd9-427a-8982-9d6fc1b62b1a"

TARGET_HOUR = 12
WEEKS_AHEAD = 2
MAX_RETRIES = 60
RETRY_DELAY = 5  # secunde între încercări

# ==============================
# UTILS
# ==============================

def ensure_correct_time_window():
    now = datetime.now()
    if now.weekday() != 3:
        print("Not Thursday. Exiting.")
        sys.exit(0)
    if not (time(20,0) <= now.time() <= time(21,30)):
        print("Outside allowed booking window (20:00–21:30). Exiting.")
        sys.exit(0)
    print("Inside booking window. Continuing...")


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

    # 🔥 cookie Supabase
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
    # 🔥 headers globale
    session.headers.update({
        "apikey": API_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    })

    print("[+] Login successful.")
    return user_id
    print(session.cookies.get_dict())


def get_app_token(session):
    r = session.post(APP_TOKEN_URL, headers={
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/",
    })
    if r.status_code != 200:
        print("[-] Failed to get app token:", r.status_code, r.text)
        return None
    data = r.json()
    token = data.get("accessToken") or data.get("token")
    if token:
        print("[+] App token obtained.")
    return token


def get_target_date():
    return datetime.now().date() + timedelta(weeks=WEEKS_AHEAD)


def get_slots(session, target_date):
    payload = {
        "complexID": SPORTS_COMPLEX_ID,
        "facilityID": FACILITY_ID,
        "selectedDate": target_date.isoformat()
    }
    r = session.post(SLOTS_URL, json=payload)
    if r.status_code != 200:
        print(f"[-] Failed to fetch slots ({r.status_code}):", r.text)
        return []
    return r.json()


def find_target_slot(slots, target_date):
    target_string = f"{target_date.isoformat()}T{TARGET_HOUR:02d}:00:00"
    for slot in slots:
        if slot["slot"] == target_string and not slot["is_Blocked"] and slot["courtId"]:
            print("[+] Found available slot:", slot)
            return slot
    return None


def create_reservation(session, user_id, slot, app_token):
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

    headers = {
        "Authorization": f"Bearer {app_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/reservations/football?preferredSportComplex=gheorgheni-base",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
    }

    r = session.post(RESERVATION_URL, json=payload, headers=headers)
    print("Reservation status:", r.status_code)
    print(r.text)
    return r.status_code in (200, 201)


# ==============================
# MAIN
# ==============================

if __name__ == "__main__":

    if not USERNAME or not PASSWORD:
        print("Missing credentials. Exiting.")
        sys.exit(1)

    # ensure_correct_time_window()  # poți reactiva

    session = requests.Session()

    user_id = login(session)
    app_token = get_app_token(session)
    if not app_token:
        print("[-] Could not obtain app token. Exiting.")
        sys.exit(1)

    target_date = get_target_date()
    print("Target booking date:", target_date)

    for attempt in range(MAX_RETRIES):
        print(f"\nAttempt {attempt + 1}/{MAX_RETRIES}")
        slots = get_slots(session, target_date)
        if not slots:
            print("No slots fetched. Retrying...")
            sleep(RETRY_DELAY)
            continue

        slot = find_target_slot(slots, target_date)
        if slot:
            success = create_reservation(session, user_id, slot, app_token)
            if success:
                print("[+] Reservation completed successfully!")
                sys.exit(0)
            else:
                print("[-] Reservation failed. Retrying...")

        else:
            print("No target slot available yet.")

        sleep(RETRY_DELAY)

    print("[-] No slot found after maximum retries.")
    sys.exit(1)

