from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import desc

from ..extensions import db
from ..models import Ride, RouteNotificationPreference
from ..services.fare_engine import calculate_fare_status
from ..services.rail_fares import estimate_rail_fare, is_rail_fare_mode
from ..services.mta_realtime import get_next_arrivals, get_service_alerts
from ..services.transit_data import (
    get_transit_options,
    is_valid_transit_selection,
    list_route_summaries,
)

transit_bp = Blueprint("transit", __name__)
BLOCKING_ALERT_EFFECTS = {"NO_SERVICE"}
BLOCKING_ALERT_KEYWORDS = (
    "no service",
    "not running",
    "suspended",
    "service suspended",
    "service is suspended",
    "line is closed",
    "station is closed",
    "temporarily closed",
)
RAIL_MODES = {"lirr", "metro_north"}
OMNY_MODES = {"subway", "bus"}
TRAVEL_TIME_MODES = {"leave_at", "arrive_by"}
SCHEDULE_BEFORE_HOURS = 2
SCHEDULE_AFTER_HOURS = 24
SCHEDULE_LIMIT = 128
RAIL_SCHEDULE_BEFORE_HOURS = 12
NY_TZ = ZoneInfo("America/New_York")
OMNY_BASE_FARE = 3.00
TRANSFER_BUFFER_MINUTES = 6
MAX_TRANSFER_CANDIDATES = 8
MAX_TRANSFER_STOPS_PER_PAIR = 2
ROUTE_PRIORITY_LABELS = {
    "fastest": "shortest time",
    "least_walking": "least walking",
    "fewest_transfers": "fewest transfers",
    "lowest_fare": "lowest fare",
    "least_crowded": "least crowded",
    "most_crowded": "most crowded",
}
ROUTE_PRIORITY_ALIASES = {
    "shortest_time": "fastest",
    "shortest_travel_time": "fastest",
    "least_transfers": "fewest_transfers",
    "lowest_price": "lowest_fare",
    "cheapest": "lowest_fare",
    "less_crowded": "least_crowded",
    "avoid_crowds": "least_crowded",
    "more_crowded": "most_crowded",
    "crowded": "most_crowded",
}
DEFAULT_ROUTE_PRIORITIES = ("fastest", "fewest_transfers")
MODE_WALKING_MINUTES = {
    "bus": 3,
    "subway": 5,
    "lirr": 7,
    "metro_north": 7,
}
MODE_CROWDING_BASE = {
    "bus": 42,
    "subway": 52,
    "lirr": 48,
    "metro_north": 48,
}


def _user_id() -> int:
    return int(get_jwt_identity())


def _preference_key(mode: str, line: str, entry_stop: str = "") -> tuple[str, str, str]:
    return (mode, line, entry_stop)


def _serialize_preference(preference: RouteNotificationPreference) -> dict:
    return {
        "id": preference.id,
        "transit_mode": preference.transit_mode,
        "transit_line": preference.transit_line,
        "entry_stop": preference.entry_stop,
        "enabled": preference.enabled,
        "created_at": preference.created_at.isoformat(),
        "updated_at": preference.updated_at.isoformat(),
    }


