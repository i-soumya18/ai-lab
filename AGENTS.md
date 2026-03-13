# AGENTS.md — Agent System Specification

> This file defines every AI agent in the Personal AI Lab, their roles, capabilities,
> tools, input/output contracts, and how the Orchestrator routes tasks between them.
> Claude Code must read this before implementing any agent logic.

---

## AGENT PHILOSOPHY

Every agent in this system follows these principles:

1. **Single Responsibility** — each agent does one thing extremely well
2. **Structured I/O** — all agents accept and return Pydantic models, never raw strings
3. **Tool-bounded** — agents can only use tools explicitly granted to them
4. **Logged** — every agent invocation is logged to PostgreSQL
5. **Timeout-safe** — all agents have a hard 120-second execution timeout
6. **Fallback-aware** — agents must handle tool failures gracefully and report them

---

## AGENT HIERARCHY

```
User Request / Goal
     │
     ▼
┌─────────────────┐
│   ORCHESTRATOR  │  ← The only agent the API talks to directly
│   (Manager)     │
└────────┬────────┘
         │  delegates to
    ┌────┴────────────────────────────────────┐
    │                                         │
    ▼                                         ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ RESEARCH │  │  CODING  │  │   DATA   │  │ WRITING  │  │  FILE    │  │  GOAL    │
│  AGENT   │  │  AGENT   │  │  AGENT   │  │  AGENT   │  │  AGENT   │  │ PLANNER  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
    │               │              │             │             │             │
   Tools           Tools          Tools         Tools         Tools         Tools

Goal Executor Layer (persistent, approval-gated):
┌─────────────────────────────────────────────────────────────┐
│  GoalExecutor (asyncio background task in FastAPI lifespan) │
│  ├─ KillSwitch check at each step (Redis key)               │
│  ├─ ApprovalQueue gate before sensitive actions             │
│  ├─ ActivityLogger records every event to PostgreSQL        │
│  └─ Delegates each step to Orchestrator                     │
└─────────────────────────────────────────────────────────────┘
```

---

## SHARED DATA MODELS

Define these in `agents/base_agent.py`. All agents use them.

```python
from pydantic import BaseModel
from typing import Any
from enum import Enum

class AgentTaskType(str, Enum):
    RESEARCH = "research"
    CODING = "coding"
    DATA = "data"
    WRITING = "writing"
    GENERAL = "general"

class AgentTask(BaseModel):
    task_id: str
    task_type: AgentTaskType
    instruction: str
    context: dict[str, Any] = {}
    memory_context: list[str] = []   # relevant memories injected by orchestrator
    max_steps: int = 10
    timeout_seconds: int = 120

class AgentResult(BaseModel):
    task_id: str
    agent_name: str
    success: bool
    output: str
    artifacts: list[dict] = []       # files, code, data produced
    sources: list[str] = []          # citations, file paths, URLs used
    steps_taken: int
    duration_ms: int
    model_used: str
    error: str | None = None
```

---

## AGENT 0: ORCHESTRATOR

**File:** `agents/orchestrator.py`  
**Model:** `llama3` (default), switches based on task  
**Framework:** LangGraph `StateGraph`

### Role
The central brain. It receives all tasks from the API, decides which agent(s) handle them,
coordinates multi-agent workflows, injects memory context, and assembles final responses.

### Routing Logic

The orchestrator uses keyword and intent classification to route tasks:

```python
ROUTING_RULES = {
    # Keywords → Agent
    "code|debug|function|class|error|refactor|architecture|git|repository": "coding",
    "research|market|competitor|trend|analysis|idea|validate|explore": "research",
    "csv|dataset|statistics|chart|analyze data|numbers|excel|tabular": "data",
    "write|report|document|summary|blog|readme|draft|format": "writing",
}
```

For complex tasks requiring multiple agents, the orchestrator creates a **LangGraph workflow**
that chains agents sequentially or in parallel.

### Multi-Agent Workflow (LangGraph StateGraph)

```python
class WorkflowState(TypedDict):
    task: AgentTask
    research_result: AgentResult | None
    data_result: AgentResult | None
    writing_result: AgentResult | None
    final_output: str
    steps: list[str]
```

### Example: "Create startup idea report" Workflow

```
Orchestrator
    │
    ├─ Step 1: ResearchAgent → collect market data
    │          (output stored in WorkflowState)
    │
    ├─ Step 2: DataAgent → analyze and structure findings
    │          (receives ResearchAgent output as context)
    │
    └─ Step 3: WritingAgent → produce formatted report
               (receives both previous outputs as context)
```

