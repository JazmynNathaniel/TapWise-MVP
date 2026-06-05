from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List

CAP_RIDES = 12
WINDOW_DAYS = 7
TRANSFER_WINDOW_HOURS = 2
TRANSFER_MODES = {"bus", "subway"}


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class FareRide:
    id: int | None
    timestamp: datetime
    transit_mode: str
    transit_line: str


@dataclass(frozen=True)
class RideFareMetadata:
    id: int | None
    timestamp: datetime
    counts_toward_cap: bool
    is_transfer: bool
    transfer_source_ride_id: int | None
    transfer_expires_at: datetime | None
    transfer_target_mode: str | None

    def to_dict(self) -> dict:
        return {
            "counts_toward_cap": self.counts_toward_cap,
            "is_transfer": self.is_transfer,
            "transfer_source_ride_id": self.transfer_source_ride_id,
            "transfer_expires_at": (
                self.transfer_expires_at.isoformat()
                if self.transfer_expires_at
                else None
            ),
            "transfer_target_mode": self.transfer_target_mode,
        }


@dataclass(frozen=True)
class TransferStatus:
    available: bool
    source_ride_id: int | None = None
    source_transit_mode: str | None = None
    target_transit_mode: str | None = None
    started_at: datetime | None = None
    expires_at: datetime | None = None
    seconds_remaining: int = 0

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "source_ride_id": self.source_ride_id,
            "source_transit_mode": self.source_transit_mode,
            "target_transit_mode": self.target_transit_mode,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "seconds_remaining": self.seconds_remaining,
        }


@dataclass(frozen=True)
class FareAnalysis:
    ride_metadata: list[RideFareMetadata]
    ride_metadata_by_id: dict[int, RideFareMetadata]
    cap_ride_timestamps: list[datetime]
    active_transfer: TransferStatus


@dataclass
class FareStatus:
    rides_taken: int
    rides_remaining: int
    cap_reached: bool
    window_start: datetime | None
    window_end: datetime | None
    free_rides_active: bool
    latest_ride_timestamp: datetime | None
    transfer_rides_taken: int
    active_transfer: TransferStatus

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
            "transfer_rides_taken": self.transfer_rides_taken,
            "active_transfer": self.active_transfer.to_dict(),
        }


def _normalize_transit_mode(value: str | None) -> str:
    return (value or "").strip().lower()


def _transfer_target_mode(transit_mode: str | None) -> str | None:
    mode = _normalize_transit_mode(transit_mode)
    if mode in TRANSFER_MODES:
        return mode
    return None


def _is_valid_transfer(source: FareRide, next_ride: FareRide) -> bool:
    if source.transit_mode == "subway":
        return next_ride.transit_mode == "bus"
    if source.transit_mode == "bus":
        if next_ride.transit_mode == "subway":
            return True
        return (
            next_ride.transit_mode == "bus"
            and source.transit_line
            and next_ride.transit_line
            and source.transit_line != next_ride.transit_line
        )
    return False


def _as_fare_ride(value) -> FareRide:
    if isinstance(value, datetime):
        return FareRide(id=None, timestamp=ensure_utc(value), transit_mode="", transit_line="")

    timestamp = getattr(value, "timestamp", None)
    if not isinstance(timestamp, datetime):
        raise TypeError("Fare rides must be datetimes or objects with a timestamp.")

    ride_id = getattr(value, "id", None)
    if ride_id is not None:
        ride_id = int(ride_id)

    return FareRide(
        id=ride_id,
        timestamp=ensure_utc(timestamp),
        transit_mode=_normalize_transit_mode(getattr(value, "transit_mode", "")),
        transit_line=(getattr(value, "transit_line", "") or "").strip(),
    )