def _parse_timestamp(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_time_mode(raw_value: str | None) -> str:
    normalized = (raw_value or "leave_at").strip().lower()
    if normalized in TRAVEL_TIME_MODES:
        return normalized
    return "leave_at"


def _parse_route_priorities(raw_values: list[str]) -> list[str]:
    priorities: list[str] = []
    for raw_value in raw_values:
        for item in raw_value.split(","):
            normalized = item.strip().lower().replace("-", "_")
            normalized = ROUTE_PRIORITY_ALIASES.get(normalized, normalized)
            if normalized in ROUTE_PRIORITY_LABELS and normalized not in priorities:
                priorities.append(normalized)

    return priorities or list(DEFAULT_ROUTE_PRIORITIES)


def _route_stop_indexes(stops: list[str], origin: str, destination: str) -> tuple[int, int]:
    return stops.index(origin), stops.index(destination)


def _estimated_travel_minutes(mode: str, stop_count: int) -> int:
    per_stop_minutes = {
        "subway": 3,
        "bus": 5,
        "lirr": 7,
        "metro_north": 7,
    }.get(mode, 4)
    minimum_minutes = {
        "subway": 5,
        "bus": 8,
        "lirr": 12,
        "metro_north": 12,
    }.get(mode, 6)
    return max(minimum_minutes, max(1, stop_count) * per_stop_minutes)


def _estimated_leg_walking_minutes(mode: str) -> int:
    return MODE_WALKING_MINUTES.get(mode, 4)


def _omny_fare_is_free(fare_status: dict | None) -> bool:
    if not fare_status:
        return False
    active_transfer = fare_status.get("active_transfer") or {}
    return bool(active_transfer.get("available") or fare_status.get("free_rides_active"))


def _route_fare_estimate(legs: list[dict], fare_status: dict | None) -> tuple[float | None, str]:
    uses_omny = any(leg["mode"] in OMNY_MODES for leg in legs)
    rail_prices: list[float] = []
    has_unavailable_rail_price = False

    for leg in legs:
        if leg["mode"] not in RAIL_MODES:
            continue
        rail_fare = leg.get("rail_fare") or {}
        rail_price = rail_fare.get("estimated_price")
        if isinstance(rail_price, (int, float)):
            rail_prices.append(float(rail_price))
        else:
            has_unavailable_rail_price = True

    fare_total = sum(rail_prices)
    if uses_omny:
        if _omny_fare_is_free(fare_status):
            omny_label = "Current OMNY transfer or cap"
        else:
            fare_total += OMNY_BASE_FARE
            omny_label = f"OMNY ${OMNY_BASE_FARE:.2f}"
    else:
        omny_label = ""

    if has_unavailable_rail_price and not rail_prices and not uses_omny:
        return None, "Rail fare unavailable"

    if uses_omny and not rail_prices:
        return fare_total, omny_label
    if uses_omny and rail_prices:
        return fare_total, f"{omny_label} + rail"
    if rail_prices:
        return fare_total, f"Rail ${fare_total:.2f}"
    return None, "Fare unavailable"


def _rush_hour_bonus(local_value: datetime) -> int:
    if local_value.weekday() >= 5:
        return -8

    minutes = local_value.hour * 60 + local_value.minute
    if 7 * 60 <= minutes < 9 * 60 + 30:
        return 30
    if 16 * 60 + 30 <= minutes < 19 * 60:
        return 30
    if (
        6 * 60 <= minutes < 7 * 60
        or 9 * 60 + 30 <= minutes < 10 * 60 + 30
        or 15 * 60 + 30 <= minutes < 16 * 60 + 30
        or 19 * 60 <= minutes < 20 * 60
    ):
        return 14
    if minutes < 5 * 60 or minutes >= 22 * 60:
        return -18
    return 0


def _clamp_metric(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _leg_crowding_score(
    *,
    mode: str,
    stop_count: int,
    service_state: str,
    travel_time: datetime,
    rail_fare: dict | None,
) -> int:
    local_value = travel_time.astimezone(NY_TZ)
    score = MODE_CROWDING_BASE.get(mode, 44)
    score += _rush_hour_bonus(local_value)

    if stop_count >= 14:
        score += 8
    elif stop_count >= 8:
        score += 4

    if service_state == "service_alert":
        score += 10
    elif service_state in {"no_service", "no_departures"}:
        score -= 16

    if rail_fare and rail_fare.get("estimated_period") == "peak":
        score += 12

    return _clamp_metric(score, 8, 96)


def _crowding_label(crowding_score: int) -> tuple[str, str]:
    if crowding_score >= 70:
        return "high", "High crowding"
    if crowding_score >= 45:
        return "moderate", "Moderate crowding"
    return "low", "Light crowding"


def _build_route_leg(
    *,
    mode: str,
    line: str,
    stops: list[str],
    origin: str,
    destination: str,
    travel_time: datetime,
) -> dict:
    origin_index, destination_index = _route_stop_indexes(stops, origin, destination)
    stop_count = abs(destination_index - origin_index)
    return {
        "mode": mode,
        "line": line,
        "origin": origin,
        "destination": destination,
        "origin_index": origin_index,
        "destination_index": destination_index,
        "stop_count": stop_count,
        "travel_minutes": _estimated_travel_minutes(mode, stop_count),
        "walking_minutes": _estimated_leg_walking_minutes(mode),
        "rail_fare": estimate_rail_fare(mode, line, origin, destination, travel_time),
        "counts_toward_cap": mode in OMNY_MODES,
    }


def _serialize_route_leg(leg: dict) -> dict:
    return {
        "mode": leg["mode"],
        "line": leg["line"],
        "origin": leg["origin"],
        "destination": leg["destination"],
        "stop_count": leg["stop_count"],
        "travel_minutes": leg["travel_minutes"],
        "walking_minutes": leg["walking_minutes"],
        "rail_fare": leg.get("rail_fare"),
        "counts_toward_cap": leg["counts_toward_cap"],
    }


def _route_label(legs: list[dict]) -> str:
    return " -> ".join(f"{leg['line']}" for leg in legs)


def _route_signature(legs: list[dict]) -> str:
    return "|".join(
        f"{leg['mode']}:{leg['line']}:{leg['origin']}:{leg['destination']}"
        for leg in legs
    )


def _route_transfer_stops(legs: list[dict]) -> list[str]:
    return [legs[index]["destination"] for index in range(len(legs) - 1)]


def _route_preference_labels(priorities: list[str]) -> list[str]:
    return [ROUTE_PRIORITY_LABELS[priority] for priority in priorities]


def _departure_search_time(
    *,
    time_mode: str,
    requested_time: datetime,
    travel_minutes: int,
) -> datetime:
    if time_mode == "arrive_by":
        return requested_time - timedelta(minutes=travel_minutes + 90)
    return requested_time


def _schedule_window(
    *,
    mode: str,
    time_mode: str,
    requested_time: datetime,
    travel_minutes: int,
) -> tuple[datetime, datetime]:
    before_hours = (
        RAIL_SCHEDULE_BEFORE_HOURS if mode in RAIL_MODES else SCHEDULE_BEFORE_HOURS
    )

    if time_mode == "arrive_by":
        start_time = requested_time - timedelta(
            hours=before_hours, minutes=travel_minutes
        )
    else:
        start_time = requested_time - timedelta(hours=before_hours)

    return start_time, requested_time + timedelta(hours=SCHEDULE_AFTER_HOURS)


def _arrival_datetime(arrival: dict) -> datetime | None:
    raw_value = arrival.get("arrival_time")
    if not raw_value:
        return None
    try:
        return _parse_timestamp(str(raw_value))
    except ValueError:
        return None


def _arrival_direction_bucket(arrival: dict) -> str:
    normalized_direction = str(arrival.get("direction") or "").lower()
    if "north" in normalized_direction or "west" in normalized_direction:
        return "first"
    if "south" in normalized_direction or "east" in normalized_direction:
        return "last"
    if arrival.get("direction_id") == 1:
        return "last"
    return "first"


def _target_direction_bucket(origin_index: int, destination_index: int) -> str:
    return "last" if destination_index > origin_index else "first"


def _directional_arrivals(
    arrivals: list[dict],
    origin_index: int,
    destination_index: int,
) -> list[dict]:
    target_bucket = _target_direction_bucket(origin_index, destination_index)
    matching_arrivals = [
        arrival for arrival in arrivals if _arrival_direction_bucket(arrival) == target_bucket
    ]
    return matching_arrivals or arrivals


def _sorted_directional_arrivals(
    arrivals: list[dict],
    origin_index: int,
    destination_index: int,
) -> list[dict]:
    def sort_key(arrival: dict) -> datetime:
        return _arrival_datetime(arrival) or datetime.max.replace(tzinfo=timezone.utc)

    return sorted(
        _directional_arrivals(arrivals, origin_index, destination_index),
        key=sort_key,
    )


def _build_trip_timing(
    *,
    arrivals: list[dict],
    time_mode: str,
    requested_time: datetime,
    travel_minutes: int,
    origin_index: int,
    destination_index: int,
) -> dict:
    usable_arrivals = _sorted_directional_arrivals(
        arrivals, origin_index, destination_index
    )
    selected_departure: datetime | None = None
    selected_arrival: datetime | None = None
    arrives_by_requested_time: bool | None = None

    if time_mode == "arrive_by":
        on_time_options: list[tuple[datetime, datetime]] = []
        late_options: list[tuple[datetime, datetime]] = []
        for arrival in usable_arrivals:
            departure_time = _arrival_datetime(arrival)
            if departure_time is None:
                continue
            estimated_arrival_time = departure_time + timedelta(minutes=travel_minutes)
            if estimated_arrival_time <= requested_time:
                on_time_options.append((departure_time, estimated_arrival_time))
            else:
                late_options.append((departure_time, estimated_arrival_time))

        if on_time_options:
            selected_departure, selected_arrival = max(
                on_time_options, key=lambda option: option[0]
            )
            arrives_by_requested_time = True
        elif late_options:
            selected_departure, selected_arrival = min(
                late_options, key=lambda option: option[1]
            )
            arrives_by_requested_time = False
        else:
            arrives_by_requested_time = False
    else:
        future_departures: list[tuple[datetime, datetime]] = []
        previous_departures: list[tuple[datetime, datetime]] = []
        for arrival in usable_arrivals:
            departure_time = _arrival_datetime(arrival)
            if departure_time is None:
                continue
            estimated_arrival_time = departure_time + timedelta(minutes=travel_minutes)
            if departure_time >= requested_time:
                future_departures.append((departure_time, estimated_arrival_time))
            else:
                previous_departures.append((departure_time, estimated_arrival_time))

        if future_departures:
            selected_departure, selected_arrival = min(
                future_departures, key=lambda option: option[0]
            )
        elif previous_departures:
            selected_departure, selected_arrival = max(
                previous_departures, key=lambda option: option[0]
            )

    return {
        "estimated_departure_time": (
            selected_departure.isoformat() if selected_departure else None
        ),
        "estimated_arrival_time": selected_arrival.isoformat() if selected_arrival else None,
        "travel_minutes": travel_minutes,
        "arrives_by_requested_time": arrives_by_requested_time,
    }


def _build_schedule_options(
    *,
    arrivals: list[dict],
    time_mode: str,
    requested_time: datetime,
    travel_minutes: int,
    origin_index: int,
    destination_index: int,
    selected_departure_time: str | None,
) -> list[dict]:
    selected_departure = (
        _parse_timestamp(selected_departure_time) if selected_departure_time else None
    )
    options = []

    for arrival in _sorted_directional_arrivals(
        arrivals, origin_index, destination_index
    ):
        departure_time = _arrival_datetime(arrival)
        if departure_time is None:
            continue

        estimated_arrival_time = departure_time + timedelta(minutes=travel_minutes)
        minutes_from_request = round(
            (
                estimated_arrival_time - requested_time
                if time_mode == "arrive_by"
                else departure_time - requested_time
            ).total_seconds()
            / 60
        )
        meets_requested_time = (
            estimated_arrival_time <= requested_time
            if time_mode == "arrive_by"
            else departure_time >= requested_time
        )
        relation = "after_selected"
        relation_label = "After selected time"
        if time_mode == "arrive_by":
            if estimated_arrival_time <= requested_time:
                relation = "before_arrive_by"
                relation_label = "Arrives before target"
            else:
                relation = "after_arrive_by"
                relation_label = "Arrives after target"
        elif departure_time < requested_time:
            relation = "before_selected"
            relation_label = "Before selected time"

        options.append(
            {
                "transit_mode": arrival.get("transit_mode"),
                "line": arrival.get("line"),
                "route_id": arrival.get("route_id"),
                "trip_id": arrival.get("trip_id"),
                "direction": arrival.get("direction"),
                "departure_time": departure_time.isoformat(),
                "estimated_arrival_time": estimated_arrival_time.isoformat(),
                "travel_minutes": travel_minutes,
                "minutes_from_request": minutes_from_request,
                "relation": relation,
                "relation_label": relation_label,
                "meets_requested_time": meets_requested_time,
                "is_selected": (
                    selected_departure is not None
                    and departure_time == selected_departure
                ),
            }
        )

    return options


def _alert_blocks_service(alert: dict) -> bool:
    effect = (alert.get("effect") or "").upper()
    if effect in BLOCKING_ALERT_EFFECTS:
        return True

    searchable_text = " ".join(
        str(alert.get(key) or "").lower()
        for key in ("title", "description", "effect", "cause")
    )
    return any(keyword in searchable_text for keyword in BLOCKING_ALERT_KEYWORDS)


def _travel_status_message(
    *,
    mode: str,
    service_state: str,
    time_mode: str,
    origin: str,
    destination: str,
    arrivals_message: str,
    alert_message: str,
    blocking_alerts: list[dict],
    alerts: list[dict],
    timing: dict,
    schedule_options: list[dict],
) -> str:
    if service_state == "no_service":
        alert = blocking_alerts[0]
        reason = alert.get("description") or alert.get("title") or alert.get("effect")
        return (
            f"No arrival or departure is available from {origin} to {destination} "
            f"because MTA reports this service is not running: {reason}"
        )
    if schedule_options:
        departure_time = timing.get("estimated_departure_time")
        arrival_time = timing.get("estimated_arrival_time")
        if time_mode == "arrive_by":
            if timing.get("arrives_by_requested_time"):
                return (
                    f"A departure can meet your arrive-by time from {origin} "
                    f"to {destination}. Nearby schedule options are shown below."
                )
            if departure_time and arrival_time:
                return (
                    f"No returned trip arrives by the selected time. TapWise found "
                    f"the closest option from {origin} to {destination}; nearby "
                    "departures are shown so you can choose another time."
                )
        if departure_time and arrival_time:
            return (
                f"TapWise found schedule options from {origin} to "
                f"{destination} around your selected time, including trips before "
                "and after it."
            )
    if service_state == "in_service":
        if time_mode == "arrive_by" and timing.get("arrives_by_requested_time"):
            return (
                f"A departure is available from {origin} to {destination} that can "
                "meet the selected arrive-by time."
            )
        if time_mode == "leave_at" and timing.get("estimated_arrival_time"):
            return (
                f"A departure is available from {origin} to {destination}; TapWise "
                "estimated the destination arrival from the selected leave time."
            )
        return f"Arrival and departure options are available from {origin} to {destination}."
    if service_state == "service_alert":
        return (
            f"Arrival and departure options are available, but {len(alerts)} service "
            f"{'change is' if len(alerts) == 1 else 'changes are'} active for this trip time."
        )
    if service_state == "no_departures":
        if time_mode == "arrive_by":
            return (
                f"No departure was returned early enough to get from {origin} to "
                f"{destination} by the selected arrive-by time."
            )
        if alerts:
            return (
                f"No arrival or departure was returned for {origin} to {destination} "
                "at the selected time. Active service changes are shown below."
            )
        return (
            f"No arrival or departure was returned for {origin} to {destination} "
            "at the selected time, and MTA has no active service change for that line then."
        )
    return arrivals_message or alert_message or "Travel information is unavailable right now."


def _first_payment_method_for_user(user_id: int):
    from ..models import PaymentMethod

    return PaymentMethod.query.filter_by(user_id=user_id).order_by(PaymentMethod.id.asc()).first()


def _route_candidate_score(
    *,
    mode: str,
    service_state: str,
    fare_status: dict | None,
    rail_fare: dict | None,
    time_mode: str,
    timing: dict,
    priorities: list[str],
    travel_minutes: int,
    walking_minutes: int,
    transfer_count: int,
    estimated_fare: float | None,
    crowding_score: int,
) -> int:
    score = 0
    if service_state == "in_service":
        score += 70
    elif service_state == "service_alert":
        score += 48
    elif service_state == "no_departures":
        score += 18
    elif service_state == "no_service":
        score -= 70
    else:
        score -= 20

    if mode in OMNY_MODES and fare_status:
        if fare_status.get("free_rides_active"):
            score += 28
        elif fare_status.get("rides_remaining", 12) <= 2:
            score += 14
        else:
            score += 8

    if mode in RAIL_MODES and rail_fare and rail_fare.get("estimated_price") is not None:
        score += 6
        if rail_fare.get("estimated_period") == "off_peak":
            score += 4
        if rail_fare.get("estimated_period") == "peak":
            score -= 4

    if time_mode == "arrive_by":
        if timing.get("arrives_by_requested_time"):
            score += 24
        elif timing.get("estimated_departure_time"):
            score -= 20
        else:
            score -= 12
    elif timing.get("estimated_arrival_time"):
        score += 10

    score += max(0, 10 - transfer_count * 5)

    priority_score = 0.0
    for priority in priorities:
        if priority == "fastest":
            priority_score += max(0, 150 - travel_minutes) * 0.72
        elif priority == "least_walking":
            priority_score += max(0, 40 - walking_minutes) * 1.9
        elif priority == "fewest_transfers":
            priority_score += max(0, 36 - transfer_count * 24)
        elif priority == "lowest_fare":
            priority_score += -12 if estimated_fare is None else max(0, 48 - estimated_fare * 5)
        elif priority == "least_crowded":
            priority_score += max(0, 96 - crowding_score) * 0.62
        elif priority == "most_crowded":
            priority_score += crowding_score * 0.6

    if priorities:
        score += round(priority_score / len(priorities))

    return score


def _route_candidate_reason(
    *,
    mode: str,
    service_state: str,
    fare_status: dict | None,
    rail_fare: dict | None,
    time_mode: str,
    timing: dict,
    priorities: list[str],
    travel_minutes: int,
    walking_minutes: int,
    transfer_count: int,
    estimated_fare: float | None,
    fare_label: str,
    crowding_label: str,
    transfer_stops: list[str],
) -> str:
    reasons = []
    if service_state == "no_service":
        reasons.append("MTA reports this line is not running for the selected time.")
    elif service_state == "no_departures":
        reasons.append("No arrival or departure was returned for the selected time.")
    elif service_state == "service_alert":
        reasons.append("Service is available, but an active service change is reported.")
    elif service_state == "in_service":
        reasons.append("Service is available for the selected time.")
    else:
        reasons.append("Live service information is unavailable right now.")

    if time_mode == "arrive_by":
        if timing.get("arrives_by_requested_time"):
            reasons.append("A returned departure can meet your arrive-by time.")
        else:
            reasons.append("No returned departure is early enough for your arrive-by time.")
    elif timing.get("estimated_arrival_time"):
        reasons.append("TapWise estimated the destination arrival from your selected leave time.")

    if priorities:
        reasons.append(
            "Ranked for "
            + ", ".join(_route_preference_labels(priorities))
            + "."
        )

    if transfer_count:
        transfer_label = ", ".join(transfer_stops) or "the transfer stop"
        reasons.append(
            f"{transfer_count} transfer via {transfer_label}; about "
            f"{travel_minutes} minutes riding and {walking_minutes} minutes walking."
        )
    else:
        reasons.append(
            f"Direct route; about {travel_minutes} minutes riding and "
            f"{walking_minutes} minutes walking."
        )

    reasons.append(f"{crowding_label} estimated for the selected time.")

    if estimated_fare is not None:
        reasons.append(f"Estimated fare: {fare_label}.")

    if mode in OMNY_MODES:
        active_transfer = (fare_status or {}).get("active_transfer") or {}
        if active_transfer.get("available"):
            reasons.append("Your selected OMNY method has an active transfer window.")
        elif fare_status and fare_status.get("free_rides_active"):
            reasons.append("Your selected OMNY method is already in free rides.")
        elif fare_status:
            remaining = fare_status.get("rides_remaining", 12)
            reasons.append(f"This ride can count toward your OMNY cap; {remaining} cap rides remain.")
        else:
            reasons.append("Subway and bus rides can count toward the OMNY weekly fare cap.")
    elif rail_fare and rail_fare.get("estimated_price") is not None:
        reasons.append(
            "This is a separate railroad ticket: "
            f"{rail_fare.get('estimated_period', 'estimated').replace('_', '-')} "
            f"${rail_fare['estimated_price']:.2f}."
        )
    elif mode in RAIL_MODES:
        reasons.append("This commuter railroad trip uses separate ticketing and does not count toward OMNY.")

    return " ".join(reasons)


def _route_candidate_from_legs(
    *,
    legs: list[dict],
    fare_status: dict | None,
    priorities: list[str],
    time_mode: str,
    travel_time: datetime,
) -> dict:
    first_leg = legs[0]
    total_stop_count = sum(leg["stop_count"] for leg in legs)
    transfer_count = max(0, len(legs) - 1)
    travel_minutes = (
        sum(leg["travel_minutes"] for leg in legs)
        + transfer_count * TRANSFER_BUFFER_MINUTES
    )
    walking_minutes = (
        max(leg["walking_minutes"] for leg in legs)
        + transfer_count * TRANSFER_BUFFER_MINUTES
    )
    search_time = _departure_search_time(
        time_mode=time_mode,
        requested_time=travel_time,
        travel_minutes=travel_minutes,
    )
    schedule_start, schedule_end = _schedule_window(
        mode=first_leg["mode"],
        time_mode=time_mode,
        requested_time=travel_time,
        travel_minutes=travel_minutes,
    )

    all_alerts = []
    blocking_alerts = []
    for leg in legs:
        alert_payload = get_service_alerts(
            mode=leg["mode"],
            line=leg["line"],
            limit=10,
            reference_time=travel_time,
        )
        leg_alerts = alert_payload.get("alerts", [])
        all_alerts.extend(leg_alerts)
        blocking_alerts.extend(
            alert for alert in leg_alerts if _alert_blocks_service(alert)
        )

    if blocking_alerts:
        arrivals = []
        service_state = "no_service"
        schedule_options = []
        timing = {
            "estimated_departure_time": None,
            "estimated_arrival_time": None,
            "travel_minutes": travel_minutes,
            "arrives_by_requested_time": False if time_mode == "arrive_by" else None,
        }
    else:
        arrival_payload = get_next_arrivals(
            mode=first_leg["mode"],
            line=first_leg["line"],
            stop_name=first_leg["origin"],
            limit=SCHEDULE_LIMIT,
            reference_time=schedule_start,
            end_time=schedule_end,
        )
        arrivals = arrival_payload.get("arrivals", [])
        timing = _build_trip_timing(
            arrivals=arrivals,
            time_mode=time_mode,
            requested_time=travel_time,
            travel_minutes=travel_minutes,
            origin_index=first_leg["origin_index"],
            destination_index=first_leg["destination_index"],
        )
        if arrival_payload.get("status") == "ok" and all_alerts:
            service_state = "service_alert"
        elif arrival_payload.get("status") == "ok":
            service_state = "in_service"
        elif arrival_payload.get("status") in {"empty", "partial"}:
            service_state = "no_departures"
        else:
            service_state = "unavailable"
        if (
            time_mode == "arrive_by"
            and service_state in {"in_service", "service_alert"}
            and not timing.get("arrives_by_requested_time")
        ):
            service_state = "no_departures"
        schedule_options = []
        if arrival_payload.get("status") == "ok":
            schedule_options = _build_schedule_options(
                arrivals=arrivals,
                time_mode=time_mode,
                requested_time=travel_time,
                travel_minutes=travel_minutes,
                origin_index=first_leg["origin_index"],
                destination_index=first_leg["destination_index"],
                selected_departure_time=timing.get("estimated_departure_time"),
            )
            if service_state == "no_departures" and schedule_options:
                service_state = "service_alert" if all_alerts else "in_service"

    estimated_fare, fare_label = _route_fare_estimate(legs, fare_status)
    crowding_score = max(
        _leg_crowding_score(
            mode=leg["mode"],
            stop_count=leg["stop_count"],
            service_state=service_state,
            travel_time=travel_time,
            rail_fare=leg.get("rail_fare"),
        )
        for leg in legs
    )
    crowding_level, crowding_label = _crowding_label(crowding_score)
    first_rail_fare = first_leg.get("rail_fare")
    score = _route_candidate_score(
        mode=first_leg["mode"],
        service_state=service_state,
        fare_status=fare_status,
        rail_fare=first_rail_fare,
        time_mode=time_mode,
        timing=timing,
        priorities=priorities,
        travel_minutes=travel_minutes,
        walking_minutes=walking_minutes,
        transfer_count=transfer_count,
        estimated_fare=estimated_fare,
        crowding_score=crowding_score,
    )
    if total_stop_count <= 4:
        score += 6
    elif total_stop_count <= 10:
        score += 3

    transfer_stops = _route_transfer_stops(legs)
    return {
        "mode": first_leg["mode"],
        "line": first_leg["line"],
        "route_label": _route_label(legs),
        "route_signature": _route_signature(legs),
        "origin": first_leg["origin"],
        "destination": legs[-1]["destination"],
        "service_state": service_state,
        "score": score,
        "stop_count": total_stop_count,
        "transfer_count": transfer_count,
        "transfer_stops": transfer_stops,
        "walking_minutes": walking_minutes,
        "estimated_fare": estimated_fare,
        "fare_label": fare_label,
        "crowding_score": crowding_score,
        "crowding_level": crowding_level,
        "crowding_label": crowding_label,
        "preference_labels": _route_preference_labels(priorities),
        "time_mode": time_mode,
        "requested_time": travel_time.isoformat(),
        "departure_search_time": search_time.isoformat(),
        "schedule_window_start": schedule_start.isoformat(),
        "schedule_window_end": schedule_end.isoformat(),
        "estimated_departure_time": timing.get("estimated_departure_time"),
        "estimated_arrival_time": timing.get("estimated_arrival_time"),
        "travel_minutes": timing.get("travel_minutes"),
        "arrives_by_requested_time": timing.get("arrives_by_requested_time"),
        "schedule_options": schedule_options,
        "message": _route_candidate_reason(
            mode=first_leg["mode"],
            service_state=service_state,
            fare_status=fare_status,
            rail_fare=first_rail_fare,
            time_mode=time_mode,
            timing=timing,
            priorities=priorities,
            travel_minutes=travel_minutes,
            walking_minutes=walking_minutes,
            transfer_count=transfer_count,
            estimated_fare=estimated_fare,
            fare_label=fare_label,
            crowding_label=crowding_label,
            transfer_stops=transfer_stops,
        ),
        "next_arrivals": arrivals,
        "alerts": all_alerts,
        "blocking_alerts": blocking_alerts,
        "rail_fare": first_rail_fare,
        "counts_toward_cap": any(leg["mode"] in OMNY_MODES for leg in legs),
        "legs": [_serialize_route_leg(leg) for leg in legs],
    }


def _route_blueprints(
    *,
    options: dict,
    origin: str,
    destination: str,
    preferred_mode: str,
    preferred_line: str,
    travel_time: datetime,
) -> list[list[dict]]:
    blueprints: list[list[dict]] = []
    seen_signatures: set[str] = set()
    origin_routes = []
    destination_routes = []

    for mode, line_options in options.items():
        if preferred_mode and mode != preferred_mode:
            continue
        for line, stops in line_options.items():
            if preferred_line and line != preferred_line:
                continue
            if origin in stops:
                origin_routes.append((mode, line, stops))
            if destination in stops:
                destination_routes.append((mode, line, stops))
            if origin in stops and destination in stops and origin != destination:
                leg = _build_route_leg(
                    mode=mode,
                    line=line,
                    stops=stops,
                    origin=origin,
                    destination=destination,
                    travel_time=travel_time,
                )
                signature = _route_signature([leg])
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    blueprints.append([leg])

    transfer_options: list[tuple[int, list[dict]]] = []
    for first_mode, first_line, first_stops in origin_routes:
        for second_mode, second_line, second_stops in destination_routes:
            if first_mode == second_mode and first_line == second_line:
                continue
            shared_stops = sorted(
                set(first_stops).intersection(second_stops) - {origin, destination}
            )
            ranked_transfer_stops: list[tuple[int, str]] = []
            for transfer_stop in shared_stops:
                first_stop_count = abs(
                    first_stops.index(transfer_stop) - first_stops.index(origin)
                )
                second_stop_count = abs(
                    second_stops.index(destination) - second_stops.index(transfer_stop)
                )
                if first_stop_count == 0 or second_stop_count == 0:
                    continue
                ranked_transfer_stops.append(
                    (first_stop_count + second_stop_count, transfer_stop)
                )

            for _, transfer_stop in sorted(ranked_transfer_stops)[
                :MAX_TRANSFER_STOPS_PER_PAIR
            ]:
                legs = [
                    _build_route_leg(
                        mode=first_mode,
                        line=first_line,
                        stops=first_stops,
                        origin=origin,
                        destination=transfer_stop,
                        travel_time=travel_time,
                    ),
                    _build_route_leg(
                        mode=second_mode,
                        line=second_line,
                        stops=second_stops,
                        origin=transfer_stop,
                        destination=destination,
                        travel_time=travel_time,
                    ),
                ]
                signature = _route_signature(legs)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                total_stop_count = sum(leg["stop_count"] for leg in legs)
                transfer_options.append((total_stop_count, legs))

    transfer_options.sort(key=lambda item: item[0])
    blueprints.extend(
        legs for _, legs in transfer_options[:MAX_TRANSFER_CANDIDATES]
    )
    return blueprints


def _load_preferences(user_id: int) -> dict[tuple[str, str, str], RouteNotificationPreference]:
    preferences = RouteNotificationPreference.query.filter_by(user_id=user_id).all()
    return {
        _preference_key(
            preference.transit_mode,
            preference.transit_line,
            preference.entry_stop,
        ): preference
        for preference in preferences
    }


def _build_frequent_routes(user_id: int, limit: int = 5) -> list[dict]:
    rides = (
        Ride.query.filter_by(user_id=user_id)
        .order_by(desc(Ride.timestamp))
        .all()
    )
    preferences = _load_preferences(user_id)
    grouped: dict[tuple[str, str, str, str], dict] = {}

    for ride in rides:
        key = (
            ride.transit_mode,
            ride.transit_line,
            ride.entry_stop,
            ride.exit_stop,
        )
        grouped.setdefault(
            key,
            {
                "transit_mode": ride.transit_mode,
                "line": ride.transit_line,
                "entry_stop": ride.entry_stop,
                "exit_stop": ride.exit_stop,
                "ride_count": 0,
                "last_used_at": ride.timestamp,
            },
        )
        grouped[key]["ride_count"] += 1
        if ride.timestamp > grouped[key]["last_used_at"]:
            grouped[key]["last_used_at"] = ride.timestamp

    frequent_routes = sorted(
        grouped.values(),
        key=lambda route: (route["ride_count"], route["last_used_at"]),
        reverse=True,
    )[:limit]

    for route in frequent_routes:
        preference = preferences.get(
            _preference_key(route["transit_mode"], route["line"], route["entry_stop"])
        )
        route["notifications_enabled"] = True if preference is None else preference.enabled
        route["last_used_at"] = route["last_used_at"].isoformat()

    return frequent_routes


@transit_bp.get("/routes")
@jwt_required()
def list_routes():
    user_id = _user_id()
    mode = (request.args.get("mode") or "").strip().lower()
    route_counts: dict[tuple[str, str], int] = {}
    for ride in Ride.query.filter_by(user_id=user_id).all():
        key = (ride.transit_mode, ride.transit_line)
        route_counts[key] = route_counts.get(key, 0) + 1

    summaries = []
    for summary in list_route_summaries():
        if mode and summary["transit_mode"] != mode:
            continue
        key = (summary["transit_mode"], summary["line"])
        summaries.append(
            {
                **summary,
                "ride_count": route_counts.get(key, 0),
                "is_frequent": route_counts.get(key, 0) > 0,
            }
        )

    return jsonify({"routes": summaries})


@transit_bp.get("/arrivals")
@jwt_required()
def arrivals():
    mode = (request.args.get("mode") or "").strip().lower()
    line = (request.args.get("line") or "").strip()
    stop = (request.args.get("stop") or "").strip()
    limit = min(12, max(1, request.args.get("limit", 6, type=int)))

    if not mode or not line or not stop:
        return jsonify({"error": "Please choose a route and stop."}), 400

    options = get_transit_options().get(mode)
    if not options or stop not in options.get(line, []):
        return jsonify({"error": "Please choose a valid route and stop."}), 400

    return jsonify(get_next_arrivals(mode=mode, line=line, stop_name=stop, limit=limit))


@transit_bp.get("/service-alerts")
@jwt_required()
def service_alerts():
    mode = (request.args.get("mode") or "").strip().lower() or None
    line = (request.args.get("line") or "").strip() or None
    limit = min(30, max(1, request.args.get("limit", 12, type=int)))
    if mode and mode not in get_transit_options():
        return jsonify({"error": "Please choose a valid transit mode."}), 400

    return jsonify(get_service_alerts(mode=mode, line=line, limit=limit))


@transit_bp.get("/travel-status")
@jwt_required()
def travel_status():
    mode = (request.args.get("mode") or "").strip().lower()
    line = (request.args.get("line") or "").strip()
    origin = (request.args.get("origin") or "").strip()
    destination = (request.args.get("destination") or "").strip()
    time_mode = _parse_time_mode(request.args.get("time_mode"))

    if not mode or not line or not origin or not destination:
        return jsonify({"error": "Please choose a service, route, origin, and destination."}), 400
    if not is_valid_transit_selection(mode, line, origin, destination):
        return jsonify({"error": "Please choose a valid route and stops."}), 400

    try:
        travel_time = _parse_timestamp(request.args.get("timestamp"))
    except ValueError:
        return jsonify({"error": "Please choose a valid travel time."}), 400

    route_stops = get_transit_options()[mode][line]
    origin_index, destination_index = _route_stop_indexes(
        route_stops, origin, destination
    )
    stop_count = abs(destination_index - origin_index)
    travel_minutes = _estimated_travel_minutes(mode, stop_count)
    search_time = _departure_search_time(
        time_mode=time_mode,
        requested_time=travel_time,
        travel_minutes=travel_minutes,
    )
    schedule_start, schedule_end = _schedule_window(
        mode=mode,
        time_mode=time_mode,
        requested_time=travel_time,
        travel_minutes=travel_minutes,
    )

    alert_payload = get_service_alerts(
        mode=mode,
        line=line,
        limit=30,
        reference_time=travel_time,
    )
    alerts = alert_payload.get("alerts", [])
    blocking_alerts = [alert for alert in alerts if _alert_blocks_service(alert)]
    schedule_options: list[dict] = []

    if blocking_alerts:
        arrivals_payload = {
            "status": "empty",
            "message": "No arrivals or departures are available while service is not running.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "arrivals": [],
        }
        service_state = "no_service"
    else:
        arrivals_payload = get_next_arrivals(
            mode=mode,
            line=line,
            stop_name=origin,
            limit=SCHEDULE_LIMIT,
            reference_time=schedule_start,
            end_time=schedule_end,
        )
        timing = _build_trip_timing(
            arrivals=arrivals_payload.get("arrivals", []),
            time_mode=time_mode,
            requested_time=travel_time,
            travel_minutes=travel_minutes,
            origin_index=origin_index,
            destination_index=destination_index,
        )
        if arrivals_payload.get("status") == "ok" and alerts:
            service_state = "service_alert"
        elif arrivals_payload.get("status") == "ok":
            service_state = "in_service"
        elif arrivals_payload.get("status") in {"empty", "partial"}:
            service_state = "no_departures"
        else:
            service_state = "unavailable"
        if (
            time_mode == "arrive_by"
            and service_state in {"in_service", "service_alert"}
            and not timing.get("arrives_by_requested_time")
        ):
            service_state = "no_departures"
        if arrivals_payload.get("status") == "ok":
            schedule_options = _build_schedule_options(
                arrivals=arrivals_payload.get("arrivals", []),
                time_mode=time_mode,
                requested_time=travel_time,
                travel_minutes=travel_minutes,
                origin_index=origin_index,
                destination_index=destination_index,
                selected_departure_time=timing.get("estimated_departure_time"),
            )
            if service_state == "no_departures" and schedule_options:
                service_state = "service_alert" if alerts else "in_service"

    if blocking_alerts:
        timing = {
            "estimated_departure_time": None,
            "estimated_arrival_time": None,
            "travel_minutes": travel_minutes,
            "arrives_by_requested_time": False if time_mode == "arrive_by" else None,
        }

    message = _travel_status_message(
        mode=mode,
        service_state=service_state,
        time_mode=time_mode,
        origin=origin,
        destination=destination,
        arrivals_message=arrivals_payload.get("message", ""),
        alert_message=alert_payload.get("message", ""),
        blocking_alerts=blocking_alerts,
        alerts=alerts,
        timing=timing,
        schedule_options=schedule_options,
    )

    return jsonify(
        {
            "status": service_state,
            "service_state": service_state,
            "mode": mode,
            "line": line,
            "origin": origin,
            "destination": destination,
            "timestamp": travel_time.isoformat(),
            "time_mode": time_mode,
            "requested_time": travel_time.isoformat(),
            "departure_search_time": search_time.isoformat(),
            "schedule_window_start": schedule_start.isoformat(),
            "schedule_window_end": schedule_end.isoformat(),
            "estimated_departure_time": timing.get("estimated_departure_time"),
            "estimated_arrival_time": timing.get("estimated_arrival_time"),
            "travel_minutes": timing.get("travel_minutes"),
            "arrives_by_requested_time": timing.get("arrives_by_requested_time"),
            "schedule_options": schedule_options,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "arrivals_status": arrivals_payload.get("status", "unavailable"),
            "arrivals_message": arrivals_payload.get("message", ""),
            "arrivals": arrivals_payload.get("arrivals", []),
            "alerts_status": alert_payload.get("status", "unavailable"),
            "alerts_message": alert_payload.get("message", ""),
            "alerts": alerts,
            "blocking_alerts": blocking_alerts,
        }
    )


@transit_bp.get("/route-suggestions")
@jwt_required()
def route_suggestions():
    user_id = _user_id()
    origin = (request.args.get("origin") or "").strip()
    destination = (request.args.get("destination") or "").strip()
    preferred_mode = (request.args.get("mode") or "").strip().lower()
    preferred_line = (request.args.get("line") or "").strip()
    time_mode = _parse_time_mode(request.args.get("time_mode"))
    payment_method_id = request.args.get("payment_method_id", type=int)
    limit = min(6, max(1, request.args.get("limit", 4, type=int)))
    priorities = _parse_route_priorities(
        request.args.getlist("priorities") + request.args.getlist("priority")
    )

    if not origin or not destination:
        return jsonify({"error": "Please choose an origin and destination."}), 400

    try:
        travel_time = _parse_timestamp(request.args.get("timestamp"))
    except ValueError:
        return jsonify({"error": "Please choose a valid travel time."}), 400

    options = get_transit_options()
    method = None
    if payment_method_id:
        from ..models import PaymentMethod

        method = PaymentMethod.query.filter_by(id=payment_method_id, user_id=user_id).first()
    if method is None:
        method = _first_payment_method_for_user(user_id)

    fare_status = None
    if method is not None:
        fare_status = calculate_fare_status(method.rides, now=travel_time).to_dict()

    route_blueprints = _route_blueprints(
        options=options,
        origin=origin,
        destination=destination,
        preferred_mode=preferred_mode,
        preferred_line=preferred_line,
        travel_time=travel_time,
    )
    candidates = [
        _route_candidate_from_legs(
            legs=legs,
            fare_status=fare_status,
            priorities=priorities,
            time_mode=time_mode,
            travel_time=travel_time,
        )
        for legs in route_blueprints
    ]

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["service_state"] == "in_service",
            -item["transfer_count"],
            -item["travel_minutes"],
            -item["walking_minutes"],
            -(item["estimated_fare"] if item["estimated_fare"] is not None else 999),
            -item["stop_count"],
        ),
        reverse=True,
    )

    if candidates:
        best = candidates[0]
        message = (
            f"Best option for {', '.join(_route_preference_labels(priorities))}: "
            f"{best['route_label']} ({best['mode'].replace('_', ' ').title()}). "
            f"{best['message']}"
        )
    else:
        message = (
            "No route in the TapWise catalog contains the selected stop pair yet. "
            "Try a different transfer hub or service."
        )

    return jsonify(
        {
            "status": "ok" if candidates else "empty",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timestamp": travel_time.isoformat(),
            "time_mode": time_mode,
            "requested_time": travel_time.isoformat(),
            "origin": origin,
            "destination": destination,
            "priorities": priorities,
            "preference_labels": _route_preference_labels(priorities),
            "message": message,
            "fare_status": fare_status,
            "suggestions": candidates[:limit],
        }
    )


