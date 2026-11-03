"""Google Calendar backend. Unit-tested against a mocked HTTP layer; NOT live-tested (see README)."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional
from urllib.parse import quote

import httpx

from .base import Booking, Interval

API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendar:
    def __init__(self, calendar_id: str, token_provider: Callable[[], str],
                 client: Optional[httpx.Client] = None, timezone: str = "UTC"):
        self.calendar_id = calendar_id
        self._token = token_provider
        self._client = client or httpx.Client(timeout=15)
        self.timezone = timezone

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}"}

    def busy(self, start: datetime, end: datetime) -> List[Interval]:
        body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": self.calendar_id}]}
        r = self._client.post(f"{API}/freeBusy", json=body, headers=self._headers())
        r.raise_for_status()
        cal = r.json()["calendars"][self.calendar_id]
        if cal.get("errors"):
            raise RuntimeError(f"Google Calendar freeBusy error: {cal['errors']}")
        return [(_parse(b["start"]), _parse(b["end"])) for b in cal.get("busy", [])]

    def create_event(self, booking: Booking) -> str:
        body = {
            "summary": f"{booking.name}: {booking.reason}",
            "description": f"Phone: {booking.phone}\nBooked by the voice receptionist",
            "start": {"dateTime": booking.start.isoformat(), "timeZone": self.timezone},
            "end": {"dateTime": booking.end.isoformat(), "timeZone": self.timezone},
        }
        r = self._client.post(f"{API}/calendars/{quote(self.calendar_id, safe='')}/events",
                              json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()["id"]


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def service_account_token_provider(path: str) -> Callable[[], str]:
    """Token provider from a service-account JSON key (needs `pip install google-auth`).
    Share the calendar with the service account's email so it can write events."""
    from google.oauth2 import service_account  # optional dependency
    from google.auth.transport.requests import Request

    creds = service_account.Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/calendar"])

    def token() -> str:
        if not creds.valid:
            creds.refresh(Request())
        return creds.token

    return token
