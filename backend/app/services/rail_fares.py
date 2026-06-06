from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


NY_TZ = ZoneInfo("America/New_York")
RAIL_FARE_EFFECTIVE_DATE = "2026-01-04"
RAIL_FARE_MODES = {"lirr", "metro_north"}
LIRR_SOURCE_URL = "https://www.mta.info/document/194866"
METRO_NORTH_HARLEM_HUDSON_SOURCE_URL = "https://www.mta.info/document/194931"
METRO_NORTH_NEW_HAVEN_SOURCE_URL = "https://www.mta.info/document/194941"
MTA_RAIL_FARES_URL = "https://www.mta.info/fares-tolls/lirr-metro-north"


def _station_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _zone_map(groups: dict[int, list[str]]) -> dict[str, int]:
    station_zones: dict[str, int] = {}
    for zone, stations in groups.items():
        for station in stations:
            station_zones[_station_key(station)] = zone
    return station_zones


LIRR_STATION_ZONES = _zone_map(
    {
        1: [
            "Penn Station",
            "Grand Central",
            "Atlantic Terminal",
            "Long Island City",
            "Hunterspoint Avenue",
            "Nostrand Avenue",
            "East New York",
            "Woodside",
            "Forest Hills",
            "Kew Gardens",
            "Mets-Willets Point",
        ],
        3: [
            "Jamaica",
            "Locust Manor",
            "Laurelton",
            "Rosedale",
            "St. Albans",
            "Hollis",
            "Queens Village",
            "Flushing",
            "Flushing Main Street",
            "Murray Hill",
            "Broadway",
            "Auburndale",
            "Bayside",
            "Douglaston",
            "Little Neck",
        ],
        4: [
            "Gibson",
            "Hewlett",
            "Woodmere",
            "Cedarhurst",
            "Lawrence",
            "Inwood",
            "Far Rockaway",
            "Lynbrook",
            "Valley Stream",
            "Westwood",
            "Malverne",
            "Lakeview",
            "Hempstead Gardens",
            "West Hempstead",
            "Elmont-UBS",
            "Elmont-UBS Arena",
            "Belmont Park",
            "Bellerose",
            "Stewart Manor",
            "Nassau Boulevard",
            "Garden City",
            "Country Life Press",
            "Hempstead",
            "Floral Park",
            "New Hyde Park",
            "Merillon Avenue",
            "Mineola",
            "East Williston",
            "Great Neck",
            "Manhasset",
            "Plandome",
            "Port Washington",
        ],
        7: [
            "Centre Avenue",
            "East Rockaway",
            "Oceanside",
            "Island Park",
            "Long Beach",
            "Rockville Centre",
            "Baldwin",
            "Freeport",
            "Merrick",
            "Bellmore",
            "Wantagh",
            "Seaford",
            "Massapequa",
            "Massapequa Park",
            "Carle Place",
            "Westbury",
            "Hicksville",
            "Bethpage",
            "Farmingdale",
            "Syosset",
            "Albertson",
            "Roslyn",
            "Greenvale",
            "Glen Head",
            "Sea Cliff",
            "Glen Street",
            "Glen Cove",
            "Locust Valley",
            "Oyster Bay",
        ],
        9: [
            "Amityville",
            "Copiague",
            "Lindenhurst",
            "Babylon",
            "Pinelawn",
            "Wyandanch",
            "Deer Park",
            "Cold Spring Harbor",
            "Huntington",
            "Greenlawn",
            "Northport",
        ],
        10: [
            "Bay Shore",
            "Islip",
            "Great River",
            "Oakdale",
            "Sayville",
            "Patchogue",
            "Brentwood",
            "Central Islip",
            "Ronkonkoma",
            "Medford",
            "Kings Park",
            "Smithtown",
            "St. James",
            "Stony Brook",
            "Port Jefferson",
        ],
        12: ["Bellport", "Mastic-Shirley", "Speonk", "Yaphank"],
        14: [
            "Westhampton",
            "Hampton Bays",
            "Southampton",
            "Bridgehampton",
            "East Hampton",
            "Amagansett",
            "Montauk",
            "Riverhead",
            "Mattituck",
            "Southold",
            "Greenport",
        ],
    }
)

