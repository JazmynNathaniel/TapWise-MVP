import os
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from sqlalchemy import inspect, text
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import cors, db, jwt
from .models import User
from .routes.auth import auth_bp
from .routes.insights import insights_bp
from .routes.payment_methods import payment_methods_bp
from .routes.rides import rides_bp
from .routes.transit import transit_bp


API_ERROR_MESSAGES = {
    400: "Please check your information and try again.",
    401: "Please sign in again.",
    403: "You do not have access to that action.",
    404: "We couldn't find that information.",
    405: "That action isn't available right now.",
    409: "That information is already in use.",
    429: "Please wait a moment and try again.",
}


def _safe_api_error(status_code: int):
    return (
        jsonify(
            {
                "error": API_ERROR_MESSAGES.get(
                    status_code,
                    "Something went wrong on our side. Please try again in a moment.",
                )
            }
        ),
        status_code,
    )


def _parse_allowed_origins(raw_value: str | None) -> set[str]:
    return {
        origin.strip().rstrip("/")
        for origin in (raw_value or "").split(",")
        if origin.strip()
    }


def _generate_unique_username(email: str, existing_usernames: set[str]) -> str:
    local_part = email.split("@", 1)[0].strip().lower()
    base = re.sub(r"[^a-z0-9_]+", "_",
                  local_part).strip("_")[:24] or "tapwise_user"
    candidate = base
    suffix = 2

    while candidate in existing_usernames:
        candidate = f"{base[:24]}_{suffix}"[:30]
        suffix += 1

    existing_usernames.add(candidate)
    return candidate


def _ensure_user_columns() -> None:
    inspector = inspect(db.engine)
    existing_columns = {column["name"]
                        for column in inspector.get_columns("users")}
    statements = []

    if "username" not in existing_columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN username VARCHAR(40) NOT NULL DEFAULT ''"
        )

    for statement in statements:
        db.session.execute(text(statement))
    if statements:
        db.session.commit()

    if "username" not in existing_columns:
        users = User.query.order_by(User.id.asc()).all()
        existing_usernames = {
            user.username.strip().lower() for user in users if user.username.strip()
        }
        updated = False

        for user in users:
            if user.username.strip():
                continue
            user.username = _generate_unique_username(
                user.email, existing_usernames)
            updated = True

        if updated:
            db.session.commit()


def _ensure_payment_method_columns() -> None:
    inspector = inspect(db.engine)
    existing_columns = {column["name"]
                        for column in inspector.get_columns("payment_methods")}
    statements = []

    if "payment_type" not in existing_columns:
        statements.append(
            "ALTER TABLE payment_methods ADD COLUMN payment_type VARCHAR(40) NOT NULL DEFAULT 'other'"
        )
    if "cardholder_name" not in existing_columns:
        statements.append(
            "ALTER TABLE payment_methods ADD COLUMN cardholder_name VARCHAR(120) NOT NULL DEFAULT ''"
        )
    if "last4" not in existing_columns:
        statements.append(
            "ALTER TABLE payment_methods ADD COLUMN last4 VARCHAR(4) NOT NULL DEFAULT '0000'"
        )
    if "identifier_code" not in existing_columns:
        statements.append(
            "ALTER TABLE payment_methods ADD COLUMN identifier_code VARCHAR(4) NOT NULL DEFAULT '0000'"
        )
    if "details_fingerprint" not in existing_columns:
        statements.append(
            "ALTER TABLE payment_methods ADD COLUMN details_fingerprint VARCHAR(64) NOT NULL DEFAULT ''"
        )

    for statement in statements:
        db.session.execute(text(statement))
    if statements:
        db.session.commit()

    if "identifier_code" not in existing_columns and "last4" in existing_columns:
        db.session.execute(
            text(
                "UPDATE payment_methods SET identifier_code = last4 "
                "WHERE (identifier_code = '0000' OR identifier_code = '') "
                "AND last4 <> ''"
            )
        )
        db.session.commit()


def _ensure_ride_columns() -> None:
    inspector = inspect(db.engine)
    existing_columns = {column["name"]
                        for column in inspector.get_columns("rides")}
    statements = []

    if "transit_mode" not in existing_columns:
        statements.append(
            "ALTER TABLE rides ADD COLUMN transit_mode VARCHAR(20) NOT NULL DEFAULT 'subway'"
        )
    if "transit_line" not in existing_columns:
        statements.append(
            "ALTER TABLE rides ADD COLUMN transit_line VARCHAR(40) NOT NULL DEFAULT ''"
        )
    if "entry_stop" not in existing_columns:
        statements.append(
            "ALTER TABLE rides ADD COLUMN entry_stop VARCHAR(120) NOT NULL DEFAULT ''"
        )
    if "exit_stop" not in existing_columns:
        statements.append(
            "ALTER TABLE rides ADD COLUMN exit_stop VARCHAR(120) NOT NULL DEFAULT ''"
        )

    for statement in statements:
        db.session.execute(text(statement))
    if statements:
        db.session.commit()


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    allowed_origins = _parse_allowed_origins(app.config.get("CLIENT_ORIGIN"))

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app)

    @jwt.unauthorized_loader
    def handle_missing_token(_reason):
        return _safe_api_error(401)

    @jwt.invalid_token_loader
    def handle_invalid_token(_reason):
        return _safe_api_error(401)

    @jwt.expired_token_loader
    def handle_expired_token(_jwt_header, _jwt_payload):
        return _safe_api_error(401)

    @jwt.revoked_token_loader
    def handle_revoked_token(_jwt_header, _jwt_payload):
        return _safe_api_error(401)

    @jwt.needs_fresh_token_loader
    def handle_stale_token(_jwt_header, _jwt_payload):
        return _safe_api_error(401)

    @jwt.token_verification_failed_loader
    def handle_failed_token_verification(_jwt_header, _jwt_payload):
        return _safe_api_error(401)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(payment_methods_bp, url_prefix="/api")
    app.register_blueprint(rides_bp, url_prefix="/api")
    app.register_blueprint(insights_bp, url_prefix="/api")
    app.register_blueprint(transit_bp, url_prefix="/api")

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok"})

    @app.get("/")
    def root_health_check():
        return jsonify({"service": "tapwise-api", "status": "ok"})

    @app.errorhandler(Exception)
    def handle_api_exception(error):
        if isinstance(error, HTTPException):
            status_code = error.code or 500
            return _safe_api_error(status_code)

        db.session.rollback()
        return _safe_api_error(500)

    @app.after_request
    def apply_cors_headers(response):
        if request.path.startswith("/api/"):
            origin = (request.headers.get("Origin") or "").rstrip("/")
            if origin in allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
                response.headers["Access-Control-Allow-Headers"] = (
                    "Content-Type, Authorization"
                )
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    with app.app_context():
        db.create_all()
        _ensure_user_columns()
        _ensure_payment_method_columns()
        _ensure_ride_columns()

    return app
