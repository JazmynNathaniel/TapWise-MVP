from datetime import datetime, timezone

from .extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(40), nullable=False, default="")
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    payment_methods = db.relationship(
        "PaymentMethod", back_populates="user", cascade="all, delete-orphan"
    )
    rides = db.relationship(
        "Ride", back_populates="user", cascade="all, delete-orphan"
    )
    route_notification_preferences = db.relationship(
        "RouteNotificationPreference",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __init__(self, email: str, username: str, password_hash: str) -> None:
        self.email = email
        self.username = username
        self.password_hash = password_hash


class PaymentMethod(db.Model):
    __tablename__ = "payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)
    payment_type = db.Column(db.String(40), nullable=False, default="other")
    cardholder_name = db.Column(db.String(120), nullable=False, default="")
    identifier_code = db.Column(db.String(4), nullable=False, default="0000")
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", back_populates="payment_methods")
    rides = db.relationship(
        "Ride",
        back_populates="payment_method",
        cascade="all, delete-orphan",
        order_by="Ride.timestamp.asc()",
    )

    def __init__(
        self,
        user_id: int,
        label: str,
        payment_type: str = "other",
        cardholder_name: str = "",
        identifier_code: str = "0000",
    ) -> None:
        self.user_id = user_id
        self.label = label
        self.payment_type = payment_type
        self.cardholder_name = cardholder_name
        self.identifier_code = identifier_code


class Ride(db.Model):
    __tablename__ = "rides"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    payment_method_id = db.Column(
        db.Integer, db.ForeignKey("payment_methods.id"), nullable=False, index=True
    )
    transit_mode = db.Column(db.String(20), nullable=False, default="subway")
    transit_line = db.Column(db.String(40), nullable=False, default="")
    entry_stop = db.Column(db.String(120), nullable=False, default="")
    exit_stop = db.Column(db.String(120), nullable=False, default="")
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", back_populates="rides")
    payment_method = db.relationship("PaymentMethod", back_populates="rides")

    def __init__(
        self,
        user_id: int,
        payment_method_id: int,
        transit_mode: str,
        transit_line: str,
        entry_stop: str,
        exit_stop: str,
        timestamp: datetime,
    ) -> None:
        self.user_id = user_id
        self.payment_method_id = payment_method_id
        self.transit_mode = transit_mode
        self.transit_line = transit_line
        self.entry_stop = entry_stop
        self.exit_stop = exit_stop
        self.timestamp = timestamp


class RouteNotificationPreference(db.Model):
    __tablename__ = "route_notification_preferences"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "transit_mode",
            "transit_line",
            "entry_stop",
            name="uq_route_notification_preference",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    transit_mode = db.Column(db.String(20), nullable=False)
    transit_line = db.Column(db.String(40), nullable=False)
    entry_stop = db.Column(db.String(120), nullable=False, default="")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", back_populates="route_notification_preferences")

    def __init__(
        self,
        user_id: int,
        transit_mode: str,
        transit_line: str,
        entry_stop: str = "",
        enabled: bool = True,
    ) -> None:
        self.user_id = user_id
        self.transit_mode = transit_mode
        self.transit_line = transit_line
        self.entry_stop = entry_stop
        self.enabled = enabled


class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __init__(self, jti: str, expires_at: datetime) -> None:
        self.jti = jti
        self.expires_at = expires_at
