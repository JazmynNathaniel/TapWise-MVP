import os


def _database_uri() -> str:
    uri = os.getenv("DATABASE_URL", "sqlite:///tapwise_dev.db")

    if uri.startswith("postgres://"):
        uri = f"postgresql://{uri.removeprefix('postgres://')}"
    if uri.startswith("postgresql://"):
        return f"postgresql+psycopg://{uri.removeprefix('postgresql://')}"

    return uri


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CLIENT_ORIGIN = os.getenv(
        "CLIENT_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173"
    )