@transit_bp.get("/rail-fare-estimate")
@jwt_required()
def rail_fare_estimate():
    mode = (request.args.get("mode") or "").strip().lower()
    line = (request.args.get("line") or "").strip()
    origin = (request.args.get("origin") or "").strip()
    destination = (request.args.get("destination") or "").strip()

    if not is_rail_fare_mode(mode):
        return jsonify({"error": "Rail fares are only available for LIRR and Metro-North."}), 400
    if not is_valid_transit_selection(mode, line, origin, destination):
        return jsonify({"error": "Please choose a valid railroad route and stations."}), 400

    try:
        timestamp = _parse_timestamp(request.args.get("timestamp"))
    except ValueError:
        return jsonify({"error": "Please choose a valid travel time."}), 400

    return jsonify(estimate_rail_fare(mode, line, origin, destination, timestamp))


@transit_bp.get("/frequent-routes")
@jwt_required()
def frequent_routes():
    return jsonify({"routes": _build_frequent_routes(_user_id())})


@transit_bp.get("/personalized-alerts")
@jwt_required()
def personalized_alerts():
    frequent_routes = _build_frequent_routes(_user_id())
    notifications = []

    for route in frequent_routes:
        route_alerts = get_service_alerts(
            mode=route["transit_mode"], line=route["line"], limit=3
        )
        route["alerts"] = route_alerts.get("alerts", [])
        route["alert_status"] = route_alerts.get("status", "unavailable")

        if not route["notifications_enabled"]:
            continue

        for alert in route["alerts"]:
            notifications.append(
                {
                    "id": f'{route["transit_mode"]}:{route["line"]}:{alert["id"]}',
                    "transit_mode": route["transit_mode"],
                    "line": route["line"],
                    "entry_stop": route["entry_stop"],
                    "title": alert["title"],
                    "message": alert["description"] or alert["effect"],
                    "created_at": route_alerts["generated_at"],
                }
            )

    return jsonify(
        {
            "routes": frequent_routes,
            "notifications": notifications[:10],
        }
    )


