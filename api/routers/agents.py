from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from agents.base_agent import AgentResult, AgentTask, AgentTaskType
from agents.orchestrator import Orchestrator, classify_task

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response Models ────────────────────────────────────────────────

class RunAgentRequest(BaseModel):
    """Request body for running an agent task."""

    instruction: str
    task_type: AgentTaskType | None = None
    context: dict[str, Any] = {}
    model: str | None = None
    workflow: bool = False  # True = multi-agent workflow


class RunAgentResponse(BaseModel):
    """Envelope response for agent run."""

    data: AgentResult | None = None
    error: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_orchestrator(request: Request) -> Orchestrator:
    """Return the shared Orchestrator instance from app state."""
    return request.app.state.orchestrator


async def _log_agent_run(result: AgentResult, task: RunAgentRequest, request: Request) -> None:
    """Persist agent run metadata to PostgreSQL (best-effort, non-blocking)."""
    try:
        from sqlalchemy import text

        async with request.app.state.db_session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO agent_runs "
                    "(task_id, agent_name, task_type, instruction, output, success, model_used, "
                    " duration_ms, steps_taken, error) "
                    "VALUES (:task_id, :agent_name, :task_type, :instruction, :output, :success, "
                    "        :model_used, :duration_ms, :steps_taken, :error)"
                ),
                {
                    "task_id": result.task_id,
                    "agent_name": result.agent_name,
                    "task_type": (task.task_type or classify_task(task.instruction)).value,
                    "instruction": task.instruction[:4000],
                    "output": result.output[:10000] if result.output else None,
                    "success": result.success,
                    "model_used": result.model_used,
                    "duration_ms": result.duration_ms,
                    "steps_taken": result.steps_taken,
                    "error": result.error,
                },
            )
            await session.commit()
    except Exception as exc:
        logger.error("agent_run.log_failed", error=str(exc))


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
async def list_agents(request: Request) -> dict:
    """List all available agents and their capabilities."""
    orchestrator = _get_orchestrator(request)
    return {"data": orchestrator.list_agents(), "error": None}


@router.post("/run", response_model=RunAgentResponse)
async def run_agent(
    body: RunAgentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> RunAgentResponse:
    """Run an agent task through the orchestrator.

    Set `workflow=true` to trigger a multi-agent pipeline (Research → Writing).
    Otherwise, the orchestrator routes to a single specialist agent.
    """
    if not body.instruction.strip():
        return RunAgentResponse(data=None, error="Instruction cannot be empty")

    orchestrator = _get_orchestrator(request)

    try:
        if body.workflow:
            result = await orchestrator.run_workflow(
                instruction=body.instruction,
                context=body.context,
            )
        elif body.task_type is not None:
            result = await orchestrator.handle_typed(
                instruction=body.instruction,
                task_type=body.task_type,
                context=body.context,
            )
        else:
            result = await orchestrator.handle(
                instruction=body.instruction,
                context=body.context,
            )
    except Exception as exc:
        logger.error("agent_run.failed", error=str(exc))
        return RunAgentResponse(data=None, error=str(exc))

    # Log to DB in background (non-blocking)
    background_tasks.add_task(_log_agent_run, result, body, request)

    return RunAgentResponse(data=result, error=None)


@router.get("/classify")
async def classify_instruction(q: str) -> dict:
    """Preview which agent would handle a given instruction."""
    task_type = classify_task(q)
    return {"data": {"instruction": q, "task_type": task_type.value}, "error": None}
