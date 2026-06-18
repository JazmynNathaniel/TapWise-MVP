import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import PasswordResetToken, TokenBlocklist, User

auth_bp = Blueprint("auth", __name__)
PASSWORD_SPECIAL_CHARACTERS = "!@#$%^&*_-"
PASSWORD_RULE_MESSAGE = (
    "Password must be at least 8 characters and include one capital letter, one number, one special "
    "character (!@#$%^&*_-), and no spaces."
)
PASSWORD_RESET_MESSAGE = (
    "If that username has a recovery email, TapWise will send password reset instructions."
)
PASSWORD_RESET_WINDOW_MINUTES = 30


def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "username": user.username}


def _normalize_username(raw_value: str) -> str:
    return (raw_value or "").strip().lower()


def _normalize_email(raw_value: str | None) -> str | None:
    email = (raw_value or "").strip().lower()
    return email or None


def _validate_username(username: str) -> str | None:
    if len(username) < 3 or len(username) > 30:
        return "Username must be between 3 and 30 characters."
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in username):
        return "Username may contain only letters, numbers, and underscores."
    return None


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


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_origin() -> str:
    origin = (current_app.config.get("CLIENT_ORIGIN") or "").split(",", 1)[0].strip()
    return origin.rstrip("/") or request.host_url.rstrip("/")


def _password_reset_url(token: str, username: str) -> str:
    return f"{_client_origin()}/?{urlencode({'reset_token': token, 'username': username})}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _send_password_reset_email(email: str, reset_url: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip()
    if not smtp_host or not smtp_from:
        return False

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    use_tls = os.getenv("SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no"}

    message = EmailMessage()
    message["Subject"] = "Reset your TapWise password"
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(
        "TapWise received a password reset request for this username.\n\n"
        f"Reset your password here: {reset_url}\n\n"
        "This link expires in 30 minutes. If you did not request this, you can ignore this email."
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if smtp_username or smtp_password:
                smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except Exception as error:
        current_app.logger.warning("Password reset email failed: %s", error)
        return False

    return True


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
    email = _normalize_email(payload.get("email"))
    username = _normalize_username(payload.get("username") or "")
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    username_error = _validate_username(username)
    if username_error:
        return jsonify({"error": username_error}), 400
    password_error = _validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "We couldn't create that account."}), 409
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "We couldn't create that account."}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        email=email,
    )
    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    return jsonify({"token": access_token, "user": _serialize_user(user)}), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json() or {}
    username = _normalize_username(payload.get("username") or "")
    password = payload.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Incorrect login information."}), 401

    access_token = create_access_token(identity=str(user.id))
    return jsonify({"token": access_token, "user": _serialize_user(user)})


@auth_bp.post("/password-reset/request")
def request_password_reset():
    payload = request.get_json() or {}
    username = _normalize_username(payload.get("username") or "")
    user = User.query.filter_by(username=username).first() if username else None

    if user and user.email:
        raw_token = secrets.token_urlsafe(32)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=_token_hash(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=PASSWORD_RESET_WINDOW_MINUTES),
        )
        db.session.add(reset_token)
        db.session.commit()
        _send_password_reset_email(user.email, _password_reset_url(raw_token, username))

    return jsonify({"message": PASSWORD_RESET_MESSAGE})


@auth_bp.post("/password-reset/confirm")
def confirm_password_reset():
    payload = request.get_json() or {}
    username = _normalize_username(payload.get("username") or "")
    token = (payload.get("token") or "").strip()
    password = payload.get("password") or ""

    password_error = _validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    user = User.query.filter_by(username=username).first() if username else None
    reset_token = (
        PasswordResetToken.query.filter_by(token_hash=_token_hash(token)).first()
        if token
        else None
    )
    now = datetime.now(timezone.utc)

    if (
        not user
        or not reset_token
        or reset_token.user_id != user.id
        or reset_token.used_at is not None
        or _as_utc(reset_token.expires_at) <= now
    ):
        return jsonify({"error": "That password reset link is invalid or expired."}), 400

    user.password_hash = generate_password_hash(password)
    reset_token.used_at = now
    db.session.commit()

    return jsonify({"message": "Your TapWise password has been reset."})


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
