from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.models import Assignment, Driver
from app.utils import driver_out, haversine_km


def rank_drivers(db: Session, delivery):
    """Score online drivers for a delivery (lower score = better). Used by the
    /dispatch/recommend endpoint and by the Dispatch Agent."""
    candidates = []
    for driver in db.query(Driver).filter(Driver.status == "online").all():
        active_count = db.query(func.count(Assignment.id)).filter(
            Assignment.driver_id == driver.id,
            Assignment.status.in_(["assigned", "accepted"])
        ).scalar()
        distance = haversine_km(driver.current_latitude, driver.current_longitude, delivery.pickup_latitude, delivery.pickup_longitude)
        score = distance + active_count * 3 + (0 if driver.vehicle_type.lower() in {"bike", "van"} else 2)
        candidates.append({
            "driver": driver_out(driver),
            "distance_km": round(distance, 2),
            "active_deliveries": active_count,
            "dispatch_score": round(score, 2)
        })
    return sorted(candidates, key=lambda x: x["dispatch_score"])