LIRR_FARES = {
    1: {
        1: {"peak": 7.25, "off_peak": 5.25},
        3: {"peak": 7.25, "off_peak": 5.25},
        4: {"peak": 13.50, "off_peak": 10.00},
        7: {"peak": 15.25, "off_peak": 11.25},
        9: {"peak": 18.25, "off_peak": 13.50},
        10: {"peak": 21.50, "off_peak": 16.00},
        12: {"peak": 25.50, "off_peak": 18.75},
        14: {"peak": 33.00, "off_peak": 24.50},
    },
    3: {
        1: {"peak": 7.25, "off_peak": 5.25},
        3: {"peak": 6.00, "off_peak": 4.50},
        4: {"peak": 9.00, "off_peak": 6.75},
        7: {"peak": 10.75, "off_peak": 8.00},
        9: {"peak": 13.25, "off_peak": 9.75},
        10: {"peak": 16.50, "off_peak": 12.25},
        12: {"peak": 22.00, "off_peak": 16.25},
        14: {"peak": 28.25, "off_peak": 21.00},
    },
    4: {
        1: {"peak": 13.50, "off_peak": 10.00},
        3: {"peak": 9.00, "off_peak": 6.75},
        4: {"peak": 3.75, "off_peak": 3.75},
        7: {"peak": 3.75, "off_peak": 3.75},
        9: {"peak": 6.50, "off_peak": 6.50},
        10: {"peak": 8.25, "off_peak": 8.25},
        12: {"peak": 12.25, "off_peak": 12.25},
        14: {"peak": 19.50, "off_peak": 19.50},
    },
    7: {
        1: {"peak": 15.25, "off_peak": 11.25},
        3: {"peak": 10.75, "off_peak": 8.00},
        4: {"peak": 3.75, "off_peak": 3.75},
        7: {"peak": 3.75, "off_peak": 3.75},
        9: {"peak": 3.75, "off_peak": 3.75},
        10: {"peak": 6.50, "off_peak": 6.50},
        12: {"peak": 10.75, "off_peak": 10.75},
        14: {"peak": 18.00, "off_peak": 18.00},
    },
    9: {
        1: {"peak": 18.25, "off_peak": 13.50},
        3: {"peak": 13.25, "off_peak": 9.75},
        4: {"peak": 6.50, "off_peak": 6.50},
        7: {"peak": 3.75, "off_peak": 3.75},
        9: {"peak": 3.75, "off_peak": 3.75},
        10: {"peak": 3.75, "off_peak": 3.75},
        12: {"peak": 8.25, "off_peak": 8.25},
        14: {"peak": 14.75, "off_peak": 14.75},
    },
    10: {
        1: {"peak": 21.50, "off_peak": 16.00},
        3: {"peak": 16.50, "off_peak": 12.25},
        4: {"peak": 8.25, "off_peak": 8.25},
        7: {"peak": 6.50, "off_peak": 6.50},
        9: {"peak": 3.75, "off_peak": 3.75},
        10: {"peak": 3.75, "off_peak": 3.75},
        12: {"peak": 3.75, "off_peak": 3.75},
        14: {"peak": 10.50, "off_peak": 10.50},
    },
    12: {
        1: {"peak": 25.50, "off_peak": 18.75},
        3: {"peak": 22.00, "off_peak": 16.25},
        4: {"peak": 12.25, "off_peak": 12.25},
        7: {"peak": 10.75, "off_peak": 10.75},
        9: {"peak": 8.25, "off_peak": 8.25},
        10: {"peak": 3.75, "off_peak": 3.75},
        12: {"peak": 3.75, "off_peak": 3.75},
        14: {"peak": 7.25, "off_peak": 7.25},
    },
    14: {
        1: {"peak": 33.00, "off_peak": 24.50},
        3: {"peak": 28.25, "off_peak": 21.00},
        4: {"peak": 19.50, "off_peak": 19.50},
        7: {"peak": 18.00, "off_peak": 18.00},
        9: {"peak": 14.75, "off_peak": 14.75},
        10: {"peak": 10.50, "off_peak": 10.50},
        12: {"peak": 7.25, "off_peak": 7.25},
        14: {"peak": 3.75, "off_peak": 3.75},
    },
}

