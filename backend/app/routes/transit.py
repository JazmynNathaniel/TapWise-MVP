from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import desc

from ..extensions import db
from ..models import Ride, RouteNotificationPreference
from ..services.mta_realtime import get_next_arrivals, get_service_alerts
from ..services.transit_data import (
    get_transit_options,
    is_valid_transit_selection,
    list_route_summaries,
)

transit_bp = Blueprint("transit", __name__)


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
