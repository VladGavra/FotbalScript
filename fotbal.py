import os
import sys
from datetime import datetime, timedelta
from time import sleep
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
LOGIN_URL = "https://aibdnbgbsrqhefelcgtb.supabase.co/auth/v1/token?grant_type=password"
GET_AVAILABLE_SLOTS = "https://www.calendis.ro/api/get_available_slots?service_id={service_id}&location_id={location_id}&date={date}"
APPOINTMENT_PRE_RESERVATION_URL = "https://www.calendis.ro/api/appointment/"
APPOINTMENT_RESERVATION_URL = "https://www.calendis.ro/api/appointment/{}"

HEADERS = {"Content-Type": "application/json"}

USERNAME = "vlad.gavra@yahoo.com"#os.getenv("FOTBAL_USERNAME")
PASSWORD = "D@cianGVR1992sportcluj"#os.getenv("FOTBAL_PASSWORD")

if not USERNAME or not PASSWORD:
    print(
        "Please set the " , USERNAME, " and" , PASSWORD, " environment variables. Exiting."
    )
    sys.exit()

TIME_ZONE_OFFSET = 2
UTC_TIMESTAMP_OFFSET = 3

# Desired time slot, format YYYY-MM-DD HH:MM:SS
# If not specified, the script will search for a slot within the next two weeks at 21:00
CUSTOM_TIME_SLOT = os.getenv("CUSTOM_TIME_SLOT")

DEFAULT_HOUR_TIME_SLOT = 21
DEFAULT_DAYS_OFFSET_TIME_SLOT = 14

LOCATION_ID = 1651
SERVICE_ID = 8031

MAX_SLOT_QUERY_TIME_MINS = 110  # 110 minutes
SLOT_QUERY_TIME_DELAY_SEC = 5  # 5 seconds


def do_login():
    """
    Logs in to the API and returns a session with the client's cookie.
    """
    payload = {"email": USERNAME, "password": PASSWORD, "gotrue_meta_security": {}}

    session = requests.Session()

    response = session.post(LOGIN_URL, json=payload, headers=HEADERS)

    if response.status_code == 200 and "client_session" in session.cookies:
        print(f"Login successful for username: {USERNAME}")

        return session
    else:
        print(f"Login failed for username: {USERNAME}. Exiting.")

        sys.exit()


def get_time_slot(session, epoch_timestamp):
    """
    Queries the API for a specific time slot to check if available.
    """
    print(f"Qeuering for available slots at: {GET_AVAILABLE_SLOTS.format(
            service_id=SERVICE_ID, location_id=LOCATION_ID, date=epoch_timestamp
        )}")

    response = session.get(
        GET_AVAILABLE_SLOTS.format(
            service_id=SERVICE_ID, location_id=LOCATION_ID, date=epoch_timestamp
        ),
        headers=HEADERS,
    )

    if response.status_code == 200:
        data = response.json()

        print(f"Available slots response: {data}")

        for slot in data.get("available_slots", []):
            if slot.get("time") == epoch_timestamp:
                print(f"Slot found: {slot}")
                return slot

        print(f"Slot with timestamp {epoch_timestamp} not found.")

        return None

    else:
        print(f"Query failed with status {response.status_code}. Exiting.")

        sys.exit()


def pre_reserve_and_get_app_id(session, slot_object):
    """
    Performs a POST request with the found slot's details to get appointment id.
    """
    time_str = datetime.fromtimestamp(
        slot_object.get("time") + TIME_ZONE_OFFSET * 3600
    ).strftime("%H:%M")

    payload = {
        "appointments": [
            {
                "dateUnix": slot_object.get("time"),
                "dateUtcUnix": slot_object.get("time") - UTC_TIMESTAMP_OFFSET * 3600,
                "location_id": LOCATION_ID,
                "service_id": SERVICE_ID,
                "staff_id": slot_object.get("staff_id"),
                "startTime": time_str,
                "originalSlot": 0,
            }
        ],
        "group_id": None,
    }

    response = session.post(
        APPOINTMENT_PRE_RESERVATION_URL, json=payload, headers=HEADERS
    )

    if response.status_code == 200:
        print(f"Pre-reservation POST successful: {response.json()}")

        return response.json().get("appointment_group_id")
    else:
        print(f"Pre-reservation POST failed: {response.status_code}. Exiting.")

        sys.exit()


def confirm_reservation_by_id(session, appointment_group_id):
    """
    Performs a PUT request with the ID of the appointment to confirm it.
    """
    payload = {
        "clients": [
            {
                "own_appointment": 1,
                "dateUnix": datetime.now().timestamp(),
                "appointment_id": appointment_group_id,
            }
        ]
    }

    response = session.put(
        APPOINTMENT_RESERVATION_URL.format(appointment_group_id),
        json=payload,
        headers=HEADERS,
    )

    if response.status_code == 200:
        print(f"Appointment PUT successful. Reservation confirmed: {response.json()}")
    else:
        print(f"Appointment PUT failed with: {response.status_code}. Exiting.")

        sys.exit()


def determine_target_time_slot():
    """
    Determines the target time slot based on the CUSTOM_TIME_SLOT environment variable.
    If not specified, the default time slot is set to 'DEFAULT_HOUR_TIME_SLOT' in the next 'DEFAULT_DAYS_OFFSET_TIME_SLOT' days.
    In both cases, the time slot is adjusted based on the TIME_ZONE_OFFSET.
    """
    try:
        if CUSTOM_TIME_SLOT and len(CUSTOM_TIME_SLOT) > 0:
            print(f"Custom time slot specified: {CUSTOM_TIME_SLOT}")

            target_time = datetime.strptime(
                CUSTOM_TIME_SLOT, "%Y-%m-%d %H:%M:%S"
            ) - timedelta(hours=TIME_ZONE_OFFSET)
            target_time_epoch = int(target_time.timestamp())
        else:
            target_time = datetime.utcnow().replace(
                hour=DEFAULT_HOUR_TIME_SLOT - TIME_ZONE_OFFSET,
                minute=0,
                second=0,
                microsecond=0,
            ) + timedelta(days=DEFAULT_DAYS_OFFSET_TIME_SLOT)
            target_time_epoch = int(target_time.timestamp())

        print(f"Target time slot: {target_time}")

        return target_time_epoch
    except ValueError:
        print(
            f"Invalid time slot format for: {CUSTOM_TIME_SLOT}. Accepted format: 'YYYY-MM-DD HH:MM:SS'. Exiting"
        )

        sys.exit()


if __name__ == "__main__":
    # Step 1: Login
    session = do_login()

    # Step 2: Determine the desired time slot
    target_timeslot = determine_target_time_slot()

    # Step 3: Query API for the desired slot for a max period of time
    stop_time = datetime.now() + timedelta(minutes=MAX_SLOT_QUERY_TIME_MINS)

    while datetime.now() < stop_time:
        found_slot = get_time_slot(session, target_timeslot)
        if found_slot:
            break

        sleep(SLOT_QUERY_TIME_DELAY_SEC)

    if not found_slot:
        print(
            f"No slot found for {target_timeslot} after {MAX_SLOT_QUERY_TIME_MINS}m. Exiting."
        )
        sys.exit()

    # Step 4: Perform a pre reservation to get the appointment id
    appointment_group_id = pre_reserve_and_get_app_id(session, found_slot)

    # Step 5: Confirm the reservation with the appointment id
    confirm_reservation_by_id(session, appointment_group_id)

#only to add something so I can commit the changes
