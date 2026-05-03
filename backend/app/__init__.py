import os

from dotenv import load_dotenv
from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt
from .routes.auth import auth_bp
from .routes.insights import insights_bp
from .routes.payment_methods import payment_methods_bp
from .routes.rides import rides_bp


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    allowed_origins = [
        origin.strip()
        for origin in str(app.config["CLIENT_ORIGIN"]).split(",")
        if origin.strip()
    ]

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": allowed_origins}},
        supports_credentials=False,
    )

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(payment_methods_bp, url_prefix="/api")
    app.register_blueprint(rides_bp, url_prefix="/api")
    app.register_blueprint(insights_bp, url_prefix="/api")

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok"})

    with app.app_context():
        db.create_all()

    return app