### Orchestrator API

```python
class Orchestrator:
    async def handle(self, task: AgentTask) -> AgentResult: ...
    async def run_workflow(self, tasks: list[AgentTask]) -> AgentResult: ...
    async def classify_task(self, instruction: str) -> AgentTaskType: ...
    async def inject_memory(self, task: AgentTask) -> AgentTask: ...
```

---

## AGENT 1: RESEARCH AGENT

**File:** `agents/research_agent.py`  
**Model:** `nemotron-3-super:cloud`  
**Tools:** `web_search`, `file_read`, `memory_search`, `url_scrape`

### Role
Collects, synthesizes, and summarizes information from multiple sources.
Used for market research, idea validation, trend analysis, competitor analysis.

### Capabilities

| Capability            | Description                                                    |
|-----------------------|----------------------------------------------------------------|
| Market research       | Gather data on a market, size, trends, key players            |
| Competitor analysis   | Profile competitors using scraped public info                  |
| Idea validation       | Evaluate ideas against market reality                         |
| Trend analysis        | Identify patterns from collected data                         |
| Literature review     | Summarize documents from the RAG knowledge base               |

### Tools Available

```python
# agents/tools/web_search.py
async def web_search(query: str, max_results: int = 5) -> list[SearchResult]:
    """
    Uses DuckDuckGo HTML scraping (no API key required).
    Returns title, url, snippet for each result.
    Falls back to cached results if network unavailable.
    """

# agents/tools/file_tools.py  
async def file_read(path: str) -> str:
    """Read a file from the local filesystem."""

async def memory_search(query: str, collection: str = "research") -> list[str]:
    """Search ChromaDB for relevant stored research."""
```

### System Prompt

```
You are a Research Agent specialized in information gathering and synthesis.
Your job is to collect accurate, relevant information and produce structured summaries.

Rules:
- Always cite your sources
- Distinguish between facts and speculation
- If information is unavailable, say so clearly
- Structure output with clear sections: Summary, Key Findings, Sources
- Do not fabricate statistics or company data
```

### Output Contract

```python
class ResearchOutput(BaseModel):
    summary: str
    key_findings: list[str]
    sources: list[str]
    confidence: float  # 0.0 to 1.0
    gaps: list[str]    # what couldn't be found
```

---

## AGENT 2: CODING AGENT

**File:** `agents/coding_agent.py`  
**Model:** `nemotron-3-super:cloud`  
**Tools:** `file_read`, `file_write`, `code_search`, `git_read`, `shell_safe`

### Role
Understands entire codebases, answers code questions, generates functions,
debugs errors, and documents software.

### Capabilities

| Capability             | Description                                                     |
|------------------------|-----------------------------------------------------------------|
| Code Q&A               | Answer questions about a codebase ingested into RAG             |
| Code generation        | Write functions, classes, modules based on spec                 |
| Bug diagnosis          | Analyze error traces and suggest fixes                          |
| Architecture review    | Explain system design, suggest improvements                     |
| Refactoring            | Propose and apply refactors                                     |
| Documentation          | Generate docstrings, README sections, API docs                  |
| Test generation        | Write unit tests for existing functions                         |

### Tools Available

```python
# agents/tools/code_tools.py

async def code_search(query: str, repo_collection: str) -> list[CodeChunk]:
    """
    Semantic search over ingested codebase in ChromaDB.
    Returns file path, line range, and code snippet.
    """

async def git_read(repo_path: str, file_path: str) -> str:
    """Read a file from a git repository."""

async def shell_safe(command: str, allowed_commands: list[str]) -> str:
    """
    Execute a shell command from an allowlist only.
    Allowed: ['git log', 'git diff', 'git show', 'python -m py_compile']
    Never executes arbitrary commands.
    """
```

### Codebase Ingestion

Before the Coding Agent can answer questions about a repo, it must be ingested:

```
POST /api/v1/rag/ingest
{
  "source_type": "git",
  "path": "/home/user/projects/my-app",
  "collection": "codebase-my-app",
  "include_extensions": [".py", ".ts", ".tsx", ".js", ".go", ".rs", ".md"]
}
```

The RAG pipeline chunks code using `RecursiveCharacterTextSplitter` with code-aware separators.

### System Prompt

