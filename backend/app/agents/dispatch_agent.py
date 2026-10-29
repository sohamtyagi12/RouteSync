"""Dispatch Agent: recommends which online driver should take a pending delivery.

It is read-only. It reads the delivery and the ranked drivers (the same data
the manual dispatch screen uses) and returns a proposal with a plain-language
reason. A human admin approves it, which calls the normal POST /assignments.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.agents.base import AgentResult, Tool, run_agent
from app.models.models import Delivery
from app.services.dispatch import rank_drivers

SYSTEM = """You are the dispatch agent for RouteSync, a delivery operations platform.
Your job: choose the best ONLINE driver for one pending delivery.

How to decide:
- Start from the ranked candidates (lower dispatch_score is better: it combines distance and current workload).
- You may override the top-ranked driver when the delivery's priority or package makes it worthwhile
  (e.g. urgent/high priority should not wait behind a busy driver; heavy packages suit vans over bikes).
- Only choose a driver_id that appears in the candidate list.

Process: call get_delivery_details and list_driver_candidates, then call submit_proposal exactly once.
In `reasoning`, write 1-3 plain sentences a dispatcher can read at a glance. Do not invent facts."""


def _delivery_details(delivery: Delivery) -> dict:
    waiting_min = int((datetime.utcnow() - delivery.created_at).total_seconds() // 60)
    return {
        "delivery_id": delivery.id,
        "priority": delivery.priority,
        "package_description": delivery.package_description,
        "package_weight_kg": delivery.package_weight,
        "pickup_address": delivery.pickup_address,
        "dropoff_address": delivery.dropoff_address,
        "minutes_waiting": max(waiting_min, 0),
    }


def run_dispatch_agent(db: Session, delivery_id: int) -> dict:
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise LookupError("Delivery not found")
    if delivery.status != "pending":
        raise ValueError(f"Only pending deliveries can be dispatched (this one is {delivery.status})")

    ranked = rank_drivers(db, delivery)
    if not ranked:
        raise ValueError("No online drivers are available right now")
    by_driver = {c["driver"]["id"]: c for c in ranked}

    def list_candidates(_input):
        return [
            {
                "driver_id": c["driver"]["id"],
                "name": c["driver"]["name"],
                "vehicle_type": c["driver"]["vehicle_type"],
                "vehicle_number": c["driver"]["vehicle_number"],
                "distance_to_pickup_km": c["distance_km"],
                "active_deliveries": c["active_deliveries"],
                "dispatch_score": c["dispatch_score"],
            }
            for c in ranked
        ]

    def submit(data):
        driver_id = data.get("driver_id")
        if driver_id not in by_driver:
            raise ValueError(f"driver_id {driver_id} is not an online candidate. Choose from {sorted(by_driver)}.")
        if data.get("confidence") not in {"low", "medium", "high"}:
            raise ValueError("confidence must be low, medium or high")
        chosen = by_driver[driver_id]
        return {
            "delivery_id": delivery.id,
            "driver_id": driver_id,
            "driver_name": chosen["driver"]["name"],
            "vehicle": f'{chosen["driver"]["vehicle_type"]} · {chosen["driver"]["vehicle_number"]}',
            "distance_km": chosen["distance_km"],
            "active_deliveries": chosen["active_deliveries"],
            "confidence": data["confidence"],
            "reasoning": str(data.get("reasoning", "")).strip(),
            "overrides_formula": driver_id != ranked[0]["driver"]["id"],
        }

    tools = [
        Tool("get_delivery_details", "Get the priority, package and addresses of the delivery being dispatched.",
             {"type": "object", "properties": {}}, lambda _i: _delivery_details(delivery)),
        Tool("list_driver_candidates", "List online drivers ranked by dispatch_score (lower is better), with distance to pickup and current workload.",
             {"type": "object", "properties": {}}, list_candidates),
        Tool("submit_proposal", "Submit the final driver recommendation. Call exactly once.",
             {"type": "object",
              "properties": {
                  "driver_id": {"type": "integer"},
                  "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                  "reasoning": {"type": "string", "description": "1-3 plain sentences for the dispatcher"},
              },
              "required": ["driver_id", "confidence", "reasoning"]},
             submit, terminal=True),
    ]
    result: AgentResult = run_agent(system=SYSTEM, task=f"Recommend the best driver for delivery #{delivery.id}.", tools=tools)
    return {"proposal": result.output, "trace": result.trace}