def analyze_rides(
    ride_events: Iterable[datetime | object], now: datetime | None = None
) -> FareAnalysis:
    now = ensure_utc(now or datetime.now(timezone.utc))
    rides = sorted(
        (_as_fare_ride(ride) for ride in ride_events),
        key=lambda ride: (ride.timestamp, ride.id or 0),
    )
    metadata: list[RideFareMetadata] = []
    cap_ride_timestamps: list[datetime] = []
    pending_transfer_source: FareRide | None = None
    pending_transfer_expires_at: datetime | None = None

    for ride in rides:
        transfer_is_valid = (
            pending_transfer_source is not None
            and pending_transfer_expires_at is not None
            and ride.timestamp <= pending_transfer_expires_at
            and _is_valid_transfer(pending_transfer_source, ride)
        )

        if transfer_is_valid:
            metadata.append(
                RideFareMetadata(
                    id=ride.id,
                    timestamp=ride.timestamp,
                    counts_toward_cap=False,
                    is_transfer=True,
                    transfer_source_ride_id=pending_transfer_source.id,
                    transfer_expires_at=pending_transfer_expires_at,
                    transfer_target_mode=None,
                )
            )
            pending_transfer_source = None
            pending_transfer_expires_at = None
            continue

        target_mode = _transfer_target_mode(ride.transit_mode)
        transfer_expires_at = (
            ride.timestamp + timedelta(hours=TRANSFER_WINDOW_HOURS)
            if target_mode
            else None
        )

        metadata.append(
            RideFareMetadata(
                id=ride.id,
                timestamp=ride.timestamp,
                counts_toward_cap=True,
                is_transfer=False,
                transfer_source_ride_id=None,
                transfer_expires_at=transfer_expires_at,
                transfer_target_mode=target_mode,
            )
        )
        cap_ride_timestamps.append(ride.timestamp)

        if target_mode:
            pending_transfer_source = ride
            pending_transfer_expires_at = transfer_expires_at
        else:
            pending_transfer_source = None
            pending_transfer_expires_at = None

    active_transfer = TransferStatus(available=False)
    if (
        pending_transfer_source
        and pending_transfer_expires_at
        and pending_transfer_source.timestamp <= now < pending_transfer_expires_at
    ):
        active_transfer = TransferStatus(
            available=True,
            source_ride_id=pending_transfer_source.id,
            source_transit_mode=pending_transfer_source.transit_mode,
            target_transit_mode=_transfer_target_mode(
                pending_transfer_source.transit_mode
            ),
            started_at=pending_transfer_source.timestamp,
            expires_at=pending_transfer_expires_at,
            seconds_remaining=max(
                0, int((pending_transfer_expires_at - now).total_seconds())
            ),
        )

    return FareAnalysis(
        ride_metadata=metadata,
        ride_metadata_by_id={
            item.id: item for item in metadata if item.id is not None
        },
        cap_ride_timestamps=cap_ride_timestamps,
        active_transfer=active_transfer,
    )


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
    ride_events: Iterable[datetime | object], now: datetime | None = None
) -> FareStatus:
    now = ensure_utc(now or datetime.now(timezone.utc))
    analysis = analyze_rides(ride_events, now=now)
    current_window, window_start = _active_window(analysis.cap_ride_timestamps, now)

    if not current_window or window_start is None:
        return FareStatus(
            rides_taken=0,
            rides_remaining=CAP_RIDES,
            cap_reached=False,
            window_start=None,
            window_end=None,
            free_rides_active=False,
            latest_ride_timestamp=None,
            transfer_rides_taken=0,
            active_transfer=analysis.active_transfer,
        )

    rides_taken = min(len(current_window), CAP_RIDES)
    rides_remaining = max(CAP_RIDES - len(current_window), 0)
    window_end = window_start + timedelta(days=WINDOW_DAYS)
    cap_reached = len(current_window) >= CAP_RIDES
    free_rides_active = cap_reached and now < window_end
    rides_in_window = [
        item
        for item in analysis.ride_metadata
        if window_start <= item.timestamp < window_end
    ]
    transfer_rides_taken = sum(1 for item in rides_in_window if item.is_transfer)
    latest_ride_timestamp = (
        max(item.timestamp for item in rides_in_window)
        if rides_in_window
        else current_window[-1]
    )

    return FareStatus(
        rides_taken=rides_taken,
        rides_remaining=rides_remaining,
        cap_reached=cap_reached,
        window_start=window_start,
        window_end=window_end,
        free_rides_active=free_rides_active,
        latest_ride_timestamp=latest_ride_timestamp,
        transfer_rides_taken=transfer_rides_taken,
        active_transfer=analysis.active_transfer,
    )
