from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import PaymentMethod

payment_methods_bp = Blueprint("payment_methods", __name__)
ALLOWED_PAYMENT_TYPES = {
    "visa",
    "mastercard",
    "amex",
    "discover",
    "omny",
    "apple_pay",
    "google_pay",
    "other",
}


def _serialize_payment_method(payment_method: PaymentMethod) -> dict:
    return {
        "id": payment_method.id,
        "label": payment_method.label,
        "payment_type": payment_method.payment_type,
        "cardholder_name": payment_method.cardholder_name,
        "last4": payment_method.last4,
        "masked_details": f"{payment_method.payment_type.replace('_', ' ').title()} ending in {payment_method.last4}",
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
    payment_type = (payload.get("payment_type") or "").strip().lower()
    cardholder_name = (payload.get("cardholder_name") or "").strip()
    last4 = (payload.get("last4") or "").strip()
    details_fingerprint = (payload.get("details_fingerprint") or "").strip().lower()

    if not label:
        return jsonify({"error": "Payment method name is required."}), 400
    if payment_type not in ALLOWED_PAYMENT_TYPES:
        return jsonify({"error": "A valid payment type is required."}), 400
    if not cardholder_name:
        return jsonify({"error": "Cardholder name is required."}), 400
    if len(last4) != 4 or not last4.isdigit():
        return jsonify({"error": "Only the last 4 digits may be stored."}), 400
    if len(details_fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in details_fingerprint
    ):
        return jsonify({"error": "A valid payment fingerprint is required."}), 400

    payment_method = PaymentMethod(
        user_id=user_id,
        label=label,
        payment_type=payment_type,
        cardholder_name=cardholder_name,
        last4=last4,
        details_fingerprint=details_fingerprint,
    )
    db.session.add(payment_method)
    db.session.commit()

    return jsonify(_serialize_payment_method(payment_method)), 201
