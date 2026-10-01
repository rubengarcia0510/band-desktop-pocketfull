"""Fixture builders for `tablekeeper`.

The spec requires the harness to generate fixtures at run time with dates near the
current date, and forbids the service from assuming any particular calendar date.
Everything here is therefore built relative to today rather than hard-coded.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

ADA = {"id": "u_ada", "email": "ada@example.com",
       "password": "correct horse", "display_name": "Ada"}
BOB = {"id": "u_bob", "email": "bob@example.com",
       "password": "correct horse", "display_name": "Bob"}

# Far enough ahead that cancellation_cutoff_minutes never interferes, and close
# enough to stay "near the current date".
BOOKING_LEAD_DAYS = 7


def all_week(opens: str = "18:00", closes: str = "23:00") -> list[dict]:
    return [{"weekday": d, "opens": opens, "closes": closes} for d in WEEKDAYS]


def restaurant(rid: str = "r_anker", *, name: str = "Zum Anker",
               timezone: str = "Europe/Berlin", slot_minutes: int = 30,
               reservation_duration_minutes: int = 90,
               cancellation_cutoff_minutes: int = 120,
               opening_hours: list[dict] | None = None,
               tables: list[dict] | None = None) -> dict:
    return {
        "id": rid,
        "name": name,
        "timezone": timezone,
        "slot_minutes": slot_minutes,
        "reservation_duration_minutes": reservation_duration_minutes,
        "cancellation_cutoff_minutes": cancellation_cutoff_minutes,
        "opening_hours": all_week() if opening_hours is None else opening_hours,
        "tables": tables if tables is not None else [
            {"id": "t_1", "label": "1", "capacity": 2},
            {"id": "t_2", "label": "2", "capacity": 4},
            {"id": "t_3", "label": "3", "capacity": 6},
        ],
    }


def fixture(*, users: list[dict] | None = None,
            restaurants: list[dict] | None = None,
            reservations: list[dict] | None = None) -> dict:
    return {
        "users": [ADA, BOB] if users is None else users,
        "restaurants": [restaurant()] if restaurants is None else restaurants,
        "reservations": reservations or [],
    }


def booking_date(timezone: str = "Europe/Berlin", lead: int = BOOKING_LEAD_DAYS) -> str:
    """A local calendar date `lead` days from now at the restaurant."""
    today = dt.datetime.now(ZoneInfo(timezone)).date()
    return (today + dt.timedelta(days=lead)).isoformat()


def weekday_of(date_str: str) -> str:
    return WEEKDAYS[dt.date.fromisoformat(date_str).weekday()]


def local(date_str: str, hhmm: str = "19:00") -> str:
    """`starts_at_local` as the API takes it: YYYY-MM-DDTHH:MM, no offset."""
    return f"{date_str}T{hhmm}"


def managed_restaurant(**kwargs):
    return {**restaurant(**kwargs), 'manager_user_ids': [ADA['id']]}


def policy(date, **overrides):
    return dict(effective_from=date, slot_minutes=30, reservation_duration_minutes=90,
                cancellation_cutoff_minutes=120, opening_hours=all_week(),
                capacities={'t_1': 2, 't_2': 4, 't_3': 6}) | overrides


def expected_slots(opens: str = "18:00", closes: str = "23:00",
                   slot_minutes: int = 30, duration: int = 90) -> list[str]:
    """Every HH:MM where slot + duration <= closes, stepping from opens."""
    def mins(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    out, t, end = [], mins(opens), mins(closes)
    while t + duration <= end:
        out.append(f"{t // 60:02d}:{t % 60:02d}")
        t += slot_minutes
    return out
