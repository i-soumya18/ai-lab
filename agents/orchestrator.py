from __future__ import annotations

import re
import time
import uuid
from typing import Any, TypedDict

import structlog
from langgraph.graph import END, StateGraph

from agents.base_agent import AgentResult, AgentTask, AgentTaskType, BaseAgent
from agents.coding_agent import CodingAgent
from agents.data_agent import DataAgent
from agents.file_agent import FileAgent
from agents.goal_planner_agent import GoalPlannerAgent
from agents.research_agent import ResearchAgent
from agents.writing_agent import WritingAgent
from memory.conversation_store import ConversationStore
from models.ollama_client import OllamaClient
from models.router import ModelRouter

logger = structlog.get_logger()

# ── Keyword routing rules ─────────────────────────────────────────────────────

_TASK_PATTERNS: dict[AgentTaskType, list[str]] = {
    AgentTaskType.RESEARCH: [
        r"\b(research|investigate|find out|look up|market|trend|competitor|"
        r"analysis|analyze market|news about|what is|who is|explain)\b",
    ],
    AgentTaskType.CODING: [
        r"\b(code|function|class|bug|debug|refactor|implement|write a script|"
        r"fix this|syntax|python|typescript|javascript|compile|test|unit test)\b",
    ],
    AgentTaskType.DATA: [
        r"\b(csv|dataset|dataframe|statistics|chart|plot|visualize|"
        r"analyze data|summarize data|average|median|correlation|json data)\b",
    ],
    AgentTaskType.WRITING: [
        r"\b(write|draft|create a report|document|summarize|essay|article|"
        r"blog post|proposal|readme|technical doc|executive summary)\b",
    ],
    AgentTaskType.FILE: [
        r"\b(file|folder|directory|ingest|read file|list files|watch|"
        r"scan dir|summarize file|diff|compare files)\b",
    ],
    AgentTaskType.GOAL_PLAN: [
        r"\b(plan|break down|decompose|goal|multi-step|workflow)\b",
    ],
}


def classify_task(instruction: str) -> AgentTaskType:
    """Classify a task instruction into an AgentTaskType.

    Priority: CODING > RESEARCH > DATA > WRITING > FILE > GOAL_PLAN.
    Falls back to GENERAL if no pattern matches.
    """
    lower = instruction.lower()

    for task_type in [
        AgentTaskType.CODING,
        AgentTaskType.RESEARCH,
        AgentTaskType.DATA,
        AgentTaskType.WRITING,
        AgentTaskType.FILE,
        AgentTaskType.GOAL_PLAN,
    ]:
        patterns = _TASK_PATTERNS.get(task_type, [])
        for pat in patterns:
            if re.search(pat, lower):
                logger.debug("orchestrator.classify", task_type=task_type, instruction=instruction[:60])
                return task_type

    return AgentTaskType.GENERAL


# ── LangGraph multi-agent workflow state ──────────────────────────────────────

