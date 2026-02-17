# app/agent/state.py
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class RequestSource(str, Enum):
    API = "api"
    CLI = "cli"
    WEB = "web"


class RunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject unknown fields

    userInput: str
    traceId: str
    timezone: str = "America/New_York"
    runId: Optional[str] = None
    idempotencyKey: Optional[str] = None
    requestSource: RequestSource = RequestSource.API
    modelInfo: Optional[Dict[str, Any]] = None


class StepOutcome(str, Enum):
    OK = "ok"
    RETRY = "retry"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")  # planner can't invent random keys

    stepId: str
    action: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    successCriteria: List[str] = Field(default_factory=list)
    fallback: Optional[str] = None

    dependsOn: List[str] = Field(default_factory=list)
    timeout_s: Optional[float] = None
    maxRetries: Optional[int] = None
    tags: List[str] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: Optional[str] = None
    steps: List[PlanStep] = Field(default_factory=list)


class StructuredError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    errorType: str
    errorMessage: str
    errorDetails: Dict[str, Any] = Field(default_factory=dict)
    stepId: Optional[str] = None
    attempt: Optional[int] = None
    retryable: bool = False


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    toolName: str
    requestPayload: Dict[str, Any] = Field(default_factory=dict)
    responsePayload: Optional[Dict[str, Any]] = None


class StepRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stepId: str
    attempt: int = 1
    startedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    endedAt: Optional[datetime] = None
    durationMs: Optional[int] = None  # computed by executor when endedAt is set

    outcome: StepOutcome = StepOutcome.OK
    call: Optional[ToolCall] = None
    error: Optional[StructuredError] = None
    observations: Dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: List[StepRun] = Field(default_factory=list)


# Artifacts

class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceId: str
    chunkId: str
    text: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CalendarEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventId: str
    title: str
    startTime: str
    endTime: str
    attendees: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Artifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: List[Evidence] = Field(default_factory=list)
    calendarEvent: Optional[CalendarEvent] = None
    finalReport: Optional[str] = None
    citations: List[Dict[str, Any]] = Field(default_factory=list)

    # Gmail/Applications tracker artifacts (optional; safe to keep even if unused now)
    emailSummaries: List[Dict[str, Any]] = Field(default_factory=list)      # e.g., {messageId, threadId, from, subject, date}
    applications: List[Dict[str, Any]] = Field(default_factory=list)        # parsed application rows
    exportPath: Optional[str] = None                                       # excel export path


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    endedAt: Optional[datetime] = None
    totalDurationMs: Optional[int] = None

    tokens: Dict[str, int] = Field(default_factory=dict)
    costEstimateUsd: Optional[float] = None


class AgentState(BaseModel):
    # Enums dump as plain strings (nice for API/UI)
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    context: RunContext

    status: AgentStatus = AgentStatus.RUNNING
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    endedAt: Optional[datetime] = None

    requestIntent: Dict[str, Any] = Field(default_factory=dict)
    plan: Plan = Field(default_factory=Plan)
    trace: ExecutionTrace = Field(default_factory=ExecutionTrace)

    artifacts: Artifacts = Field(default_factory=Artifacts)
    errors: List[StructuredError] = Field(default_factory=list)

    telemetry: Telemetry = Field(default_factory=Telemetry)
    scratch: Dict[str, Any] = Field(default_factory=dict)