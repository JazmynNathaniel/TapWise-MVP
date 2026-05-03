from datetime import datetime, timezone

from .extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
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


class PaymentMethod(db.Model):
    __tablename__ = "payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)
    payment_type = db.Column(db.String(40), nullable=False, default="other")
    cardholder_name = db.Column(db.String(120), nullable=False, default="")
    last4 = db.Column(db.String(4), nullable=False, default="0000")
    details_fingerprint = db.Column(db.String(64), nullable=False, default="")
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
