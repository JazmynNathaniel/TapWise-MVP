from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "transit_catalog.json"
FALLBACK_OPTIONS = {
    "subway": {
        "A": ["Inwood-207 St", "125 St", "59 St-Columbus Circle", "Fulton St"],
    },
    "bus": {
        "M15-SBS": ["South Ferry Terminal", "14 St", "34 St", "125 St"],
    },
}


@lru_cache(maxsize=1)
def get_transit_options() -> dict:
    if DATA_PATH.exists():
        with DATA_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    return FALLBACK_OPTIONS


def refresh_transit_options_cache() -> None:
    get_transit_options.cache_clear()


def is_valid_transit_selection(mode: str, line: str, entry_stop: str, exit_stop: str) -> bool:
    mode_options = get_transit_options().get(mode)
    if not mode_options:
        return False
    stop_options = mode_options.get(line)
    if not stop_options:
        return False
    return entry_stop in stop_options and exit_stop in stop_options
