from app.database import Base, SessionLocal, engine
from app.auth import hash_password
from app.models.models import Assignment, Delivery, DeliveryEvent, Driver, User

Base.metadata.create_all(bind=engine)
db = SessionLocal()

def user(email, name, role, password):
    item = db.query(User).filter(User.email == email).first()

    if not item:
        item = User(
            name=name,
            email=email,
            role=role,
            password_hash=hash_password(password)
        )
        db.add(item)
        db.flush()
    else:
        item.name = name
        item.role = role
        item.password_hash = hash_password(password)

    return item

admin = user("admin@routesync.com", "RouteSync Admin", "admin", "Admin@123")
driver_user = user("driver@routesync.com", "Aarav Sharma", "driver", "Driver@123")
customer = user("customer@routesync.com", "Riya Mehta", "customer", "Customer@123")

driver = db.query(Driver).filter(Driver.user_id == driver_user.id).first()
if not driver:
    driver = Driver(
        user_id=driver_user.id,
        vehicle_type="Bike",
        vehicle_number="MH01AB1234",
        status="online",
        current_latitude=19.1197,
        current_longitude=72.8468
    )
    db.add(driver)
    db.flush()

if db.query(Delivery).count() == 0:
    deliveries = [
        Delivery(
            customer_id=customer.id,
            pickup_address="Andheri East, Mumbai",
            pickup_latitude=19.1197,
            pickup_longitude=72.8468,
            dropoff_address="Bandra West, Mumbai",
            dropoff_latitude=19.0607,
            dropoff_longitude=72.8362,
            package_description="Electronics Package",
            package_weight=2.5,
            priority="high",
            status="assigned"
        ),
        Delivery(
            customer_id=customer.id,
            pickup_address="Powai, Mumbai",
            pickup_latitude=19.1176,
            pickup_longitude=72.9060,
            dropoff_address="Thane West",
            dropoff_latitude=19.2183,
            dropoff_longitude=72.9781,
            package_description="Documents",
            package_weight=0.5,
            priority="normal",
            status="pending"
        ),
        Delivery(
            customer_id=customer.id,
            pickup_address="Lower Parel, Mumbai",
            pickup_latitude=18.9988,
            pickup_longitude=72.8258,
            dropoff_address="Colaba, Mumbai",
            dropoff_latitude=18.9067,
            dropoff_longitude=72.8147,
            package_description="Medical Supplies",
            package_weight=4,
            priority="urgent",
            status="in_transit"
        )
    ]
    db.add_all(deliveries)
    db.flush()
    assignment = Assignment(driver_id=driver.id, delivery_id=deliveries[0].id, status="assigned")
    db.add(assignment)
    db.add(DeliveryEvent(delivery_id=deliveries[0].id, status="pending", note="Delivery request created"))
    db.add(DeliveryEvent(delivery_id=deliveries[0].id, status="assigned", note="Dispatcher assigned a driver"))
    db.add(DeliveryEvent(delivery_id=deliveries[2].id, status="in_transit", note="Package is on the way"))

db.commit()
db.close()
print("RouteSync seed complete")