class WorkflowState(TypedDict):
    """Shared state across a multi-agent workflow."""

    task_id: str
    original_instruction: str
    research_result: AgentResult | None
    data_result: AgentResult | None
    writing_result: AgentResult | None
    final_output: str
    error: str | None


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """Routes tasks to the appropriate agent or runs multi-agent workflows.

    The Orchestrator is the single entry point from the API layer.
    It never runs tasks itself — it delegates 100% to specialist agents.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        chroma_client: Any = None,
        embedder: Any = None,
        conversation_store: ConversationStore | None = None,
        redis: Any = None,
    ) -> None:
        self._ollama = ollama_client
        self._chroma = chroma_client
        self._embedder = embedder
        self._conversation_store = conversation_store
        self._model_router = ModelRouter()
        self._redis = redis

        # Initialize specialist agents
        self._agents: dict[AgentTaskType, BaseAgent] = {
            AgentTaskType.RESEARCH: ResearchAgent(
                ollama_client=ollama_client,
                chroma_client=chroma_client,
                embedder=embedder,
            ),
            AgentTaskType.CODING: CodingAgent(
                ollama_client=ollama_client,
                chroma_client=chroma_client,
                embedder=embedder,
            ),
            AgentTaskType.DATA: DataAgent(ollama_client=ollama_client),
            AgentTaskType.WRITING: WritingAgent(ollama_client=ollama_client),
            AgentTaskType.FILE: FileAgent(
                ollama_client=ollama_client,
                chroma_client=chroma_client,
                embedder=embedder,
            ),
            AgentTaskType.GOAL_PLAN: GoalPlannerAgent(ollama_client=ollama_client),
            AgentTaskType.GENERAL: WritingAgent(ollama_client=ollama_client),
        }

    async def _inject_memory(self, task: AgentTask) -> AgentTask:
        """Search long-term memory and inject relevant context into the task."""
        if self._chroma and self._embedder:
            from agents.tools.memory_tools import memory_search
            memories = await memory_search(
                query=task.instruction,
                chroma_client=self._chroma,
                embedder=self._embedder,
            )
            task = task.model_copy(
                update={"memory_context": [m.content for m in memories[:3]]}
            )
        return task

    async def handle(self, instruction: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Handle a single-agent task.

        1. Classify the task type
        2. Inject memory context
        3. Delegate to the appropriate agent (with kill-switch awareness)
        4. Return structured result
        """
        task_type = classify_task(instruction)
        agent = self._agents.get(task_type) or self._agents.get(AgentTaskType.RESEARCH)

        task = AgentTask(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            instruction=instruction,
            context=context or {},
        )
        task = await self._inject_memory(task)

        logger.info(
            "orchestrator.delegating",
            task_id=task.task_id,
            agent=agent.name if agent else "none",
            task_type=task_type,
        )

        if agent is None:
            return AgentResult(
                task_id=task.task_id,
                agent_name="orchestrator",
                success=False,
                output="",
                error=f"No agent available for task type: {task_type}",
                model_used="",
            )

        return await agent.execute(task, redis=self._redis)

    async def handle_typed(
        self,
        instruction: str,
        task_type: AgentTaskType,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Handle a task with an explicitly specified agent type (used by GoalExecutor)."""
        agent = self._agents.get(task_type) or self._agents.get(AgentTaskType.RESEARCH)
        task = AgentTask(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            instruction=instruction,
            context=context or {},
        )
        task = await self._inject_memory(task)

        if agent is None:
            return AgentResult(
                task_id=task.task_id,
                agent_name="orchestrator",
                success=False,
                output="",
                error=f"No agent for task type: {task_type}",
                model_used="",
            )
        return await agent.execute(task, redis=self._redis)

    async def run_workflow(self, instruction: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Run a multi-agent workflow for complex tasks using LangGraph StateGraph."""
        task_id = str(uuid.uuid4())
        start = time.monotonic()
        ctx = context or {}

        workflow = StateGraph(WorkflowState)

        async def research_node(state: WorkflowState) -> WorkflowState:
            agent = self._agents[AgentTaskType.RESEARCH]
            task = AgentTask(
                task_id=state["task_id"],
                task_type=AgentTaskType.RESEARCH,
                instruction=state["original_instruction"],
                context=ctx,
            )
            task = await self._inject_memory(task)
            result = await agent.execute(task, redis=self._redis)
            return {**state, "research_result": result}

        async def writing_node(state: WorkflowState) -> WorkflowState:
            agent = self._agents[AgentTaskType.WRITING]
            research_out = state.get("research_result")
            writing_ctx = {
                **ctx,
                "research_output": research_out.output if research_out else "",
            }
            task = AgentTask(
                task_id=state["task_id"],
                task_type=AgentTaskType.WRITING,
                instruction=state["original_instruction"],
                context=writing_ctx,
            )
            task = await self._inject_memory(task)
            result = await agent.execute(task, redis=self._redis)
            return {**state, "writing_result": result, "final_output": result.output}

        workflow.add_node("research", research_node)
        workflow.add_node("writing", writing_node)
        workflow.set_entry_point("research")
        workflow.add_edge("research", "writing")
        workflow.add_edge("writing", END)

        compiled = workflow.compile()
        initial_state: WorkflowState = {
            "task_id": task_id,
            "original_instruction": instruction,
            "research_result": None,
            "data_result": None,
            "writing_result": None,
            "final_output": "",
            "error": None,
        }

        final_state = await compiled.ainvoke(initial_state)
        elapsed = int((time.monotonic() - start) * 1000)

        writing_result = final_state.get("writing_result")
        research_result = final_state.get("research_result")

        return AgentResult(
            task_id=task_id,
            agent_name="orchestrator:workflow",
            success=writing_result is not None and writing_result.success,
            output=final_state.get("final_output", ""),
            sources=research_result.sources if research_result else [],
            steps_taken=2,
            duration_ms=elapsed,
            model_used=self._model_router.get_model("general"),
        )

    def list_agents(self) -> list[dict[str, str]]:
        """Return metadata about available agents."""
        return [
            {
                "name": agent.name,
                "task_type": task_type.value,
                "model": agent.model,
            }
            for task_type, agent in self._agents.items()
        ]
