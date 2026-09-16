from datetime import datetime
import os
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.auth import create_token, get_current_user, require_roles, verify_password
from app.database import Base, engine, get_db
from app.models.models import Assignment, Delivery, DeliveryEvent, Driver, User
from app.schemas.schemas import AssignmentAction, AssignmentCreate, DeliveryCreate, DeliveryOut, DriverOut, LocationUpdate, LoginRequest, RouteOptimizeRequest, RouteOptimizeOut, RouteStopOut, Token, UserOut
from app.utils import haversine_km, optimize_stops

Base.metadata.create_all(bind=engine)

app = FastAPI(title="RouteSync API", version="2.0.0", description="Delivery operations and route management API")

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins = [x.strip() for x in frontend_url.split(",") if x.strip()]
origins.extend(["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
def root():
    return {"name": "RouteSync API", "version": "2.0.0", "status": "online"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/auth/login", response_model=Token)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_token(user), "token_type": "bearer"}

@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

@app.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return db.query(User).order_by(User.id).all()

def driver_out(driver):
    return {
        "id": driver.id,
        "user_id": driver.user_id,
        "name": driver.user.name,
        "email": driver.user.email,
        "vehicle_type": driver.vehicle_type,
        "vehicle_number": driver.vehicle_number,
        "status": driver.status,
        "current_latitude": driver.current_latitude,
        "current_longitude": driver.current_longitude,
        "updated_at": driver.updated_at
    }

@app.get("/drivers", response_model=list[DriverOut])
def drivers(search: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Driver).join(User)
    if search:
        term = f"%{search}%"
        query = query.filter((User.name.ilike(term)) | (Driver.vehicle_number.ilike(term)) | (Driver.status.ilike(term)))
    return [driver_out(d) for d in query.order_by(Driver.id).all()]

@app.patch("/drivers/{driver_id}/location")
def update_location(driver_id: int, data: LocationUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "driver"))):
    driver = db.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    if user.role == "driver" and driver.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only update your own location")
    driver.current_latitude = data.latitude
    driver.current_longitude = data.longitude
    if data.status:
        driver.status = data.status
    driver.updated_at = datetime.utcnow()
    db.commit()
    return driver_out(driver)

@app.get("/deliveries", response_model=list[DeliveryOut])
def deliveries(search: str | None = None, status: str | None = None, priority: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Delivery)
    if user.role == "customer":
        query = query.filter(Delivery.customer_id == user.id)
    if search:
        term = f"%{search}%"
        query = query.filter((Delivery.pickup_address.ilike(term)) | (Delivery.dropoff_address.ilike(term)) | (Delivery.package_description.ilike(term)))
    if status:
        query = query.filter(Delivery.status == status)
    if priority:
        query = query.filter(Delivery.priority == priority)
    return query.order_by(Delivery.created_at.desc()).all()

@app.post("/deliveries", response_model=DeliveryOut)
def create_delivery(data: DeliveryCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "customer"))):
    customer_id = user.id
    if user.role == "admin":
        customer = db.query(User).filter(User.role == "customer", User.active.is_(True)).order_by(User.id).first()
        if not customer:
            raise HTTPException(status_code=400, detail="No active customer account available")
        customer_id = customer.id
    item = Delivery(customer_id=customer_id, **data.model_dump())
    db.add(item)
    db.flush()
    db.add(DeliveryEvent(delivery_id=item.id, status="pending", note="Delivery request created"))
    db.commit()
    db.refresh(item)
    return item

@app.get("/deliveries/{delivery_id}")
def delivery_detail(delivery_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if user.role == "customer" and delivery.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    assignment = db.query(Assignment).filter(Assignment.delivery_id == delivery.id).order_by(Assignment.id.desc()).first()
    driver = assignment.driver if assignment else None
    return {
        "delivery": DeliveryOut.model_validate(delivery),
        "driver": driver_out(driver) if driver else None,
        "assignment": {
            "id": assignment.id,
            "status": assignment.status,
            "assigned_at": assignment.assigned_at,
            "accepted_at": assignment.accepted_at,
            "completed_at": assignment.completed_at
        } if assignment else None,
        "events": [
            {"id": e.id, "status": e.status, "note": e.note, "created_at": e.created_at}
            for e in sorted(delivery.events, key=lambda x: x.created_at)
        ]
    }

@app.patch("/deliveries/{delivery_id}/status", response_model=DeliveryOut)
def update_delivery_status(delivery_id: int, data: AssignmentAction, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "driver"))):
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if user.role == "driver":
        driver = db.query(Driver).filter(Driver.user_id == user.id).first()
        active_assignment = db.query(Assignment).filter(
            Assignment.delivery_id == delivery.id,
            Assignment.driver_id == (driver.id if driver else -1),
            Assignment.status.in_(["assigned", "accepted"])
        ).first()
        if not active_assignment:
            raise HTTPException(status_code=403, detail="Delivery is not assigned to you")

    allowed = {
        "pending": {"assigned"},
        "assigned": {"accepted", "pending"},
        "accepted": {"pickup_started"},
        "pickup_started": {"picked_up"},
        "picked_up": {"in_transit"},
        "in_transit": {"delivered"},
    }
    new_status = data.action
    if new_status not in allowed.get(delivery.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid transition from {delivery.status} to {new_status}")
    delivery.status = new_status
    db.add(DeliveryEvent(delivery_id=delivery.id, status=new_status, note=f"Status changed to {new_status}"))
    if new_status == "delivered":
        assignment = db.query(Assignment).filter(Assignment.delivery_id == delivery.id).order_by(Assignment.id.desc()).first()
        if assignment:
            assignment.status = "completed"
            assignment.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(delivery)
    return delivery

@app.get("/assignments")
def assignments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Assignment).join(Driver).join(User, Driver.user_id == User.id)
    if user.role == "driver":
        query = query.filter(Driver.user_id == user.id)
    items = query.order_by(Assignment.assigned_at.desc()).all()
    return [
        {
            "id": a.id,
            "driver_id": a.driver_id,
            "driver_name": a.driver.user.name,
            "vehicle_number": a.driver.vehicle_number,
            "delivery_id": a.delivery_id,
            "pickup": a.delivery.pickup_address,
            "dropoff": a.delivery.dropoff_address,
            "delivery_status": a.delivery.status,
            "status": a.status,
            "assigned_at": a.assigned_at,
            "accepted_at": a.accepted_at,
            "completed_at": a.completed_at
        } for a in items
    ]

