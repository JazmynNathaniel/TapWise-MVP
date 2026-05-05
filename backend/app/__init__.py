import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from sqlalchemy import inspect, text

from .config import Config
from .extensions import cors, db, jwt
from .routes.auth import auth_bp
from .routes.insights import insights_bp
from .routes.payment_methods import payment_methods_bp
from .routes.rides import rides_bp


def _ensure_payment_method_columns() -> None:
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns("payment_methods")}
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
    existing_columns = {column["name"] for column in inspector.get_columns("rides")}
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
    allowed_origins = {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(payment_methods_bp, url_prefix="/api")
    app.register_blueprint(rides_bp, url_prefix="/api")
    app.register_blueprint(insights_bp, url_prefix="/api")

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok"})

    @app.after_request
    def apply_cors_headers(response):
        if request.path.startswith("/api/"):
            origin = request.headers.get("Origin")
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
        _ensure_payment_method_columns()
        _ensure_ride_columns()

    return app
