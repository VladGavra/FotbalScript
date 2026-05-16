import os
import sys
import json
import requests

from datetime import datetime, timedelta, time
from time import sleep
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = "https://aibdnbgbsrqhefelcgtb.supabase.co"

LOGIN_URL = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"

SLOTS_URL = (
    f"{SUPABASE_URL}/rest/v1/rpc/get_facility_time_slots"
)

RESERVATION_URL = (
    "https://sportinclujnapoca.ro/api/reservations"
)

API_KEY = "sb_publishable_jUOeK9gZS9vffHcOslwd9Q_NV8HvFTH"

USERNAME = os.getenv("FOTBAL_USERNAME")
PASSWORD = os.getenv("FOTBAL_PASSWORD")

# Gheorgheni Base Football
SPORTS_COMPLEX_ID = "211fdc7a-166e-43c8-9c5a-75094878b63a"
FACILITY_ID = "742f59e9-0bd9-427a-8982-9d6fc1b62b1a"

TARGET_HOUR = 12
WEEKS_AHEAD = 2

MAX_RETRIES = 60
RETRY_DELAY = 5

DEBUG = True

# =========================================================
# DEBUG
# =========================================================

def debug_session(session, title="SESSION DEBUG"):

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print("\nHEADERS:")
    for k, v in session.headers.items():

        if "authorization" in k.lower():
            print(f"{k}: {v[:60]}...")
        else:
            print(f"{k}: {v}")

    print("\nCOOKIES:")
    for c in session.cookies:
        print(f"{c.name} = {c.value}")

    print("=" * 70 + "\n")


# =========================================================
# TIME WINDOW
# =========================================================

