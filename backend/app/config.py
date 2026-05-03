import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///tapwise_dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CLIENT_ORIGIN = os.getenv(
        "CLIENT_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173"
    )
