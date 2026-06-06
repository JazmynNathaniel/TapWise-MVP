from __future__ import annotations

import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .transit_data import get_route_ids_for_selection, get_stop_ids_for_selection

try:
    from google.transit import gtfs_realtime_pb2
except ImportError:  # pragma: no cover - deployment dependency, graceful local fallback
    gtfs_realtime_pb2 = None


MTA_GTFS_RT_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds"
SUBWAY_ALERTS_FEED = f"{MTA_GTFS_RT_BASE}/camsys%2Fsubway-alerts"
BUS_TRIP_UPDATES_FEED = "https://gtfsrt.prod.obanyc.com/tripUpdates"
BUS_ALERTS_FEED = "https://gtfsrt.prod.obanyc.com/alerts"
RAILROAD_TRIP_UPDATE_FEEDS = {
    "lirr": f"{MTA_GTFS_RT_BASE}/lirr%2Fgtfs-lirr",
    "metro_north": f"{MTA_GTFS_RT_BASE}/mnr%2Fgtfs-mnr",
}
RAILROAD_ALERT_FEEDS = {
    "lirr": f"{MTA_GTFS_RT_BASE}/camsys%2Flirr-alerts",
    "metro_north": f"{MTA_GTFS_RT_BASE}/camsys%2Fmnr-alerts",
}
CACHE_SECONDS = 30
LIVE_UPDATES_UNAVAILABLE = "Live updates are taking a moment. Please check again soon."
ARRIVALS_UNAVAILABLE = "Live arrivals are taking a moment. Please check again soon."
ALERTS_UNAVAILABLE = "Service updates are taking a moment. Please check again soon."

SUBWAY_ROUTE_FEEDS = {
    "1": "nyct%2Fgtfs",
    "2": "nyct%2Fgtfs",
    "3": "nyct%2Fgtfs",
    "4": "nyct%2Fgtfs",
    "5": "nyct%2Fgtfs",
    "6": "nyct%2Fgtfs",
    "7": "nyct%2Fgtfs",
    "A": "nyct%2Fgtfs-ace",
    "C": "nyct%2Fgtfs-ace",
    "E": "nyct%2Fgtfs-ace",
    "H": "nyct%2Fgtfs-ace",
    "B": "nyct%2Fgtfs-bdfm",
    "D": "nyct%2Fgtfs-bdfm",
    "F": "nyct%2Fgtfs-bdfm",
    "M": "nyct%2Fgtfs-bdfm",
    "G": "nyct%2Fgtfs-g",
    "J": "nyct%2Fgtfs-jz",
    "Z": "nyct%2Fgtfs-jz",
    "L": "nyct%2Fgtfs-l",
    "N": "nyct%2Fgtfs-nqrw",
    "Q": "nyct%2Fgtfs-nqrw",
    "R": "nyct%2Fgtfs-nqrw",
    "W": "nyct%2Fgtfs-nqrw",
    "FS": "nyct%2Fgtfs-bdfm",
    "GS": "nyct%2Fgtfs",
}

_FEED_CACHE: dict[str, tuple[float, bytes]] = {}