```
You are a Coding Agent with deep software engineering expertise.
You have access to a codebase through semantic search tools.

Rules:
- Always look up relevant code before answering code questions
- Produce working, tested code — never pseudocode unless asked
- Follow the language conventions of the existing codebase
- Explain your reasoning step by step
- Flag potential bugs or security issues you notice
- Never generate shell commands outside the safe allowlist
```

### Output Contract

```python
class CodingOutput(BaseModel):
    explanation: str
    code_blocks: list[CodeBlock]
    files_modified: list[str]
    tests: list[CodeBlock]
    warnings: list[str]

class CodeBlock(BaseModel):
    language: str
    filename: str | None
    content: str
    description: str
```

---

## AGENT 3: DATA AGENT

**File:** `agents/data_agent.py`  
**Model:** `nemotron-3-super:cloud`  
**Tools:** `file_read`, `csv_analyze`, `json_parse`, `memory_search`

### Role
Analyzes structured data (CSV, JSON, spreadsheets), generates insights,
identifies patterns, creates summaries with statistics.

### Capabilities

| Capability          | Description                                               |
|---------------------|-----------------------------------------------------------|
| CSV analysis        | Load and describe datasets, compute statistics            |
| Insight generation  | Identify top patterns, outliers, trends                   |
| Data summarization  | Produce human-readable summaries of datasets              |
| Cross-source join   | Combine multiple datasets conceptually                    |
| Report structuring  | Organize analysis results for the Writing Agent           |

### Tools Available

```python
# agents/tools/file_tools.py

async def csv_analyze(file_path: str) -> DataSummary:
    """
    Uses pandas to:
    - Load CSV
    - Compute shape, dtypes, null counts
    - Generate describe() statistics
    - Identify top 5 patterns
    Returns a DataSummary object (never returns raw DataFrame)
    """

async def json_parse(file_path: str, jq_query: str | None) -> dict:
    """Parse and optionally filter JSON data."""
```

### System Prompt

```
You are a Data Analysis Agent specialized in extracting insights from structured data.

Rules:
- Always describe the shape and structure of data before analyzing it
- Report actual numbers, not vague descriptions
- Highlight anomalies and outliers explicitly
- Keep statistical jargon minimal — speak plainly
- Never fabricate data points — only report what the data shows
```

### Output Contract

```python
class DataOutput(BaseModel):
    dataset_description: str
    key_statistics: dict[str, Any]
    insights: list[str]
    anomalies: list[str]
    recommendations: list[str]
    chart_suggestions: list[str]  # for future visualization
```

---

## AGENT 4: WRITING AGENT

**File:** `agents/writing_agent.py`  
**Model:** `nemotron-3-super:cloud`  
**Tools:** `file_read`, `file_write`, `memory_search`, `template_load`

### Role
Produces well-structured written content: reports, documentation,
summaries, blog posts, README files, and research papers.

### Capabilities

| Capability          | Description                                                   |
|---------------------|---------------------------------------------------------------|
| Report generation   | Multi-section professional reports from structured input      |
| Documentation       | README, API docs, user guides                                 |
| Summarization       | Condense long content into key points                         |
| Blog/article        | Write formatted long-form content                             |
| Email drafting      | Professional email composition                                |
| Meeting notes       | Structure raw notes into formal meeting minutes               |

### Tools Available

```python
async def file_write(path: str, content: str) -> bool:
    """Write output to a file in /home/user/ai-lab/outputs/"""

async def template_load(template_name: str) -> str:
    """Load a document template from /ai-lab/templates/"""
```

### System Prompt

```
You are a Writing Agent specialized in producing clear, professional written content.

Rules:
- Always use the input context — never fabricate information
- Structure documents with clear headings, sections, and flow
- Match the requested tone (professional, casual, technical)
- Produce complete documents, not outlines (unless an outline is requested)
- Cite sources when provided by Research or Data agents
- Output in Markdown format unless another format is specified
```

### Output Contract

```python
class WritingOutput(BaseModel):
    title: str
    content: str           # full document in Markdown
    word_count: int
    sections: list[str]    # list of section headings
    output_file: str | None  # path if saved to disk
```

---

## AUTOMATION AGENTS

These are **scheduled agents** that run on a cron schedule without user interaction.
Defined in `automation/tasks/`.

### Daily Summary Agent

```
Schedule: every day at 8:00 AM
Task: Summarize key events, pending items, and research from the past 24 hours
Output: Saved to memory + optionally pushed as notification
Model: phi3 (fast, lightweight)
```

### News Collector Agent

