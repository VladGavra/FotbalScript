import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta

SPORTS_COMPLEX_ID = "211fdc7a-166e-43c8-9c5a-75094878b63a"
FACILITY_ID = "742f59e9-0bd9-427a-8982-9d6fc1b62b1a"

TARGET_HOUR = 14
WEEKS_AHEAD = 2


def get_target_date():
    today = datetime.now().date()
    return today + timedelta(weeks=WEEKS_AHEAD)


async def run():
    target_date = get_target_date()
    target_slot = f"{target_date.isoformat()}T{TARGET_HOUR:02d}:00:00"

    async with async_playwright() as p:

        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        page = await context.new_page()

        print("Opening site...")

        await page.goto("https://sportinclujnapoca.ro")

        print("👉 LOGIN MANUAL (one time)")

        # 🔴 IMPORTANT:
        # aici te loghezi manual prima dată
        await page.wait_for_timeout(30000)

        print("Login done, starting watcher...")

        async def handle_response(response):
            if "get_facility_time_slots" in response.url:
                try:
                    data = await response.json()

                    if not data.get("ok"):
                        return

                    for slot in data.get("data", []):

                        if (
                            slot["slot"] == target_slot
                            and not slot.get("is_Blocked")
                            and slot.get("courtId")
                        ):
                            print("🔥 SLOT FOUND:", slot)

                            await book_slot(page, slot)
                            return

                except:
                    pass

        async def book_slot(page, slot):

            start = slot["slot"]
            end = (datetime.fromisoformat(start) + timedelta(hours=1)).isoformat()

            payload = {
                "sportsComplexId": SPORTS_COMPLEX_ID,
                "courtId": slot["courtId"],
                "facilityId": FACILITY_ID,
                "startTime": start + ".000Z",
                "endTime": end + ".000Z",
                "type": "team",
                "createdBy": slot.get("userId"),
                "ownerId": slot.get("userId"),
                "groupId": None
            }

            print("🚀 Sending reservation...")

            res = await page.request.post(
                "https://sportinclujnapoca.ro/api/reservations",
                data=payload
            )

            print("STATUS:", res.status())
            print(await res.text())

        page.on("response", lambda r: asyncio.create_task(handle_response(r)))

        # 🔁 ultra-low polling alternative: just keep browser alive
        while True:
            await page.reload()
            await page.wait_for_timeout(800)  # sub-second refresh

asyncio.run(run())
