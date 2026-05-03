from __future__ import annotations

from datetime import datetime, timezone

from .fare_engine import calculate_fare_status


def build_recommendation(payment_methods, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    statuses = []

    for method in payment_methods:
        status = calculate_fare_status([ride.timestamp for ride in method.rides], now=now)
        statuses.append(
            {
                "payment_method_id": method.id,
                "label": method.label,
                "status": status.to_dict(),
            }
        )

    if not statuses:
        return {
            "best_payment_method_id": None,
            "message": "Add a payment method to start tracking OMNY progress.",
            "warning": None,
            "estimated_rides_until_free": None,
            "methods": [],
        }

    best_method = min(
        statuses,
        key=lambda item: (
            0 if item["status"]["free_rides_active"] else 1,
            item["status"]["rides_remaining"],
            item["label"].lower(),
        ),
    )

    progressed_methods = [
        item
        for item in statuses
        if item["status"]["rides_taken"] > 0 and not item["status"]["free_rides_active"]
    ]
    warning = None
    if len(progressed_methods) > 1:
        warning = "Switching methods right now will reset your progress toward the current fare cap."

    if best_method["status"]["free_rides_active"]:
        message = f"Use {best_method['label']} - free rides are active."
        estimated = 0
    else:
        remaining = best_method["status"]["rides_remaining"]
        ride_word = "ride" if remaining == 1 else "rides"
        message = f"Use {best_method['label']} - {remaining} {ride_word} left until free trips."
        estimated = remaining

    return {
        "best_payment_method_id": best_method["payment_method_id"],
        "message": message,
        "warning": warning,
        "estimated_rides_until_free": estimated,
        "methods": statuses,
    }