METRO_NORTH_HARLEM_HUDSON_ZONES = _zone_map(
    {
        1: ["Grand Central", "Harlem-125 St", "Harlem-125th Street"],
        2: [
            "Yankees-E 153 St",
            "Morris Heights",
            "Morris Hts.",
            "University Heights",
            "University Hts.",
            "Marble Hill",
            "Spuyten Duyvil",
            "Riverdale",
            "Melrose",
            "Tremont",
            "Fordham",
            "Botanical Garden",
            "Williams Bridge",
            "Woodlawn",
            "Wakefield",
        ],
        3: [
            "Ludlow",
            "Yonkers",
            "Glenwood",
            "Greystone",
            "Mt Vernon West",
            "Mt. Vernon West",
            "Fleetwood",
            "Bronxville",
            "Tuckahoe",
            "Crestwood",
        ],
        4: [
            "Hastings-on-Hudson",
            "Dobbs Ferry",
            "Ardsley-on-Hudson",
            "Irvington",
            "Scarsdale",
            "Hartsdale",
            "White Plains",
            "North White Plains",
        ],
        5: [
            "Tarrytown",
            "Philipse Manor",
            "Scarborough",
            "Ossining",
            "Croton-Harmon",
            "Valhalla",
            "Mt Pleasant",
            "Mt. Pleasant",
            "Hawthorne",
            "Pleasantville",
            "Chappaqua",
        ],
        6: [
            "Cortlandt",
            "Peekskill",
            "Mt Kisco",
            "Mount Kisco",
            "Bedford Hills",
            "Katonah",
            "Goldens Bridge",
        ],
        7: [
            "Manitou",
            "Garrison",
            "Cold Spring",
            "Breakneck Ridge",
            "Purdy's",
            "Purdy's",
            "Croton Falls",
            "Brewster",
            "Southeast",
        ],
        8: ["Beacon", "New Hamburg", "Patterson", "Pawling", "Appalachian Trail"],
        9: ["Poughkeepsie", "Harlem Valley-Wingdale", "Dover Plains"],
        10: ["Tenmile River", "Wassaic"],
    }
)

METRO_NORTH_NEW_HAVEN_ZONES = _zone_map(
    {
        1: ["Grand Central", "Harlem-125 St", "Harlem-125th Street"],
        11: ["Fordham"],
        12: ["Mt Vernon East", "Mt. Vernon East", "Pelham", "New Rochelle"],
        13: ["Larchmont", "Mamaroneck", "Harrison"],
        14: ["Rye", "Port Chester"],
        15: ["Greenwich", "Cos Cob", "Riverside", "Old Greenwich"],
        16: ["Stamford", "Noroton Heights", "Darien", "Rowayton"],
        17: ["South Norwalk", "East Norwalk"],
        18: [
            "Westport",
            "Green's Farms",
            "Southport",
            "Fairfield",
            "Fairfield-Black Rock",
        ],
        19: ["Bridgeport"],
        20: ["Stratford", "Milford"],
        21: ["West Haven", "New Haven", "New Haven - Union Station", "New Haven - State St"],
        31: ["Glenbrook", "Springdale", "Talmadge Hill", "New Canaan"],
        41: ["Merritt 7", "Wilton", "Cannondale"],
        42: ["Branchville", "Redding", "Bethel", "Danbury"],
        51: ["Derby-Shelton", "Ansonia", "Seymour", "Beacon Falls", "Naugatuck", "Waterbury"],
    }
)

METRO_NORTH_TERMINAL_FARES = {
    1: {"peak": 7.25, "off_peak": 5.25},
    2: {"peak": 7.25, "off_peak": 5.25},
    3: {"peak": 12.50, "off_peak": 9.25},
    4: {"peak": 13.75, "off_peak": 10.25},
    5: {"peak": 16.00, "off_peak": 11.75},
    6: {"peak": 19.00, "off_peak": 14.00},
    7: {"peak": 21.75, "off_peak": 16.00},
    8: {"peak": 25.00, "off_peak": 18.50},
    9: {"peak": 28.25, "off_peak": 21.00},
    10: {"peak": 29.75, "off_peak": 22.00},
    11: {"peak": 7.25, "off_peak": 5.25},
    12: {"peak": 12.25, "off_peak": 9.00},
    13: {"peak": 13.75, "off_peak": 10.25},
    14: {"peak": 15.00, "off_peak": 11.00},
    15: {"peak": 15.00, "off_peak": 11.00},
    16: {"peak": 17.00, "off_peak": 12.50},
    17: {"peak": 18.25, "off_peak": 13.50},
    18: {"peak": 19.75, "off_peak": 14.50},
    19: {"peak": 21.75, "off_peak": 16.00},
    20: {"peak": 23.25, "off_peak": 17.25},
    21: {"peak": 26.00, "off_peak": 19.25},
    31: {"peak": 17.00, "off_peak": 12.50},
    41: {"peak": 18.75, "off_peak": 14.00},
    42: {"peak": 19.75, "off_peak": 14.50},
    51: {"peak": 23.00, "off_peak": 17.00},
}

