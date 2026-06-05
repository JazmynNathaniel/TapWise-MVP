from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_PATH = DATA_DIR / "transit_catalog.json"
METADATA_PATH = DATA_DIR / "transit_metadata.json"
FALLBACK_OPTIONS = {
    "subway": {
        "A": ["Inwood-207 St", "125 St", "59 St-Columbus Circle", "Fulton St"],
    },
    "bus": {
        "M15-SBS": ["South Ferry Terminal", "14 St", "34 St", "125 St"],
    },
}
FALLBACK_METADATA = {
    mode: {
        line: [{"name": stop, "stop_ids": [], "route_ids": [line]} for stop in stops]
        for line, stops in line_options.items()
    }
    for mode, line_options in FALLBACK_OPTIONS.items()
}


@lru_cache(maxsize=1)
def get_transit_options() -> dict:
    if DATA_PATH.exists():
        with DATA_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    return FALLBACK_OPTIONS


@lru_cache(maxsize=1)
def get_transit_metadata() -> dict:
    if METADATA_PATH.exists():
        with METADATA_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)

    metadata = {}
    for mode, line_options in get_transit_options().items():
        metadata[mode] = {
            line: [{"name": stop, "stop_ids": [], "route_ids": [line]} for stop in stops]
            for line, stops in line_options.items()
        }
    return metadata or FALLBACK_METADATA


def refresh_transit_options_cache() -> None:
    get_transit_options.cache_clear()
    get_transit_metadata.cache_clear()


def is_valid_transit_selection(mode: str, line: str, entry_stop: str, exit_stop: str) -> bool:
    mode_options = get_transit_options().get(mode)
    if not mode_options:
        return False
    stop_options = mode_options.get(line)
    if not stop_options:
        return False
    return entry_stop in stop_options and exit_stop in stop_options


def list_route_summaries() -> list[dict]:
    summaries = []
    options = get_transit_options()
    for mode, line_options in options.items():
        for line, stops in line_options.items():
            summaries.append(
                {
                    "transit_mode": mode,
                    "line": line,
                    "stop_count": len(stops),
                    "sample_stops": stops[:3],
                }
            )
    return summaries


def get_route_stops(mode: str, line: str) -> list[dict]:
    return get_transit_metadata().get(mode, {}).get(line, [])


def get_stop_ids_for_selection(mode: str, line: str, stop_name: str) -> list[str]:
    for stop in get_route_stops(mode, line):
        if stop.get("name") == stop_name:
            return list(stop.get("stop_ids") or [])
    return []


def get_route_ids_for_selection(mode: str, line: str) -> list[str]:
    route_ids = set()
    for stop in get_route_stops(mode, line):
        route_ids.update(stop.get("route_ids") or [])
    return sorted(route_ids or {line})
