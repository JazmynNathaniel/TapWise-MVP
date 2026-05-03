from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import PaymentMethod

payment_methods_bp = Blueprint("payment_methods", __name__)


def _serialize_payment_method(payment_method: PaymentMethod) -> dict:
    return {
        "id": payment_method.id,
        "label": payment_method.label,
        "created_at": payment_method.created_at.isoformat(),
    }


@payment_methods_bp.get("/payment-methods")
@payment_methods_bp.get("/payment_mthods")
@jwt_required()
def list_payment_methods():
    user_id = int(get_jwt_identity())
    methods = (
        PaymentMethod.query.filter_by(user_id=user_id)
        .order_by(PaymentMethod.created_at.asc())
        .all()
    )
    return jsonify([_serialize_payment_method(method) for method in methods])


@payment_methods_bp.post("/payment-methods")
@jwt_required()
def create_payment_method():
    user_id = int(get_jwt_identity())
    payload = request.get_json() or {}
    label = (payload.get("label") or "").strip()

    if not label:
        return jsonify({"error": "Label is required."}), 400

    payment_method = PaymentMethod(user_id=user_id, label=label)
    db.session.add(payment_method)
    db.session.commit()

    return jsonify(_serialize_payment_method(payment_method)), 201
