from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.agents.base import AgentError, AgentNotConfigured, agent_model, agents_configured, provider_name
from app.agents.dispatch_agent import run_dispatch_agent
from app.agents.intake_agent import run_intake_agent
from app.agents.ratelimit import check_agent_rate_limit
from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models.models import User

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status")
def agent_status(user: User = Depends(get_current_user)):
    """Lets the frontend hide AI panels when no API key is configured."""
    return {"configured": agents_configured(), "provider": provider_name(), "model": agent_model()}


@router.post("/dispatch/{delivery_id}")
def dispatch_agent(delivery_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    check_agent_rate_limit(user)
    try:
        return run_dispatch_agent(db, delivery_id)
    except AgentNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


class IntakeRequest(BaseModel):
    text: str


@router.post("/intake")
def intake_agent(body: IntakeRequest, user: User = Depends(require_roles("admin", "customer"))):
    """Turns a plain-English request into a DRAFT delivery. Creates nothing."""
    check_agent_rate_limit(user)
    try:
        return run_intake_agent(body.text)
    except AgentNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