METRO_NORTH_HARLEM_HUDSON_INTERMEDIATE = {
    2: {2: 3.50, 3: 3.50, 4: 4.50, 5: 6.25, 6: 8.75, 7: 12.50, 8: 15.75, 9: 18.25, 10: 19.50},
    3: {2: 3.50, 3: 3.50, 4: 3.50, 5: 5.50, 6: 8.00, 7: 9.75, 8: 14.25, 9: 16.75, 10: 17.25},
    4: {2: 4.50, 3: 3.50, 4: 3.50, 5: 3.50, 6: 6.50, 7: 8.50, 8: 12.50, 9: 15.00, 10: 15.75},
    5: {2: 6.25, 3: 5.50, 4: 3.50, 5: 3.50, 6: 3.50, 7: 7.25, 8: 9.00, 9: 13.00, 10: 14.00},
    6: {2: 8.75, 3: 8.00, 4: 6.50, 5: 3.50, 6: 3.50, 7: 3.50, 8: 7.25, 9: 9.00, 10: 10.75},
    7: {2: 12.50, 3: 9.75, 4: 8.50, 5: 7.25, 6: 3.50, 7: 3.50, 8: 4.50, 9: 7.00, 10: 8.00},
    8: {2: 15.75, 3: 14.25, 4: 12.50, 5: 9.00, 6: 7.25, 7: 4.50, 8: 3.50, 9: 4.50, 10: 5.00},
    9: {2: 18.25, 3: 16.75, 4: 15.00, 5: 13.00, 6: 9.00, 7: 7.00, 8: 4.50, 9: 3.50, 10: 3.50},
    10: {2: 19.50, 3: 17.25, 4: 15.75, 5: 14.00, 6: 10.75, 7: 8.00, 8: 5.00, 9: 3.50, 10: 3.50},
}

