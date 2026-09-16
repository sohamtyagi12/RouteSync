from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: str
    active: bool

class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    email: str
    vehicle_type: str
    vehicle_number: str
    status: str
    current_latitude: float
    current_longitude: float
    updated_at: datetime

class DeliveryCreate(BaseModel):
    pickup_address: str
    pickup_latitude: float
    pickup_longitude: float
    dropoff_address: str
    dropoff_latitude: float
    dropoff_longitude: float
    package_description: str
    package_weight: float = 1
    priority: str = "normal"

class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    pickup_address: str
    pickup_latitude: float
    pickup_longitude: float
    dropoff_address: str
    dropoff_latitude: float
    dropoff_longitude: float
    package_description: str
    package_weight: float
    priority: str
    status: str
    created_at: datetime

class AssignmentCreate(BaseModel):
    driver_id: int
    delivery_id: int

class AssignmentAction(BaseModel):
    action: str

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    status: str | None = None

class RouteStop(BaseModel):
    name: str
    latitude: float
    longitude: float

class RouteOptimizeRequest(BaseModel):
    stops: list[RouteStop]

class RouteStopOut(RouteStop):
    sequence: int

class RouteOptimizeOut(BaseModel):
    stops: list[RouteStopOut]
    total_distance_km: float
    estimated_minutes: int
