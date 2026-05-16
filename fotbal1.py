import os
import sys
import json
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
FACILITY_ID = "742f59e9-0bd9-427a-8982-9d6fc1b62b1a"

TARGET_HOUR = 13

MAX_RETRIES = 1000
RETRY_DELAY = 5

DEBUG = True


# =========================================================
# LOGIN (UNCHANGED)
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
        "x-client-info": "supabase-ssr",
        "x-supabase-api-version": "2024-01-01"
    })

    print("Login OK")
    return user_id


# =========================================================
# TARGET DATE (2 weeks ahead)
# =========================================================

def get_target_date():
    return (datetime.now().date() + timedelta(weeks=2))


# =========================================================
# GET SLOTS (REAL ENDPOINT)
# =========================================================

def get_slots(session, target_date):

    url = (
        f"{SLOTS_URL}"
        f"?complexId={SPORTS_COMPLEX_ID}"
        f"&facilityId={FACILITY_ID}"
        f"&date={target_date.isoformat()}"
    )

    r = session.get(url)

    if r.status_code != 200:
        print("Slot fetch failed:", r.text)
        return []

    return r.json()


# =========================================================
# FIND SLOT (ROBUST)
# =========================================================

def find_slot(slots, target_date):

    target_prefix = f"{target_date.isoformat()} {TARGET_HOUR:02d}:00:00"

    for s in slots:

        if s["slot"].startswith(target_prefix):

            if not s["is_Blocked"]:

                print("\nFOUND SLOT:", s)
                return s

    return None


# =========================================================
# RESERVATION
# =========================================================

def reserve(session, slot, user_id):

    start = datetime.fromisoformat(slot["slot"])
    end = start + timedelta(hours=1)

    payload = {
        "sportsComplexId": SPORTS_COMPLEX_ID,
        "courtId": None,  # backend decide
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

    if r.status_code in (200, 201):
        return True

    return False


# =========================================================
# MAIN LOOP (FAST POLLING)
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

            ok = reserve(session, slot, user_id)

            if ok:
                print("SUCCESS")
                sys.exit(0)

        sleep(RETRY_DELAY)

    print("FAILED after retries")