@transit_bp.get("/notification-preferences")
@jwt_required()
def notification_preferences():
    preferences = RouteNotificationPreference.query.filter_by(user_id=_user_id()).all()
    return jsonify([_serialize_preference(preference) for preference in preferences])


@transit_bp.post("/notification-preferences")
@jwt_required()
def upsert_notification_preference():
    user_id = _user_id()
    payload = request.get_json() or {}
    mode = (payload.get("transit_mode") or "").strip().lower()
    line = (payload.get("transit_line") or payload.get("line") or "").strip()
    entry_stop = (payload.get("entry_stop") or "").strip()
    enabled = bool(payload.get("enabled", True))

    if entry_stop:
        exit_stop = entry_stop
        if not is_valid_transit_selection(mode, line, entry_stop, exit_stop):
            return jsonify({"error": "Please choose a valid route and stop."}), 400
    elif mode not in get_transit_options() or line not in get_transit_options()[mode]:
        return jsonify({"error": "Please choose a valid route."}), 400

    preference = RouteNotificationPreference.query.filter_by(
        user_id=user_id,
        transit_mode=mode,
        transit_line=line,
        entry_stop=entry_stop,
    ).first()

    if preference is None:
        preference = RouteNotificationPreference(
            user_id=user_id,
            transit_mode=mode,
            transit_line=line,
            entry_stop=entry_stop,
            enabled=enabled,
        )
        db.session.add(preference)
    else:
        preference.enabled = enabled

    db.session.commit()
    return jsonify(_serialize_preference(preference))