METRO_NORTH_NEW_HAVEN_INTERMEDIATE = {
    11: {11: 3.50, 12: 3.50, 13: 4.50, 14: 5.75, 15: 5.75, 16: 6.75, 17: 8.00, 18: 9.75, 19: 11.50, 20: 12.75, 21: 15.75, 31: 6.75, 41: 8.50, 42: 11.25, 51: 13.75},
    12: {11: 3.50, 12: 3.50, 13: 3.50, 14: 4.25, 15: 5.50, 16: 6.75, 17: 8.00, 18: 9.75, 19: 11.50, 20: 12.75, 21: 15.75, 31: 6.75, 41: 8.50, 42: 9.75, 51: 13.25},
    13: {11: 4.50, 12: 3.50, 13: 3.50, 14: 4.25, 15: 4.25, 16: 5.75, 17: 6.75, 18: 8.25, 19: 10.00, 20: 11.50, 21: 14.25, 31: 5.75, 41: 7.25, 42: 8.50, 51: 12.25},
    14: {11: 5.75, 12: 4.25, 13: 4.25, 14: 3.50, 15: 4.00, 16: 5.50, 17: 6.50, 18: 8.00, 19: 9.50, 20: 10.75, 21: 13.75, 31: 5.50, 41: 6.75, 42: 8.00, 51: 11.75},
    15: {11: 5.75, 12: 5.50, 13: 4.25, 14: 4.00, 15: 3.25, 16: 3.25, 17: 4.00, 18: 5.25, 19: 6.75, 20: 8.25, 21: 11.25, 31: 3.25, 41: 4.50, 42: 6.50, 51: 8.75},
    16: {11: 6.75, 12: 6.75, 13: 5.75, 14: 5.50, 15: 3.25, 16: 3.25, 17: 3.25, 18: 3.25, 19: 5.25, 20: 6.50, 21: 9.25, 31: 3.25, 41: 4.00, 42: 5.50, 51: 7.50},
    17: {11: 8.00, 12: 8.00, 13: 6.75, 14: 6.50, 15: 4.00, 16: 3.25, 17: 3.25, 18: 3.25, 19: 4.25, 20: 5.25, 21: 8.00, 31: 4.00, 41: 3.25, 42: 4.00, 51: 6.75},
    18: {11: 9.75, 12: 9.75, 13: 8.25, 14: 8.00, 15: 5.25, 16: 3.25, 17: 3.25, 18: 3.25, 19: 3.25, 20: 4.00, 21: 6.25, 31: 5.25, 41: 4.00, 42: 5.75, 51: 5.75},
    19: {11: 11.50, 12: 11.50, 13: 10.00, 14: 9.50, 15: 6.75, 16: 5.25, 17: 4.25, 18: 3.25, 19: 3.25, 20: 3.25, 21: 4.25, 31: 6.50, 41: 5.25, 42: 6.75, 51: 3.25},
    20: {11: 12.75, 12: 12.75, 13: 11.50, 14: 10.75, 15: 8.25, 16: 6.50, 17: 5.25, 18: 4.00, 19: 3.25, 20: 3.25, 21: 4.00, 31: 7.25, 41: 5.75, 42: 7.25, 51: 3.25},
    21: {11: 15.75, 12: 15.75, 13: 14.25, 14: 13.75, 15: 11.25, 16: 9.25, 17: 8.00, 18: 6.25, 19: 4.25, 20: 4.00, 21: 3.25, 31: 9.75, 41: 8.00, 42: 10.00, 51: 6.75},
    31: {11: 6.75, 12: 6.75, 13: 5.75, 14: 5.50, 15: 3.25, 16: 3.25, 17: 4.00, 18: 5.25, 19: 6.50, 20: 7.25, 21: 9.75, 31: 3.25, 41: 5.25, 42: 6.50, 51: 8.75},
    41: {11: 8.50, 12: 8.50, 13: 7.25, 14: 6.75, 15: 4.50, 16: 4.00, 17: 3.25, 18: 4.00, 19: 5.25, 20: 5.75, 21: 8.00, 31: 5.25, 41: 3.00, 42: 3.00, 51: 8.00},
    42: {11: 11.25, 12: 9.75, 13: 8.50, 14: 8.00, 15: 6.50, 16: 5.50, 17: 4.00, 18: 5.75, 19: 6.75, 20: 7.25, 21: 10.00, 31: 6.50, 41: 3.00, 42: 3.00, 51: 10.00},
    51: {11: 13.75, 12: 13.25, 13: 12.25, 14: 11.75, 15: 8.75, 16: 7.50, 17: 6.75, 18: 5.75, 19: 3.25, 20: 3.25, 21: 6.75, 31: 8.75, 41: 8.00, 42: 10.00, 51: 3.00},
}


def is_rail_fare_mode(mode: str | None) -> bool:
    return (mode or "").strip().lower() in RAIL_FARE_MODES


def _ensure_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_2026_mta_holiday(local_value: datetime) -> bool:
    return local_value.date().isoformat() in {
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-05-25",
        "2026-07-04",
        "2026-09-07",
        "2026-11-26",
        "2026-11-27",
        "2026-12-25",
    }


def _is_lirr_terminal(station: str) -> bool:
    return _station_key(station) in {
        _station_key(value)
        for value in [
            "Penn Station",
            "Grand Central",
            "Atlantic Terminal",
            "Long Island City",
            "Hunterspoint Avenue",
        ]
    }


def _is_metro_north_terminal(station: str) -> bool:
    return _station_key(station) in {
        _station_key("Grand Central"),
        _station_key("Harlem-125 St"),
        _station_key("Harlem-125th Street"),
    }