```
Schedule: every 6 hours
Task: Scrape configured RSS feeds or topics, summarize new content
Output: Stored in RAG collection "news"
Model: phi3
```

### Website Monitor Agent

```
Schedule: every hour
Task: Check configured URLs for changes, alert user if significant change detected
Output: Stored diff + alert in memory
Model: phi3
```

---

## MEMORY TOOLS AVAILABLE TO ALL AGENTS

Every agent can use these tools via `agents/tools/memory_tools.py`:

```python
async def memory_search(
    query: str,
    collection: str = "memory",
    top_k: int = 5
) -> list[MemoryChunk]:
    """Semantic search across long-term vector memory."""

async def memory_store(
    content: str,
    metadata: dict,
    collection: str = "memory"
) -> bool:
    """Store a fact or summary in long-term memory."""

async def memory_recall_recent(
    user_id: str,
    limit: int = 10
) -> list[ConversationMessage]:
    """Get recent conversation messages from Redis."""
```

---

## AGENT LOGGING SCHEMA

Every agent invocation must be logged to PostgreSQL table `agent_runs`:

```sql
CREATE TABLE agent_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       TEXT NOT NULL,
    agent_name    TEXT NOT NULL,
    task_type     TEXT NOT NULL,
    instruction   TEXT NOT NULL,
    output        TEXT,
    success       BOOLEAN NOT NULL,
    model_used    TEXT NOT NULL,
    duration_ms   INTEGER,
    steps_taken   INTEGER,
    error         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

## AGENT 5: GOAL PLANNER AGENT

**File:** `agents/goal_planner_agent.py`
**Model:** `nemotron-3-super:cloud` (temperature=0.2 for determinism)
**Tools:** None — pure LLM reasoning

### Role
Decomposes a high-level user goal into an ordered sequence of executable `GoalTask` steps.
Each step is assigned to one of the specialist agents. Used by `POST /api/v1/goals/` on creation.

### Output Contract

```python
class GoalPlannerOutput(BaseModel):
    tasks: list[GoalTask]   # ordered list from goals/models.py
    reasoning: str          # brief explanation of the decomposition
```

### System Prompt

```
You are a Goal Planner. Break the given goal into a sequence of 2-8 concrete, executable tasks.
Each task must specify:
- step_number (1-based integer)
- task_type: one of "research", "coding", "data", "writing", "file"
- instruction: a clear, self-contained instruction for the agent
- requires_approval: true only for file writes, deletions, or external calls
- depends_on: list of step_numbers this task depends on (empty = run immediately)

Respond ONLY with valid JSON: {"tasks": [...], "reasoning": "..."}
Do not add markdown fences or explanation outside the JSON.
```

---

## AGENT 6: FILE AGENT

**File:** `agents/file_agent.py`
**Model:** `nemotron-3-super:cloud`
**Tools:** `file_list`, `file_read`, `file_diff`, `ingest_to_rag`

### Role
Manages file system operations: listing, reading, comparing, and ingesting files into the RAG system.
All write/delete operations require an approval request before execution.

### Security Constraints

```python
SAFE_READ_DIRS = ["/app/data", "/app/watched", "/app/outputs", "/app/templates"]
# Agent can ONLY read from these directories. Writes go to /app/outputs ONLY.
# Any write outside /app/outputs requires approval AND is blocked by path check.
```

### Capabilities

| Capability         | Description                                              | Requires Approval |
|--------------------|----------------------------------------------------------|-------------------|
| List directory     | List files in a safe dir with metadata                  | No                |
| Read file          | Read text content of a file                             | No                |
| Diff files         | Compare two versions of a file                          | No                |
| Ingest to RAG      | Chunk + embed a file into a ChromaDB collection         | No                |
| Write file         | Write content to `/app/outputs/`                        | Yes               |
| Auto-summarize     | Summarize a document on file change trigger             | No                |

### Output Contract

```python
class FileOutput(BaseModel):
    files_processed: list[str]
    summary: str
    ingested_to_collection: str | None
    output_file: str | None
    warnings: list[str]
```

---

## SAFETY & APPROVAL SYSTEM

### Overview

Every sensitive action in the system (file writes, shell commands, goal starts) goes through
a **human-in-the-loop approval gate** before execution. The safety layer lives in `safety/`.

### Action Types Requiring Approval

| `ActionType`    | Description                                          |
|-----------------|------------------------------------------------------|
| `file_write`    | Writing any file to disk                             |
| `file_delete`   | Deleting any file                                    |
| `shell_exec`    | Running any shell command                            |
| `web_request`   | Making HTTP requests outside the Docker network      |
| `memory_write`  | Writing to long-term vector memory                   |
| `goal_start`    | Starting a goal that accesses sensitive areas        |
| `external_call` | Any call to an external service                      |

### Approval Flow

```
Agent decides to do sensitive action
         │
         ▼
