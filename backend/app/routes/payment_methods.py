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
    identifier_code = payment_method.identifier_code
    return {
        "id": payment_method.id,
        "label": payment_method.label,
        "payment_type": payment_method.payment_type,
        "identifier_code": identifier_code,
        "masked_details": f"{payment_method.payment_type.replace('_', ' ').title()} code {identifier_code}",
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
    identifier_code = (payload.get("identifier_code") or "").strip()

    if not label:
        return jsonify({"error": "Please enter a payment method name."}), 400
    if payment_type not in ALLOWED_PAYMENT_TYPES:
        return jsonify({"error": "Please choose a payment type."}), 400
    if len(identifier_code) != 4 or not identifier_code.isdigit():
        return jsonify({"error": "Please enter a 4-digit code."}), 400

    payment_method = PaymentMethod(
        user_id=user_id,
        label=label,
        payment_type=payment_type,
        cardholder_name="",
        identifier_code=identifier_code,
    )
    db.session.add(payment_method)
    db.session.commit()

    return jsonify(_serialize_payment_method(payment_method)), 201
