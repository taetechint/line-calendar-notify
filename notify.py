"""
Calendar → LINE Notifier
Sends a LINE push message when a meeting is ~5 minutes away.
Designed to run every 5 minutes via GitHub Actions (no Mac required).
"""

import os
import requests
from icalendar import Calendar
from datetime import datetime, timezone, timedelta
import pytz

# ── Config ────────────────────────────────────────────────────────────────────
CALENDAR_URLS = [
    "https://p146-caldav.icloud.com/published/2/MjAzNDk2NTU4MTIwMzQ5Ng2tDExU75UhpLxHXl9lFRhAEixjfdAUaXX5PI4qhfURsvb8rHpJ1EIJLEBQI9GZ48YM4tsBYOhIDHIbnTZfC2A",
    "https://p23-caldav.icloud.com/published/2/MjAzNDk2NTU4MTIwMzQ5Ng2tDExU75UhpLxHXl9lFRg30AbMt2LDr9985uSi0BzVkMcJgUnR3O1VkBSTlALWioPkqIh0OFbhYj72PT9-7C8",
    "https://p146-caldav.icloud.com/published/2/MjAzNDk2NTU4MTIwMzQ5Ng2tDExU75UhpLxHXl9lFRiTDgJ4jKuk2Ha_8yfxuzSVuvH0cewfNRLcwRFcVK8HXw6Ug3YkLzB1KiH69zqB4WE",
]

LINE_TOKEN   = os.environ["LINE_TOKEN"]       # set as GitHub Secret
LINE_USER_ID = "U7494a4fbb73442776d95bad7c2b634ec"

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

# Notify if meeting starts within this window (minutes from now)
WINDOW_MIN = 3
WINDOW_MAX = 8

# ── Helpers ───────────────────────────────────────────────────────────────────

def send_line(message: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]},
        timeout=10,
    )
    resp.raise_for_status()


def fetch_events(url: str):
    """Yield VEVENT components from an iCal URL."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    cal = Calendar.from_ical(resp.text)
    for component in cal.walk():
        if component.name == "VEVENT":
            yield component


def to_aware_dt(dt):
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if hasattr(dt, "hour"):                          # is a datetime, not a date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None                                       # all-day event — skip


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now_utc     = datetime.now(timezone.utc)
    window_lo   = now_utc + timedelta(minutes=WINDOW_MIN)
    window_hi   = now_utc + timedelta(minutes=WINDOW_MAX)

    seen_uids   = set()   # deduplicate across calendars
    notified    = []

    for url in CALENDAR_URLS:
        try:
            for event in fetch_events(url):
                uid   = str(event.get("UID", ""))
                start = to_aware_dt(event.get("DTSTART").dt)

                if start is None or uid in seen_uids:
                    continue
                seen_uids.add(uid)

                if not (window_lo <= start <= window_hi):
                    continue

                summary     = str(event.get("SUMMARY",     "Untitled Event")).strip()
                location    = str(event.get("LOCATION",    "")).strip()
                description = str(event.get("DESCRIPTION", "")).strip()
                url         = str(event.get("URL",         "")).strip()

                # End time & duration
                dtend = event.get("DTEND")
                end_str      = ""
                duration_str = ""
                if dtend:
                    end_dt = to_aware_dt(dtend.dt)
                    if end_dt:
                        end_bkk      = end_dt.astimezone(BANGKOK_TZ)
                        end_str      = end_bkk.strftime("%H:%M")
                        total_mins   = int((end_dt - start).total_seconds() / 60)
                        hours, mins  = divmod(total_mins, 60)
                        if hours and mins:
                            duration_str = f"{hours}h {mins}m"
                        elif hours:
                            duration_str = f"{hours}h"
                        else:
                            duration_str = f"{mins}m"

                start_bkk = start.astimezone(BANGKOK_TZ)
                time_str  = start_bkk.strftime("%H:%M")

                # Build time line
                if end_str and duration_str:
                    time_line = f"{time_str} – {end_str}  ({duration_str})"
                else:
                    time_line = time_str

                msg = f"⏰ Meeting in 5 minutes!\n\n📅 {summary}\n🕐 {time_line}"
                if location:
                    msg += f"\n📍 {location}"
                if url:
                    msg += f"\n🔗 {url}"
                if description:
                    # Trim to 300 chars to keep message readable
                    desc_trimmed = description[:300] + ("…" if len(description) > 300 else "")
                    msg += f"\n📝 {desc_trimmed}"

                send_line(msg)
                notified.append(summary)
                print(f"[OK] Notified: {summary} at {time_str}")

        except Exception as e:
            print(f"[ERROR] {url[:60]}... — {e}")

    if not notified:
        print(f"[--] No meetings in the {WINDOW_MIN}–{WINDOW_MAX} min window. ({now_utc.strftime('%H:%M UTC')})")


if __name__ == "__main__":
    main()
