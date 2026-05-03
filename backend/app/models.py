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
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", back_populates="rides")
    payment_method = db.relationship("PaymentMethod", back_populates="rides")