def _estimate_period(mode: str, origin: str, destination: str, timestamp: datetime) -> str:
    local_value = _ensure_utc(timestamp).astimezone(NY_TZ)
    if local_value.weekday() >= 5 or _is_2026_mta_holiday(local_value):
        return "off_peak"

    minutes = local_value.hour * 60 + local_value.minute
    morning_arrival = 6 * 60 <= minutes < 10 * 60
    evening_departure = 16 * 60 <= minutes < 20 * 60
    metro_north_morning_departure = 6 * 60 <= minutes < 9 * 60

    if mode == "lirr":
        if _is_lirr_terminal(destination) and morning_arrival:
            return "peak"
        if _is_lirr_terminal(origin) and evening_departure:
            return "peak"
        return "off_peak"

    if _is_metro_north_terminal(destination) and morning_arrival:
        return "peak"
    if _is_metro_north_terminal(origin) and evening_departure:
        return "peak"
    if _station_key(origin) == _station_key("Grand Central") and metro_north_morning_departure:
        return "peak"
    return "off_peak"


def _lookup_pair(table: dict[int, dict[int, object]], origin_zone: int, destination_zone: int):
    row = table.get(origin_zone, {})
    fare = row.get(destination_zone)
    if fare is not None:
        return fare
    return table.get(destination_zone, {}).get(origin_zone)


def _base_payload(
    mode: str,
    line: str,
    origin: str,
    destination: str,
    timestamp: datetime,
    status: str = "ok",
) -> dict:
    return {
        "status": status,
        "mode": mode,
        "line": line,
        "origin": origin,
        "destination": destination,
        "timestamp": _ensure_utc(timestamp).isoformat(),
        "currency": "USD",
        "effective_date": RAIL_FARE_EFFECTIVE_DATE,
    }


def _unavailable_payload(
    mode: str,
    line: str,
    origin: str,
    destination: str,
    timestamp: datetime,
    message: str,
) -> dict:
    return {
        **_base_payload(mode, line, origin, destination, timestamp, status="unavailable"),
        "message": message,
        "origin_zone": None,
        "destination_zone": None,
        "peak_price": None,
        "off_peak_price": None,
        "estimated_price": None,
        "estimated_period": None,
        "source_label": "MTA railroad fares",
        "source_url": MTA_RAIL_FARES_URL,
    }


def _lirr_zone(station: str) -> int | None:
    return LIRR_STATION_ZONES.get(_station_key(station))


def _metro_north_zone(line: str, station: str) -> int | None:
    line_key = _station_key(line)
    station_key = _station_key(station)
    if line_key in {
        _station_key("New Haven"),
        _station_key("New Canaan"),
        _station_key("Danbury"),
        _station_key("Waterbury"),
    }:
        return (
            METRO_NORTH_NEW_HAVEN_ZONES.get(station_key)
            or METRO_NORTH_HARLEM_HUDSON_ZONES.get(station_key)
        )
    return (
        METRO_NORTH_HARLEM_HUDSON_ZONES.get(station_key)
        or METRO_NORTH_NEW_HAVEN_ZONES.get(station_key)
    )


def _estimate_lirr_fare(
    mode: str,
    line: str,
    origin: str,
    destination: str,
    timestamp: datetime,
) -> dict:
    origin_zone = _lirr_zone(origin)
    destination_zone = _lirr_zone(destination)
    if origin_zone is None or destination_zone is None:
        return _unavailable_payload(
            mode,
            line,
            origin,
            destination,
            timestamp,
            "Fare zones are not available for this LIRR station pair yet.",
        )

    fares = _lookup_pair(LIRR_FARES, origin_zone, destination_zone)
    if not isinstance(fares, dict):
        return _unavailable_payload(
            mode,
            line,
            origin,
            destination,
            timestamp,
            "Ticket prices are not available for this LIRR zone pair yet.",
        )

    estimated_period = _estimate_period(mode, origin, destination, timestamp)
    return {
        **_base_payload(mode, line, origin, destination, timestamp),
        "message": "LIRR one-way fare estimate from the 2026 MTA zone table.",
        "origin_zone": origin_zone,
        "destination_zone": destination_zone,
        "peak_price": fares["peak"],
        "off_peak_price": fares["off_peak"],
        "estimated_price": fares[estimated_period],
        "estimated_period": estimated_period,
        "source_label": "MTA LIRR fares effective January 4, 2026",
        "source_url": LIRR_SOURCE_URL,
    }


