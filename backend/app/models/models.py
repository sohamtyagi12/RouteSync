from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30), default="customer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    driver: Mapped["Driver | None"] = relationship(back_populates="user", uselist=False)
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="customer")

class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    vehicle_type: Mapped[str] = mapped_column(String(40))
    vehicle_number: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="offline")
    current_latitude: Mapped[float] = mapped_column(Float, default=19.076)
    current_longitude: Mapped[float] = mapped_column(Float, default=72.8777)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="driver")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="driver")

class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pickup_address: Mapped[str] = mapped_column(String(255))
    pickup_latitude: Mapped[float] = mapped_column(Float)
    pickup_longitude: Mapped[float] = mapped_column(Float)
    dropoff_address: Mapped[str] = mapped_column(String(255))
    dropoff_latitude: Mapped[float] = mapped_column(Float)
    dropoff_longitude: Mapped[float] = mapped_column(Float)
    package_description: Mapped[str] = mapped_column(String(255))
    package_weight: Mapped[float] = mapped_column(Float, default=1)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped[User] = relationship(back_populates="deliveries")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="delivery")
    events: Mapped[list["DeliveryEvent"]] = relationship(back_populates="delivery", cascade="all, delete-orphan")

class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"))
    status: Mapped[str] = mapped_column(String(30), default="assigned")
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    driver: Mapped[Driver] = relationship(back_populates="assignments")
    delivery: Mapped[Delivery] = relationship(back_populates="assignments")

class DeliveryEvent(Base):
    __tablename__ = "delivery_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"))
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    delivery: Mapped[Delivery] = relationship(back_populates="events")
