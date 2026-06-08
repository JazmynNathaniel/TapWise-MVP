from __future__ import annotations

from datetime import datetime, timedelta, timezone

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

    return score


def _route_candidate_reason(
    *,
    mode: str,
    service_state: str,
    fare_status: dict | None,
    rail_fare: dict | None,
    time_mode: str,
    timing: dict,
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

    candidates = []
    for mode, line_options in options.items():
        if preferred_mode and mode != preferred_mode:
            continue
        for line, stops in line_options.items():
            if preferred_line and line != preferred_line:
                continue
            if origin not in stops or destination not in stops or origin == destination:
                continue

            origin_index, destination_index = _route_stop_indexes(
                stops, origin, destination
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
                limit=10,
                reference_time=travel_time,
            )
            alerts = alert_payload.get("alerts", [])
            blocking_alerts = [alert for alert in alerts if _alert_blocks_service(alert)]

            if blocking_alerts:
                arrivals = []
                service_state = "no_service"
                schedule_options = []
            else:
                arrival_payload = get_next_arrivals(
                    mode=mode,
                    line=line,
                    stop_name=origin,
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
                    origin_index=origin_index,
                    destination_index=destination_index,
                )
                if arrival_payload.get("status") == "ok" and alerts:
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

            rail_fare = estimate_rail_fare(mode, line, origin, destination, travel_time)
            score = _route_candidate_score(
                mode=mode,
                service_state=service_state,
                fare_status=fare_status,
                rail_fare=rail_fare,
                time_mode=time_mode,
                timing=timing,
            )
            if stop_count <= 4:
                score += 6
            elif stop_count <= 10:
                score += 3

            candidates.append(
                {
                    "mode": mode,
                    "line": line,
                    "origin": origin,
                    "destination": destination,
                    "service_state": service_state,
                    "score": score,
                    "stop_count": stop_count,
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
                        mode=mode,
                        service_state=service_state,
                        fare_status=fare_status,
                        rail_fare=rail_fare,
                        time_mode=time_mode,
                        timing=timing,
                    ),
                    "next_arrivals": arrivals,
                    "alerts": alerts,
                    "blocking_alerts": blocking_alerts,
                    "rail_fare": rail_fare,
                    "counts_toward_cap": mode in OMNY_MODES,
                }
            )

    candidates.sort(
        key=lambda item: (
            item["score"],
            -item["stop_count"],
            item["service_state"] == "in_service",
        ),
        reverse=True,
    )

    if candidates:
        best = candidates[0]
        message = (
            f"Best direct option: {best['line']} "
            f"({best['mode'].replace('_', ' ').title()}). {best['message']}"
        )
    else:
        message = (
            "No direct route in the TapWise catalog contains both selected stops. "
            "Try a transfer hub or another service."
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
