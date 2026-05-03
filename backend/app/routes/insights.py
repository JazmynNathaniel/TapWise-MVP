from datetime import datetime, timezone

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..models import PaymentMethod
from ..services.fare_engine import calculate_fare_status
from ..services.recommendations import build_recommendation

insights_bp = Blueprint("insights", __name__)


@insights_bp.get("/fare-status/<int:payment_method_id>")
@insights_bp.get("/fare-status/<string:payment_method_id>")
@jwt_required()
def fare_status(payment_method_id):
    user_id = int(get_jwt_identity())
    try:
        method_id = int(payment_method_id)
    except ValueError:
        return jsonify({"error": "Invalid payment method id."}), 400

    payment_method = PaymentMethod.query.filter_by(id=method_id, user_id=user_id).first()
    if not payment_method:
        return jsonify({"error": "Payment method not found."}), 404

    status = calculate_fare_status(
        [ride.timestamp for ride in payment_method.rides],
        now=datetime.now(timezone.utc),
    )
    return jsonify(
        {
            "payment_method_id": payment_method.id,
            "label": payment_method.label,
            **status.to_dict(),
        }
    )


@insights_bp.get("/recommendation")
@insights_bp.get("/recomendation")
@jwt_required()
def recommendation():
    user_id = int(get_jwt_identity())
    payment_methods = (
        PaymentMethod.query.filter_by(user_id=user_id)
        .order_by(PaymentMethod.created_at.asc())
        .all()
    )
    return jsonify(build_recommendation(payment_methods))
