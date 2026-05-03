from __future__ import annotations

import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path


FEEDS = {
    "subway": ["https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"],
    "bus": [
        "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_bx.zip",
        "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_b.zip",
        "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_m.zip",
        "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_q.zip",
        "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_si.zip",
        "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_busco.zip",
    ],
}

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "transit_catalog.json"


def _read_csv(zip_file: zipfile.ZipFile, name: str):
    with zip_file.open(name) as file:
        text = io.TextIOWrapper(file, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text)


def _download_zip(url: str) -> zipfile.ZipFile:
    with urllib.request.urlopen(url) as response:
        payload = response.read()
    return zipfile.ZipFile(io.BytesIO(payload))


def _build_route_stop_map(url: str) -> dict[str, list[str]]:
    with _download_zip(url) as zip_file:
        route_names = {}
        for row in _read_csv(zip_file, "routes.txt"):
            route_name = (row.get("route_short_name") or row.get("route_long_name") or "").strip()
            if route_name:
                route_names[row["route_id"]] = route_name

        trip_to_route = {}
        for row in _read_csv(zip_file, "trips.txt"):
            route_name = route_names.get(row["route_id"])
            if route_name:
                trip_to_route[row["trip_id"]] = route_name

        stop_names = {}
        for row in _read_csv(zip_file, "stops.txt"):
            stop_names[row["stop_id"]] = (row.get("stop_name") or "").strip()

        best_trip_by_route: dict[str, list[str]] = {}
        current_trip_id = None
        current_route_name = None
        current_stop_ids: list[str] = []

        def flush_current_trip() -> None:
            nonlocal current_trip_id, current_route_name, current_stop_ids
            if not current_trip_id or not current_route_name:
                return
            deduped_stop_ids = []
            seen_stop_ids = set()
            for stop_id in current_stop_ids:
                if stop_id and stop_id not in seen_stop_ids:
                    deduped_stop_ids.append(stop_id)
                    seen_stop_ids.add(stop_id)
            if len(deduped_stop_ids) > len(best_trip_by_route.get(current_route_name, [])):
                best_trip_by_route[current_route_name] = deduped_stop_ids

        for row in _read_csv(zip_file, "stop_times.txt"):
            trip_id = row["trip_id"]
            if trip_id != current_trip_id:
                flush_current_trip()
                current_trip_id = trip_id
                current_route_name = trip_to_route.get(trip_id)
                current_stop_ids = []
            if current_route_name:
                current_stop_ids.append(row["stop_id"])
        flush_current_trip()

        route_stop_map = {}
        for route_name, stop_ids in best_trip_by_route.items():
            stop_list = []
            seen_names = set()
            for stop_id in stop_ids:
                stop_name = stop_names.get(stop_id, "")
                if stop_name and stop_name not in seen_names:
                    stop_list.append(stop_name)
                    seen_names.add(stop_name)
            if stop_list:
                route_stop_map[route_name] = stop_list

        return dict(sorted(route_stop_map.items()))


def main() -> None:
    catalog = {"subway": {}, "bus": {}}
    for mode, urls in FEEDS.items():
        combined = {}
        for url in urls:
            combined.update(_build_route_stop_map(url))
        catalog[mode] = dict(sorted(combined.items()))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Wrote transit catalog to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