def ensure_correct_time_window():

    now = datetime.now()

    if now.weekday() != 3:
        print("Not Thursday. Exiting.")
        sys.exit(0)

    start = time(20, 0)
    end = time(21, 30)

    if not (start <= now.time() <= end):
        print("Outside booking window.")
        sys.exit(0)

    print("Inside booking window.")


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

        # IMPORTANT:
        # loginul initial foloseste API_KEY
        "Authorization": f"Bearer {API_KEY}",

        "Origin": "https://sportinclujnapoca.ro",
        "Referer": "https://sportinclujnapoca.ro/",

        "X-Client-Info": "custom-python-script"
    }

    response = session.post(
        LOGIN_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    print("\nLOGIN STATUS:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        raise SystemExit("Login failed")

    data = response.json()

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    user_id = data["user"]["id"]

    # =====================================================
    # IMPORTANT:
    # de aici folosim USER ACCESS TOKEN
    # =====================================================

    session.headers.update({

        "apikey": API_KEY,

        "Authorization": f"Bearer {access_token}",

        "Content-Type": "application/json",

        # IMPORTANT pentru Supabase RPC
        "x-client-info": (
            "supabase-ssr/0.7.0 createBrowserClient"
        ),

        "x-supabase-api-version": "2024-01-01"
    })

    # =====================================================
    # DEBUG
    # =====================================================

    if DEBUG:

        print("\n=== LOGIN RESPONSE ===")

        print(json.dumps({
            "user_id": user_id,
            "email": data["user"]["email"],
            "access_token_first_40": access_token[:40],
            "refresh_token_first_40": refresh_token[:40],
        }, indent=2))

        print("\n=== RESPONSE HEADERS ===")

        for k, v in response.headers.items():
            print(f"{k}: {v}")

        debug_session(session, "SESSION AFTER LOGIN")

        auth_data = {

            "saved_at": datetime.utcnow().isoformat(),

            "access_token": access_token,
            "refresh_token": refresh_token,

            "expires_in": data.get("expires_in"),
            "expires_at": data.get("expires_at"),

            "token_type": data.get("token_type"),

            "user": data["user"],

            "cookies": requests.utils.dict_from_cookiejar(
                session.cookies
            ),

            "response_headers": dict(response.headers)
        }

        with open(
            "auth_debug.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(auth_data, f, indent=2)

        print("\nAuth debug saved.")

    print("\nLogin successful.")

    return user_id


# =========================================================
# TARGET DATE
# =========================================================

def get_target_date():

    today = datetime.now().date()

    target_date = today + timedelta(
        weeks=WEEKS_AHEAD
    )

    return target_date


# =========================================================
# GET SLOTS
# =========================================================

def get_slots(session, target_date):

    payload = {
        "complexID": SPORTS_COMPLEX_ID,
        "facilityID": FACILITY_ID,
        "selectedDate": target_date.isoformat()
    }

    # IMPORTANT:
    # fara headers custom aici
    # folosim session.headers
    r = session.post(
        SLOTS_URL,
        json=payload
    )

    print("\nGET SLOTS STATUS:", r.status_code)

    if r.status_code != 200:

        print("\nFAILED TO FETCH SLOTS")
        print(r.text)

        print("\n=== REQUEST HEADERS ===")
        print(r.request.headers)

        print("\n=== RESPONSE HEADERS ===")
        print(r.headers)

        return []

    try:
        return r.json()

    except Exception as e:

        print("JSON decode error:", e)

        return []


# =========================================================
# FIND SLOT
# =========================================================

def find_target_slot(slots, target_date):

    target_string = (
        f"{target_date.isoformat()}T"
        f"{TARGET_HOUR:02d}:00:00"
    )

    for slot in slots:

        if (
            slot["slot"] == target_string
            and not slot["is_Blocked"]
            and slot["courtId"]
        ):

            print("\nFOUND AVAILABLE SLOT")

            print(json.dumps(slot, indent=2))

            return slot

    return None


# =========================================================
# CREATE RESERVATION
# =========================================================

def create_reservation(session, slot, user_id):

    start_dt = datetime.fromisoformat(
        slot["slot"]
    )

    end_dt = start_dt + timedelta(hours=1)

    payload = {

        "sportsComplexId": SPORTS_COMPLEX_ID,

        "courtId": slot["courtId"],

        "facilityId": FACILITY_ID,

        "startTime": (
            start_dt.isoformat() + ".000Z"
        ),

        "endTime": (
            end_dt.isoformat() + ".000Z"
        ),

        "type": "team",

        "createdBy": user_id,

        "ownerId": user_id,

        "groupId": None
    }

    headers = {

        "Accept": (
            "application/json, text/plain, */*"
        ),

        "Content-Type": "application/json",

        "Origin": (
            "https://sportinclujnapoca.ro"
        ),

        "Referer": (
            "https://sportinclujnapoca.ro/"
            "reservations/football"
            "?preferredSportComplex="
            "gheorgheni-base"
        ),

        # IMPORTANT
        "Authorization": (
            session.headers["Authorization"]
        ),

        "apikey": API_KEY,

        # IMPORTANT
        "x-client-info": (
            "supabase-ssr/0.7.0 createBrowserClient"
        ),
    }

    # =====================================================
    # DEBUG
    # =====================================================

    if DEBUG:

        print("\n=== RESERVATION PAYLOAD ===")

        print(json.dumps(payload, indent=2))

        print("\n=== RESERVATION HEADERS ===")

        for k, v in headers.items():

            if "authorization" in k.lower():
                print(f"{k}: {v[:60]}...")
            else:
                print(f"{k}: {v}")

        debug_session(
            session,
            "SESSION BEFORE RESERVATION"
        )

    r = session.post(
        RESERVATION_URL,
        json=payload,
        headers=headers
    )

    print("\nRESERVATION STATUS:", r.status_code)

    print("\n=== RESPONSE BODY ===")
    print(r.text)

    print("\n=== RESPONSE HEADERS ===")
    print(r.headers)

    # =====================================================
    # SAVE DEBUG
    # =====================================================

    if DEBUG:

        try:

            with open(
                "reservation_response.json",
                "w",
                encoding="utf-8"
            ) as f:

                json.dump({

                    "status_code": r.status_code,

                    "request_headers": dict(
                        r.request.headers
                    ),

                    "response_headers": dict(
                        r.headers
                    ),

                    "body": r.text

                }, f, indent=2)

            print(
                "\nReservation debug saved."
            )

        except Exception as e:

            print(
                "Failed saving reservation debug:",
                e
            )

    if r.status_code not in (200, 201):

        print("\nReservation failed.")

        return False

    print("\nReservation successful!")

    return True


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    if not USERNAME or not PASSWORD:

        print("Missing credentials.")

        sys.exit(1)

    # ensure_correct_time_window()

    session = requests.Session()

    user_id = login(session)

    target_date = get_target_date()

    print(
        "\nTARGET BOOKING DATE:",
        target_date
    )

    for attempt in range(MAX_RETRIES):

        print(
            f"\nATTEMPT "
            f"{attempt + 1}/{MAX_RETRIES}"
        )

        slots = get_slots(
            session,
            target_date
        )

        slot = find_target_slot(
            slots,
            target_date
        )

        if slot:

            success = create_reservation(
                session,
                slot,
                user_id
            )

            if success:
                sys.exit(0)

        sleep(RETRY_DELAY)

    print("\nNo slot found after retries.")

    sys.exit(1)
