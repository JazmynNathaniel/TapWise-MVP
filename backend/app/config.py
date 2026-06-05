import os
from datetime import timedelta


def _database_uri() -> str:
    uri = os.getenv("DATABASE_URL", "sqlite:///tapwise_dev.db")

    if uri.startswith("postgres://"):
        uri = f"postgresql://{uri.removeprefix('postgres://')}"
    if uri.startswith("postgresql://"):
        return f"postgresql+psycopg://{uri.removeprefix('postgresql://')}"

    return uri


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _app_environment() -> str:
    if _env_flag("RENDER"):
        return "production"
    return os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).strip().lower()


def _required_secret(name: str, default: str) -> str:
    value = os.getenv(name, default)
    is_production = _app_environment() in {"prod", "production"}
    if is_production and value == default:
        raise RuntimeError(f"{name} must be set in production.")
    return value


class Config:
    APP_ENV = _app_environment()
    SECRET_KEY = _required_secret("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = _required_secret("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CLIENT_ORIGIN = os.getenv(
        "CLIENT_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173"
    )
