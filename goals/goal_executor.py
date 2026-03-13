"""Persistent goal execution engine.

GoalExecutor runs goal tasks in the background as asyncio tasks inside the
FastAPI lifespan. It is kill-switch-aware and approval-gated.

Key design decisions:
- One asyncio.Task per running goal, stored in self._running dict
- Kill switch checked at every step boundary (max latency = agent timeout)
- Approval polling uses DB, not pub/sub (survives container restarts)
- Step results written to goals.tasks JSONB after each step
- Progress events published to Redis channel goal:{id}:events for SSE streaming
- Interrupted goals (status=running at startup) are auto-resumed
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.base_agent import AgentTaskType
from goals.goal_manager import GoalManager
from goals.models import Goal, GoalStatus, GoalTask, GoalTaskStatus
from safety.activity_logger import log_event
from safety.approval_queue import await_approval, request_approval
from safety.kill_switch import is_killed

logger = structlog.get_logger()


class GoalExecutor:
    """Manages persistent background execution of goals.

    Usage:
        executor = GoalExecutor(orchestrator, db_session_factory, redis, settings)
        await executor.resume_interrupted_goals()  # called at startup

        # Start a goal:
        await executor.start(goal_id)

        # Cancel a goal:
        await executor.cancel(goal_id)
    """

    def __init__(
        self,
        orchestrator: Any,
        db_session_factory: async_sessionmaker,
        redis: Any,
        approval_timeout_seconds: int = 300,
        max_concurrent: int = 3,
    ) -> None:
        self._orchestrator = orchestrator
        self._db_factory = db_session_factory
        self._redis = redis
        self._approval_timeout = approval_timeout_seconds
        self._max_concurrent = max_concurrent
        self._running: dict[str, asyncio.Task] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self, goal_id: str) -> bool:
        """Launch a background task to execute the goal.

        Returns False if already running or at max concurrency.
        """
        if goal_id in self._running:
            logger.warning("goal_executor.already_running", goal_id=goal_id)
            return False
        if len(self._running) >= self._max_concurrent:
            logger.warning("goal_executor.max_concurrent_reached", goal_id=goal_id)
            return False

        task = asyncio.create_task(
            self._execute_goal(goal_id),
            name=f"goal:{goal_id}",
        )
        self._running[goal_id] = task
        task.add_done_callback(lambda t: self._running.pop(goal_id, None))
        logger.info("goal_executor.started", goal_id=goal_id)
        return True

    async def cancel(self, goal_id: str) -> bool:
        """Cancel a running goal's asyncio task and mark it CANCELLED in the DB."""
        task = self._running.get(goal_id)
        if task is None:
            return False
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        async with self._db_factory() as db:
            manager = GoalManager(db)
            await manager.update_status(goal_id, GoalStatus.CANCELLED)
            await log_event(
                db,
                event_type="goal.cancelled",
                description=f"Goal cancelled by user: {goal_id}",
                entity_type="goal",
                entity_id=goal_id,
            )
        logger.info("goal_executor.cancelled", goal_id=goal_id)
        return True

    async def resume_interrupted_goals(self) -> None:
        """Re-queue goals that were RUNNING when the system last shut down."""
        async with self._db_factory() as db:
            manager = GoalManager(db)
            interrupted = await manager.get_interrupted_goals()
        for goal_id in interrupted:
            logger.info("goal_executor.resuming_interrupted", goal_id=goal_id)
            await self.start(goal_id)

    def running_count(self) -> int:
        """Return the number of currently running goals."""
        return len(self._running)

    # ── Internal execution loop ───────────────────────────────────────────────

    async def _execute_goal(self, goal_id: str) -> None:
        """Main execution loop for one goal. Runs as a background asyncio.Task."""
        async with self._db_factory() as db:
            manager = GoalManager(db)
            goal = await manager.get(goal_id)
            if goal is None:
                logger.error("goal_executor.goal_not_found", goal_id=goal_id)
                return

            await manager.update_status(goal_id, GoalStatus.RUNNING)
            await log_event(
                db,
                event_type="goal.started",
                description=f"Goal execution started: {goal.title}",
                entity_type="goal",
                entity_id=goal_id,
            )
            await self._publish_event(goal_id, "goal.started", {"title": goal.title})

        try:
            await self._run_steps(goal_id, goal)
        except asyncio.CancelledError:
            logger.info("goal_executor.task_cancelled", goal_id=goal_id)
        except Exception as exc:
            logger.error("goal_executor.fatal_error", goal_id=goal_id, error=str(exc))
            async with self._db_factory() as db:
                manager = GoalManager(db)
                await manager.update_status(goal_id, GoalStatus.FAILED)
                await log_event(
                    db,
                    event_type="goal.failed",
                    description=f"Goal failed with unhandled error: {exc}",
                    entity_type="goal",
                    entity_id=goal_id,
                    payload={"error": str(exc)},
                )
            await self._publish_event(goal_id, "goal.failed", {"error": str(exc)})

    async def _run_steps(self, goal_id: str, goal: Goal) -> None:
        """Execute goal tasks in dependency order."""
        completed_steps: set[int] = {
            t.step_number for t in goal.tasks if t.status == GoalTaskStatus.COMPLETED
        }

        for task_def in sorted(goal.tasks, key=lambda t: t.step_number):
            if task_def.status == GoalTaskStatus.COMPLETED:
                continue  # already done — skip on resume

            # Check kill switch
            if await is_killed(self._redis):
                logger.warning("goal_executor.killed", goal_id=goal_id, step=task_def.step_number)
                async with self._db_factory() as db:
                    manager = GoalManager(db)
                    await manager.update_status(goal_id, GoalStatus.PAUSED)
                await self._publish_event(goal_id, "goal.killed", {"step": task_def.step_number})
                return

            # Dependency check
            if task_def.depends_on:
                unmet = [s for s in task_def.depends_on if s not in completed_steps]
                if unmet:
                    logger.info("goal_executor.step_skipped_deps", goal_id=goal_id,
                                step=task_def.step_number, unmet=unmet)
                    async with self._db_factory() as db:
                        await GoalManager(db).update_task_result(
                            goal_id, task_def.step_number, {},
                            GoalTaskStatus.SKIPPED,
                            error=f"Dependencies not met: {unmet}",
                        )
                    continue

            # Approval gate: explicit flag or inherently sensitive task types.
            needs_approval = task_def.requires_approval or task_def.task_type in {"file"}
            if needs_approval:
                approved = await self._request_and_await_approval(goal_id, task_def)
                if not approved:
                    async with self._db_factory() as db:
                        await GoalManager(db).update_task_result(
                            goal_id, task_def.step_number, {},
                            GoalTaskStatus.FAILED,
                            error="Action denied or timed out in approval queue.",
                        )
                    await self._publish_event(goal_id, "goal.step.denied",
                                              {"step": task_def.step_number})
                    continue

            # Execute step
            await self._execute_step(goal_id, task_def, completed_steps)

        # Check if all tasks completed
        async with self._db_factory() as db:
            refreshed = await GoalManager(db).get(goal_id)
        if refreshed:
            all_done = all(
                t.status in (GoalTaskStatus.COMPLETED, GoalTaskStatus.SKIPPED)
                for t in refreshed.tasks
            )
            any_failed = any(t.status == GoalTaskStatus.FAILED for t in refreshed.tasks)
            final_status = GoalStatus.FAILED if any_failed else GoalStatus.COMPLETED

            async with self._db_factory() as db:
                manager = GoalManager(db)
                await manager.update_status(goal_id, final_status)
                await log_event(
                    db,
                    event_type=f"goal.{final_status.value}",
                    description=f"Goal {final_status.value}: {refreshed.title}",
                    entity_type="goal",
                    entity_id=goal_id,
                )
            await self._publish_event(goal_id, f"goal.{final_status.value}", {})
            logger.info("goal_executor.done", goal_id=goal_id, status=final_status.value)

    async def _execute_step(
        self,
        goal_id: str,
        task_def: GoalTask,
        completed_steps: set[int],
    ) -> None:
        """Run one agent task and persist the result."""
        logger.info("goal_executor.step_start", goal_id=goal_id, step=task_def.step_number,
                    task_type=task_def.task_type)
        await self._publish_event(goal_id, "goal.step.started",
                                  {"step": task_def.step_number, "task_type": task_def.task_type})

        async with self._db_factory() as db:
            await GoalManager(db).update_task_result(
                goal_id, task_def.step_number, {}, GoalTaskStatus.RUNNING,
            )

        start_ms = int(time.monotonic() * 1000)
        try:
            task_type = AgentTaskType(task_def.task_type)
        except ValueError:
            task_type = AgentTaskType.GENERAL

        step_context: dict[str, Any] = {"goal_id": goal_id, "step_number": task_def.step_number}

        # For file tasks, pass dependency outputs as write content when available.
        if task_type == AgentTaskType.FILE and task_def.depends_on:
            async with self._db_factory() as db:
                goal_state = await GoalManager(db).get(goal_id)
            if goal_state:
                dep_outputs: list[str] = []
                by_step = {t.step_number: t for t in goal_state.tasks}
                for dep in task_def.depends_on:
                    dep_task = by_step.get(dep)
                    if dep_task and isinstance(dep_task.result, dict):
                        out = dep_task.result.get("output")
                        if isinstance(out, str) and out.strip():
                            dep_outputs.append(out)
                if dep_outputs:
                    step_context["content"] = "\n\n".join(dep_outputs)

        result = await self._orchestrator.handle_typed(
            instruction=task_def.instruction,
            task_type=task_type,
            context=step_context,
        )

        step_status = GoalTaskStatus.COMPLETED if result.success else GoalTaskStatus.FAILED
        result_payload = {
            "output": result.output,
            "sources": result.sources,
            "artifacts": result.artifacts,
            "duration_ms": result.duration_ms,
            "model_used": result.model_used,
        }

        async with self._db_factory() as db:
            manager = GoalManager(db)
            await manager.update_task_result(
                goal_id=goal_id,
                step_number=task_def.step_number,
                result=result_payload,
                status=step_status,
                error=result.error,
            )
            await log_event(
                db,
                event_type=f"goal.step.{'completed' if result.success else 'failed'}",
                description=f"Step {task_def.step_number} {step_status.value}: {task_def.instruction[:80]}",
                entity_type="goal",
                entity_id=goal_id,
                payload={"step": task_def.step_number, "agent": result.agent_name,
                         "duration_ms": result.duration_ms},
            )

        if result.success:
            completed_steps.add(task_def.step_number)

        await self._publish_event(
            goal_id,
            f"goal.step.{'completed' if result.success else 'failed'}",
            {
                "step": task_def.step_number,
                "output_preview": result.output[:200],
                "success": result.success,
            },
        )
        logger.info("goal_executor.step_done", goal_id=goal_id, step=task_def.step_number,
                    success=result.success)

    async def _request_and_await_approval(
        self, goal_id: str, task_def: GoalTask
    ) -> bool:
        """Create an approval request and block until resolved."""
        async with self._db_factory() as db:
            approval_id = await request_approval(
                db=db,
                action_type=task_def.task_type,
                action_description=task_def.instruction[:200],
                action_payload={"step_number": task_def.step_number, "instruction": task_def.instruction},
                goal_id=goal_id,
                task_step=task_def.step_number,
            )
            # Update task to record approval_id
            await GoalManager(db).update_task_result(
                goal_id, task_def.step_number, {},
                GoalTaskStatus.AWAITING_APPROVAL,
                approval_id=approval_id,
            )

        await self._publish_event(
            goal_id, "approval.requested",
            {"step": task_def.step_number, "approval_id": approval_id,
             "description": task_def.instruction[:200]},
        )

        approved = await await_approval(
            db_session_factory=self._db_factory,
            redis=self._redis,
            approval_id=approval_id,
            timeout_seconds=self._approval_timeout,
        )
        return approved

    async def _publish_event(self, goal_id: str, event_type: str, data: dict) -> None:
        """Publish a progress event to Redis pub/sub for SSE streaming."""
        channel = f"goal:{goal_id}:events"
        payload = json.dumps({"event": event_type, "data": data})
        try:
            await self._redis.publish(channel, payload)
        except Exception as exc:
            logger.warning("goal_executor.publish_error", channel=channel, error=str(exc))
