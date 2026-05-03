from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List

CAP_RIDES = 12
WINDOW_DAYS = 7


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class FareStatus:
    rides_taken: int
    rides_remaining: int
    cap_reached: bool
    window_start: datetime | None
    window_end: datetime | None
    free_rides_active: bool
    latest_ride_timestamp: datetime | None

    def to_dict(self) -> dict:
        return {
            "rides_taken": self.rides_taken,
            "rides_remaining": self.rides_remaining,
            "cap_reached": self.cap_reached,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "free_rides_active": self.free_rides_active,
            "latest_ride_timestamp": (
                self.latest_ride_timestamp.isoformat()
                if self.latest_ride_timestamp
                else None
            ),
        }


def _active_window(rides: List[datetime], now: datetime) -> tuple[list[datetime], datetime | None]:
    if not rides:
        return [], None

    rides = sorted(ensure_utc(ride) for ride in rides)
    now = ensure_utc(now)
    current_window: list[datetime] = []
    window_start: datetime | None = None

    # OMNY progress is anchored to the first ride in the current 7-day block.
    # Once a ride lands outside that block, it starts a new window instead of
    # extending the previous one as a sliding range.
    for ride in rides:
        if window_start is None:
            window_start = ride
            current_window = [ride]
            continue

        if ride < window_start + timedelta(days=WINDOW_DAYS):
            current_window.append(ride)
        else:
            window_start = ride
            current_window = [ride]

    if window_start and now >= window_start + timedelta(days=WINDOW_DAYS):
        return [], None

    return current_window, window_start


def calculate_fare_status(
    ride_timestamps: Iterable[datetime], now: datetime | None = None
) -> FareStatus:
    now = ensure_utc(now or datetime.now(timezone.utc))
    rides = [ensure_utc(timestamp) for timestamp in ride_timestamps]
    current_window, window_start = _active_window(rides, now)

    if not current_window or window_start is None:
        return FareStatus(
            rides_taken=0,
            rides_remaining=CAP_RIDES,
            cap_reached=False,
            window_start=None,
            window_end=None,
            free_rides_active=False,
            latest_ride_timestamp=None,
        )

    rides_taken = min(len(current_window), CAP_RIDES)
    rides_remaining = max(CAP_RIDES - len(current_window), 0)
    window_end = window_start + timedelta(days=WINDOW_DAYS)
    cap_reached = len(current_window) >= CAP_RIDES
    free_rides_active = cap_reached and now < window_end

    return FareStatus(
        rides_taken=rides_taken,
        rides_remaining=rides_remaining,
        cap_reached=cap_reached,
        window_start=window_start,
        window_end=window_end,
        free_rides_active=free_rides_active,
        latest_ride_timestamp=current_window[-1],
    )
