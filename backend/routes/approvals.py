"""Shell approval endpoints: resolve the pause-and-ask gate of the agent loop.

The loop creates a pending approval per ``shell`` call and waits. The
frontend shows a modal and resolves it here. On deny (or timeout) the
loop cuts the turn.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.agent.utils.approvals import (
    pending_approvals,
    resolve_approval,
)
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    zero_usage,
)

router = APIRouter()


class ApprovalDecision(BaseModel):
    """User decision on a pending shell approval."""

    approved: bool


@router.get("/approvals/pending")
async def list_pending_approvals(session_id: str | None = None) -> JSONResponse:
    """List pending shell approvals, optionally filtered by session.

    Args:
        session_id: When given, only approvals of that session are listed.

    Returns:
        JSON with the pending approvals.
    """
    return JSONResponse(
        status_code=200,
        content=make_success_response(
            message="Pending shell approvals.",
            data=pending_approvals(session_id),
            usage=zero_usage(),
        ),
    )


@router.post("/approvals/{approval_id}/resolve")
async def resolve_pending_approval(approval_id: str, decision: ApprovalDecision) -> JSONResponse:
    """Resolve a pending shell approval with the user's decision.

    Args:
        approval_id: Id emitted in the ``approval_required`` SSE event.
        decision: Whether the user approved the command.

    Returns:
        JSON with the resolution outcome.
    """
    if not resolve_approval(approval_id, decision.approved):
        return JSONResponse(
            status_code=404,
            content=make_error_response(
                message="Approval not found or already resolved.",
                usage=zero_usage(),
            ),
        )
    return JSONResponse(
        status_code=200,
        content=make_success_response(
            message="Approval resolved.",
            data={"approval_id": approval_id, "approved": decision.approved},
            usage=zero_usage(),
        ),
    )
