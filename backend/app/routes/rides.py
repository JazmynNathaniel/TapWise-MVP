from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import PaymentMethod, Ride
from ..services.fare_engine import ensure_utc
from ..services.transit_data import get_transit_options, is_valid_transit_selection

rides_bp = Blueprint("rides", __name__)


def _parse_timestamp(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    return ensure_utc(parsed)


def _serialize_ride(ride: Ride) -> dict:
    return {
        "id": ride.id,
        "payment_method_id": ride.payment_method_id,
        "payment_method_label": ride.payment_method.label,
        "transit_mode": ride.transit_mode,
        "transit_line": ride.transit_line,
        "entry_stop": ride.entry_stop,
        "exit_stop": ride.exit_stop,
        "timestamp": ride.timestamp.isoformat(),
        "created_at": ride.created_at.isoformat(),
    }


@rides_bp.get("/transit-options")
@jwt_required()
def transit_options():
    return jsonify(get_transit_options())


@rides_bp.get("/rides")
@jwt_required()
def list_rides():
    user_id = int(get_jwt_identity())
    rides = (
        Ride.query.filter_by(user_id=user_id)
        .order_by(Ride.timestamp.desc())
        .all()
    )
    return jsonify([_serialize_ride(ride) for ride in rides])


@rides_bp.post("/rides")
@jwt_required()
def create_ride():
    user_id = int(get_jwt_identity())
    payload = request.get_json() or {}
    payment_method_id = payload.get("payment_method_id")
    transit_mode = (payload.get("transit_mode") or "").strip().lower()
    transit_line = (payload.get("transit_line") or "").strip()
    entry_stop = (payload.get("entry_stop") or "").strip()
    exit_stop = (payload.get("exit_stop") or "").strip()

    if not payment_method_id:
        return jsonify({"error": "payment_method_id is required."}), 400
    if not is_valid_transit_selection(transit_mode, transit_line, entry_stop, exit_stop):
        return jsonify({"error": "A valid line and stop selection is required."}), 400

    payment_method = PaymentMethod.query.filter_by(
        id=payment_method_id, user_id=user_id
    ).first()
    if not payment_method:
        return jsonify({"error": "Payment method not found."}), 404

    ride = Ride(
        user_id=user_id,
        payment_method_id=payment_method.id,
        transit_mode=transit_mode,
        transit_line=transit_line,
        entry_stop=entry_stop,
        exit_stop=exit_stop,
        timestamp=_parse_timestamp(payload.get("timestamp")),
    )
    db.session.add(ride)
    db.session.commit()

    return jsonify(_serialize_ride(ride)), 201