class RealtimeUnavailable(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_from_timestamp(value: int | None) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _feed_response(
    *,
    status: str,
    message: str,
    arrivals: list[dict] | None = None,
    alerts: list[dict] | None = None,
) -> dict:
    payload = {
        "status": status,
        "message": message,
        "generated_at": _now().isoformat(),
    }
    if arrivals is not None:
        payload["arrivals"] = arrivals
    if alerts is not None:
        payload["alerts"] = alerts
    return payload


def _build_headers() -> dict[str, str]:
    headers = {"User-Agent": "TapWise/1.0"}
    api_key = os.getenv("MTA_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _fetch_feed(url: str) -> bytes:
    cached = _FEED_CACHE.get(url)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    request = urllib.request.Request(url, headers=_build_headers())
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RealtimeUnavailable(LIVE_UPDATES_UNAVAILABLE) from exc

    _FEED_CACHE[url] = (now + CACHE_SECONDS, payload)
    return payload


def _parse_feed(url: str):
    if gtfs_realtime_pb2 is None:
        raise RealtimeUnavailable(LIVE_UPDATES_UNAVAILABLE)

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(_fetch_feed(url))
    return feed


def _subway_feed_urls(line: str, route_ids: list[str]) -> list[str]:
    feed_names = []
    for route_id in [line, *route_ids]:
        feed_name = SUBWAY_ROUTE_FEEDS.get(route_id)
        if feed_name and feed_name not in feed_names:
            feed_names.append(feed_name)

    return [f"{MTA_GTFS_RT_BASE}/{feed_name}" for feed_name in feed_names]


def _bus_feed_url(base_url: str) -> str | None:
    api_key = os.getenv("MTA_BUS_TIME_API_KEY", "").strip()
    if not api_key:
        return None

    return f"{base_url}?{urllib.parse.urlencode({'key': api_key})}"


def _route_id_matches(route_id: str, line: str, route_ids: list[str]) -> bool:
    normalized = route_id.strip()
    if not normalized:
        return False
    if normalized == line or normalized in route_ids:
        return True
    suffix = normalized.rsplit("_", 1)[-1]
    return suffix == line


def _arrival_timestamp(stop_time_update) -> int | None:
    if stop_time_update.HasField("arrival") and stop_time_update.arrival.time:
        return int(stop_time_update.arrival.time)
    if stop_time_update.HasField("departure") and stop_time_update.departure.time:
        return int(stop_time_update.departure.time)
    return None


def _trip_direction_id(trip) -> int | None:
    try:
        if trip.HasField("direction_id"):
            return int(trip.direction_id)
    except ValueError:
        return None
    return None


def _direction_label(stop_id: str, direction_id: int | None) -> str:
    if stop_id.endswith("N"):
        return "Northbound"
    if stop_id.endswith("S"):
        return "Southbound"
    if direction_id is not None:
        return f"Direction {direction_id}"
    return "Inbound"


def _build_arrival(
    *,
    mode: str,
    line: str,
    stop_name: str,
    stop_id: str,
    route_id: str,
    trip_id: str,
    direction_id: int | None,
    timestamp: int,
    now: datetime,
) -> dict:
    arrival_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    seconds_until = max(0, (arrival_time - now).total_seconds())
    return {
        "transit_mode": mode,
        "line": line,
        "route_id": route_id or line,
        "stop": stop_name,
        "stop_id": stop_id,
        "trip_id": trip_id,
        "direction": _direction_label(stop_id, direction_id),
        "direction_id": direction_id,
        "arrival_time": arrival_time.isoformat(),
        "minutes_until": max(0, math.ceil(seconds_until / 60)),
    }


def _arrivals_from_feed(
    *,
    feed,
    mode: str,
    line: str,
    route_ids: list[str],
    stop_name: str,
    stop_ids: set[str],
    now: datetime,
) -> list[dict]:
    arrivals = []
    now_timestamp = int(now.timestamp())

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue

        trip = entity.trip_update.trip
        route_id = trip.route_id
        direction_id = _trip_direction_id(trip)
        if not _route_id_matches(route_id, line, route_ids):
            continue

        for stop_update in entity.trip_update.stop_time_update:
            stop_id = stop_update.stop_id
            if stop_id not in stop_ids:
                continue

            timestamp = _arrival_timestamp(stop_update)
            if not timestamp or timestamp < now_timestamp:
                continue

            arrivals.append(
                _build_arrival(
                    mode=mode,
                    line=line,
                    stop_name=stop_name,
                    stop_id=stop_id,
                    route_id=route_id,
                    trip_id=trip.trip_id,
                    direction_id=direction_id,
                    timestamp=timestamp,
                    now=now,
                )
            )

    return arrivals


def get_next_arrivals(
    *,
    mode: str,
    line: str,
    stop_name: str,
    limit: int = 6,
) -> dict:
    route_ids = get_route_ids_for_selection(mode, line)
    stop_ids = set(get_stop_ids_for_selection(mode, line, stop_name))
    if not stop_ids:
        return _feed_response(
            status="unavailable",
            message="We don't have live arrivals for this stop yet.",
            arrivals=[],
        )

    if mode == "bus":
        feed_url = _bus_feed_url(BUS_TRIP_UPDATES_FEED)
        if not feed_url:
            return _feed_response(
                status="unavailable",
                message="Live bus arrivals are not connected yet.",
                arrivals=[],
            )
        feed_urls = [feed_url]
    elif mode in RAILROAD_TRIP_UPDATE_FEEDS:
        feed_urls = [RAILROAD_TRIP_UPDATE_FEEDS[mode]]
    else:
        feed_urls = _subway_feed_urls(line, route_ids)

    if not feed_urls:
        return _feed_response(
            status="unavailable",
            message="We don't have live arrivals for this route yet.",
            arrivals=[],
        )

    try:
        now = _now()
        arrivals: list[dict] = []
        for feed_url in feed_urls:
            arrivals.extend(
                _arrivals_from_feed(
                    feed=_parse_feed(feed_url),
                    mode=mode,
                    line=line,
                    route_ids=route_ids,
                    stop_name=stop_name,
                    stop_ids=stop_ids,
                    now=now,
                )
            )
    except RealtimeUnavailable:
        return _feed_response(
            status="unavailable", message=ARRIVALS_UNAVAILABLE, arrivals=[]
        )

    deduped = {
        (arrival["trip_id"], arrival["stop_id"], arrival["arrival_time"]): arrival
        for arrival in arrivals
    }
    sorted_arrivals = sorted(
        deduped.values(), key=lambda arrival: arrival["arrival_time"]
    )[:limit]
    return _feed_response(
        status="ok" if sorted_arrivals else "empty",
        message=(
            "Live arrivals are ready."
            if sorted_arrivals
            else "No upcoming arrivals to show for this stop right now. Check again in a moment."
        ),
        arrivals=sorted_arrivals,
    )


def _translated_text(value) -> str:
    translations = list(value.translation)
    if not translations:
        return ""

    preferred = next(
        (
            translation.text
            for translation in translations
            if translation.language.lower().startswith("en")
        ),
        "",
    )
    return preferred or translations[0].text


def _enum_name(enum_owner, field_name: str, value: int) -> str:
    try:
        descriptor = enum_owner.DESCRIPTOR.fields_by_name[field_name].enum_type
        return descriptor.values_by_number[value].name
    except (AttributeError, KeyError):
        return "UNKNOWN"


def _alert_route_ids(alert) -> list[str]:
    route_ids = []
    for selector in alert.informed_entity:
        if selector.route_id and selector.route_id not in route_ids:
            route_ids.append(selector.route_id)
    return route_ids


def _alert_active_periods(alert) -> list[dict]:
    periods = []
    for period in alert.active_period:
        periods.append(
            {
                "start": _iso_from_timestamp(period.start),
                "end": _iso_from_timestamp(period.end),
            }
        )
    return periods


def _alert_is_current(alert, now_timestamp: int) -> bool:
    if not alert.active_period:
        return True

    for period in alert.active_period:
        starts_before_now = not period.start or period.start <= now_timestamp
        ends_after_now = not period.end or period.end >= now_timestamp
        if starts_before_now and ends_after_now:
            return True
    return False


def _alerts_from_feed(*, feed, mode: str, line: str | None, route_ids: list[str]) -> list[dict]:
    alerts = []
    now_timestamp = int(time.time())

    for entity in feed.entity:
        if not entity.HasField("alert") or not _alert_is_current(entity.alert, now_timestamp):
            continue

        alert = entity.alert
        alert_route_ids = _alert_route_ids(alert)
        if line and alert_route_ids:
            if not any(
                _route_id_matches(route_id, line, route_ids)
                for route_id in alert_route_ids
            ):
                continue

        display_line = line
        if not display_line and alert_route_ids:
            display_line = alert_route_ids[0].rsplit("_", 1)[-1]

        alerts.append(
            {
                "id": entity.id,
                "transit_mode": mode,
                "line": display_line,
                "route_ids": alert_route_ids,
                "title": _translated_text(alert.header_text) or "Service alert",
                "description": _translated_text(alert.description_text),
                "effect": _enum_name(alert, "effect", alert.effect),
                "cause": _enum_name(alert, "cause", alert.cause),
                "active_periods": _alert_active_periods(alert),
            }
        )

    return alerts


def get_service_alerts(
    *,
    mode: str | None = None,
    line: str | None = None,
    limit: int = 12,
) -> dict:
    modes = [mode] if mode else ["subway", "bus", *RAILROAD_ALERT_FEEDS]
    alerts: list[dict] = []
    messages = []

    for active_mode in modes:
        route_ids = get_route_ids_for_selection(active_mode, line) if line else []
        if active_mode == "bus":
            feed_url = _bus_feed_url(BUS_ALERTS_FEED)
            if not feed_url:
                messages.append("Live bus service updates are not connected yet.")
                continue
        elif active_mode in RAILROAD_ALERT_FEEDS:
            feed_url = RAILROAD_ALERT_FEEDS[active_mode]
        else:
            feed_url = SUBWAY_ALERTS_FEED

        try:
            alerts.extend(
                _alerts_from_feed(
                    feed=_parse_feed(feed_url),
                    mode=active_mode,
                    line=line,
                    route_ids=route_ids,
                )
            )
        except RealtimeUnavailable:
            messages.append(ALERTS_UNAVAILABLE)

    status = "ok"
    if messages and not alerts:
        status = "unavailable"
    elif messages:
        status = "partial"

    return _feed_response(
        status=status,
        message=" ".join(messages) if messages else "Service updates are ready.",
        alerts=alerts[:limit],
    )