def _estimate_metro_north_fare(
    mode: str,
    line: str,
    origin: str,
    destination: str,
    timestamp: datetime,
) -> dict:
    origin_zone = _metro_north_zone(line, origin)
    destination_zone = _metro_north_zone(line, destination)
    if origin_zone is None or destination_zone is None:
        return _unavailable_payload(
            mode,
            line,
            origin,
            destination,
            timestamp,
            "Fare zones are not available for this Metro-North station pair yet.",
        )

    terminal_zone = None
    if origin_zone == 1:
        terminal_zone = destination_zone
    elif destination_zone == 1:
        terminal_zone = origin_zone

    if terminal_zone is not None:
        fares = METRO_NORTH_TERMINAL_FARES.get(terminal_zone)
        if not fares:
            return _unavailable_payload(
                mode,
                line,
                origin,
                destination,
                timestamp,
                "Ticket prices are not available for this Metro-North zone yet.",
            )
        estimated_period = _estimate_period(mode, origin, destination, timestamp)
        source_url = (
            METRO_NORTH_NEW_HAVEN_SOURCE_URL
            if terminal_zone >= 11
            else METRO_NORTH_HARLEM_HUDSON_SOURCE_URL
        )
        return {
            **_base_payload(mode, line, origin, destination, timestamp),
            "message": "Metro-North one-way fare estimate from the 2026 MTA zone table.",
            "origin_zone": origin_zone,
            "destination_zone": destination_zone,
            "peak_price": fares["peak"],
            "off_peak_price": fares["off_peak"],
            "estimated_price": fares[estimated_period],
            "estimated_period": estimated_period,
            "source_label": "MTA Metro-North fares effective January 4, 2026",
            "source_url": source_url,
        }

    if origin_zone in METRO_NORTH_HARLEM_HUDSON_INTERMEDIATE:
        price = _lookup_pair(
            METRO_NORTH_HARLEM_HUDSON_INTERMEDIATE, origin_zone, destination_zone
        )
        source_url = METRO_NORTH_HARLEM_HUDSON_SOURCE_URL
    else:
        price = _lookup_pair(
            METRO_NORTH_NEW_HAVEN_INTERMEDIATE, origin_zone, destination_zone
        )
        source_url = METRO_NORTH_NEW_HAVEN_SOURCE_URL

    if not isinstance(price, (int, float)):
        return _unavailable_payload(
            mode,
            line,
            origin,
            destination,
            timestamp,
            "Intermediate Metro-North ticket prices are not available for this zone pair yet.",
        )

    return {
        **_base_payload(mode, line, origin, destination, timestamp),
        "message": "Metro-North intermediate one-way fare estimate from the 2026 MTA zone table.",
        "origin_zone": origin_zone,
        "destination_zone": destination_zone,
        "peak_price": price,
        "off_peak_price": price,
        "estimated_price": price,
        "estimated_period": "intermediate",
        "source_label": "MTA Metro-North intermediate fares effective January 4, 2026",
        "source_url": source_url,
    }


def estimate_rail_fare(
    mode: str | None,
    line: str | None,
    origin: str | None,
    destination: str | None,
    timestamp: datetime | None = None,
) -> dict | None:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in RAIL_FARE_MODES:
        return None

    line_value = (line or "").strip()
    origin_value = (origin or "").strip()
    destination_value = (destination or "").strip()
    fare_timestamp = _ensure_utc(timestamp)

    if not origin_value or not destination_value:
        return _unavailable_payload(
            normalized_mode,
            line_value,
            origin_value,
            destination_value,
            fare_timestamp,
            "Choose an origin and destination to estimate a railroad ticket price.",
        )

    if _station_key(origin_value) == _station_key(destination_value):
        return _unavailable_payload(
            normalized_mode,
            line_value,
            origin_value,
            destination_value,
            fare_timestamp,
            "Choose two different stations to estimate a railroad ticket price.",
        )

    if normalized_mode == "lirr":
        return _estimate_lirr_fare(
            normalized_mode, line_value, origin_value, destination_value, fare_timestamp
        )
    return _estimate_metro_north_fare(
        normalized_mode, line_value, origin_value, destination_value, fare_timestamp
    )
