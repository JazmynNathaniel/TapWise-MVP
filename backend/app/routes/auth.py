from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import TokenBlocklist, User

auth_bp = Blueprint("auth", __name__)
PASSWORD_SPECIAL_CHARACTERS = "!@#$%^&*_-"
PASSWORD_RULE_MESSAGE = (
    "Password must be at least 8 characters and include one capital letter, one number, one special "
    "character (!@#$%^&*_-), and no spaces."
)


def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "username": user.username}


def _normalize_username(raw_value: str) -> str:
    return (raw_value or "").strip().lower()


def _validate_password(password: str) -> str | None:
    if len(password) < 8:
        return PASSWORD_RULE_MESSAGE
    if any(character.isspace() for character in password):
        return PASSWORD_RULE_MESSAGE
    if not any(character.isupper() for character in password):
        return PASSWORD_RULE_MESSAGE
    if not any(character.isdigit() for character in password):
        return PASSWORD_RULE_MESSAGE
    if not any(character in PASSWORD_SPECIAL_CHARACTERS for character in password):
        return PASSWORD_RULE_MESSAGE
    return None


def _block_current_token() -> None:
    token_payload = get_jwt()
    jti = token_payload.get("jti")
    expires_at = token_payload.get("exp")
    if not jti or not expires_at:
        return

    expires_datetime = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    existing_token = TokenBlocklist.query.filter_by(jti=jti).first()
    if existing_token:
        return

    db.session.add(TokenBlocklist(jti=jti, expires_at=expires_datetime))


@auth_bp.post("/register")
def register():
    payload = request.get_json() or {}
    email = (payload.get("email") or "").strip().lower()
    username = _normalize_username(payload.get("username") or "")
    password = payload.get("password") or ""

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required."}), 400
    if len(username) < 3 or len(username) > 30:
        return jsonify({"error": "Username must be between 3 and 30 characters."}), 400
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in username):
        return jsonify({"error": "Username may contain only letters, numbers, and underscores."}), 400
    password_error = _validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "We couldn't create that account."}), 409
    existing_username = User.query.filter_by(username=username).first()
    if existing_username:
        return jsonify({"error": "We couldn't create that account."}), 409

    user = User(
        email=email,
        username=username,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    return jsonify({"token": access_token, "user": _serialize_user(user)}), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json() or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Incorrect login information."}), 401

    access_token = create_access_token(identity=str(user.id))
    return jsonify({"token": access_token, "user": _serialize_user(user)})


@auth_bp.post("/logout")
@jwt_required()
def logout():
    _block_current_token()
    db.session.commit()
    return jsonify({"message": "Logged out."})


@auth_bp.delete("/profile")
@jwt_required()
def delete_profile():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    _block_current_token()
    if user:
        db.session.delete(user)
    db.session.commit()

    return jsonify({"message": "Profile deleted."})