safety/approval_queue.py:request_approval()
  → INSERT into approval_requests table (status="pending")
  → Log to activity_log
         │
         ▼
GoalExecutor.await_approval()  ← polls DB every 2 seconds
  → Also checks kill switch on each poll
  → Times out after settings.approval_timeout_seconds (default: 300s)
         │
    ┌────┴────────────────────┐
    │                         │
    ▼                         ▼
User calls                User calls
/api/v1/approvals/{id}/   /api/v1/approvals/{id}/
   approve                    deny
         │                         │
         ▼                         ▼
approval_requests.status    Agent aborts the step,
= "approved"                logs the denial,
Agent proceeds              continues to next task
```

### Kill Switch

```python
# safety/kill_switch.py
KILL_SWITCH_KEY = "system:killswitch"

async def activate(redis) -> None: ...    # sets key to "1"
async def deactivate(redis) -> None: ...  # deletes key
async def is_killed(redis) -> bool: ...   # checks key, handles decode_responses=True
```

**Important:** The kill switch is **cooperative** — agents check it at each step boundary.
Maximum latency before a running goal stops = one agent timeout (default 120s).
All goal executors call `is_killed()` at the start of every step.

### Activity Log

Every significant event is appended to the `activity_log` PostgreSQL table by `safety/activity_logger.py`:

```python
async def log_event(
    db: AsyncSession,
    event_type: str,          # e.g. "goal.started", "approval.requested", "agent.run"
    entity_type: str | None,  # e.g. "goal", "agent", "file"
    entity_id: str | None,    # e.g. goal UUID, agent name
    description: str,         # human-readable summary
    payload: dict = {},       # structured data
) -> None: ...
```

---

## HOW TO ADD A NEW AGENT

1. Create `agents/new_agent.py` extending `BaseAgent`
2. Define its `AgentTask` subclass with any extra fields
3. Define its output model extending `AgentResult`
4. Register it in `agents/orchestrator.py` routing rules
5. Add its model and tools to `docker-compose.yml` if needed
6. Add API endpoint in `api/routers/agents.py` if user-facing
7. Document it in this file under a new section

```python
# agents/base_agent.py
class BaseAgent(ABC):
    name: str
    model: str
    tools: list[BaseTool]
    
    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult: ...
    
    async def _run_with_timeout(self, task: AgentTask) -> AgentResult:
        """Wraps run() with timeout and logging."""
```

---

## EXAMPLE MULTI-AGENT TASK TRACE

User says: *"Research the AI coding assistant market and write a 2-page report"*

```
1. API receives request → POST /api/v1/agents/run
   { "instruction": "Research the AI coding assistant market and write a 2-page report" }

2. Orchestrator.classify_task() → ["research", "writing"]  (multi-agent workflow)

3. Orchestrator.inject_memory() → adds relevant past research from vector memory

4. LangGraph StateGraph starts:
   
   Node: research_agent
   ├─ Tool: web_search("AI coding assistant market 2024")
   ├─ Tool: web_search("GitHub Copilot Cursor Tabnine market share")
   ├─ Tool: memory_search("coding assistant research")
   └─ Output: ResearchOutput { summary, key_findings, sources }

   Node: writing_agent
   ├─ Input: ResearchOutput from previous node
   ├─ Tool: template_load("market_report")
   └─ Output: WritingOutput { title, content (full Markdown report), word_count }

5. Orchestrator assembles final AgentResult
   └─ output = WritingOutput.content
   └─ sources = ResearchOutput.sources
   └─ artifacts = [{ type: "markdown", content: "..." }]

6. API streams response back to frontend
7. Result saved to agent_runs table
8. Summary stored in long-term memory
```

---

## AGENT SECURITY RULES

- Agents can **only write files** to `/home/user/ai-lab/outputs/` — never elsewhere
- Agents can **never** execute shell commands outside the `shell_safe` allowlist
- Agents can **never** make network requests outside the Docker network (except `web_search` via proxy)
- Agents can **never** read `/etc/`, `/root/`, or system directories
- All agent tool inputs are validated with Pydantic before execution
- Agent outputs are sanitized before being stored in the database
