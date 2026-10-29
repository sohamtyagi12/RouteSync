from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.agents.base import AgentError, AgentNotConfigured, agent_model, agents_configured, provider_name
from app.agents.dispatch_agent import run_dispatch_agent
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