@app.post("/assignments")
def create_assignment(data: AssignmentCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    driver = db.get(Driver, data.driver_id)
    delivery = db.get(Delivery, data.delivery_id)
    if not driver or not delivery:
        raise HTTPException(status_code=404, detail="Driver or delivery not found")
    if driver.status != "online":
        raise HTTPException(status_code=400, detail="Driver is not online")
    existing = db.query(Assignment).filter(Assignment.delivery_id == delivery.id, Assignment.status.in_(["assigned", "accepted"])).first()
    if existing:
        raise HTTPException(status_code=400, detail="Delivery already has an active assignment")
    assignment = Assignment(driver_id=driver.id, delivery_id=delivery.id, status="assigned")
    delivery.status = "assigned"
    db.add(assignment)
    db.add(DeliveryEvent(delivery_id=delivery.id, status="assigned", note=f"Assigned to {driver.user.name}"))
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id, "status": assignment.status, "driver_id": assignment.driver_id, "delivery_id": assignment.delivery_id}

@app.patch("/assignments/{assignment_id}/action")
def assignment_action(assignment_id: int, data: AssignmentAction, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if user.role == "driver" and assignment.driver.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if data.action == "accept":
        assignment.status = "accepted"
        assignment.accepted_at = datetime.utcnow()
        assignment.delivery.status = "accepted"
        db.add(DeliveryEvent(delivery_id=assignment.delivery_id, status="accepted", note=f"{assignment.driver.user.name} accepted the delivery"))
    elif data.action == "reject":
        assignment.status = "rejected"
        assignment.rejected_at = datetime.utcnow()
        assignment.delivery.status = "pending"
        db.add(DeliveryEvent(delivery_id=assignment.delivery_id, status="pending", note="Driver rejected the assignment"))
    elif data.action == "complete":
        assignment.status = "completed"
        assignment.completed_at = datetime.utcnow()
        assignment.delivery.status = "delivered"
        db.add(DeliveryEvent(delivery_id=assignment.delivery_id, status="delivered", note="Delivery completed"))
    else:
        raise HTTPException(status_code=400, detail="Action must be accept, reject, or complete")
    db.commit()
    return {"message": f"Assignment {data.action}ed", "status": assignment.status}

@app.get("/dispatch/recommend/{delivery_id}")
def recommend_driver(delivery_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    drivers = db.query(Driver).filter(Driver.status == "online").all()
    candidates = []
    for driver in drivers:
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

@app.post("/routes/optimize", response_model=RouteOptimizeOut)
def optimize_route(data: RouteOptimizeRequest, user: User = Depends(get_current_user)):
    stops = [s.model_dump() for s in data.stops]
    ordered = optimize_stops(stops)
    total = sum(
        haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        for a, b in zip(ordered, ordered[1:])
    )
    return {
        "stops": [RouteStopOut(sequence=i + 1, **stop) for i, stop in enumerate(ordered)],
        "total_distance_km": round(total, 2),
        "estimated_minutes": round((total / 28) * 60)
    }

@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    delivery_query = db.query(Delivery)
    if user.role == "customer":
        delivery_query = delivery_query.filter(Delivery.customer_id == user.id)
    total_deliveries = delivery_query.count()
    counts = {
        "pending": delivery_query.filter(Delivery.status == "pending").count(),
        "assigned": delivery_query.filter(Delivery.status == "assigned").count(),
        "accepted": delivery_query.filter(Delivery.status == "accepted").count(),
        "pickup_started": delivery_query.filter(Delivery.status == "pickup_started").count(),
        "picked_up": delivery_query.filter(Delivery.status == "picked_up").count(),
        "in_transit": delivery_query.filter(Delivery.status == "in_transit").count(),
        "delivered": delivery_query.filter(Delivery.status == "delivered").count(),
    }
    return {
        "total_drivers": db.query(Driver).count(),
        "online_drivers": db.query(Driver).filter(Driver.status == "online").count(),
        "total_deliveries": total_deliveries,
        "active_deliveries": total_deliveries - counts["delivered"],
        "completed_deliveries": counts["delivered"],
        "assignments": db.query(Assignment).count(),
        "statuses": counts
    }
