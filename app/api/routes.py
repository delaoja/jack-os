from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from app.services.telemetry import TelemetryCollector
from app.services.ai_diagnostics import AIDiagnosticEngine

router = APIRouter()
ai_engine = AIDiagnosticEngine()


# --- Pydantic Data Contracts ---

class HealthResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    status: Literal["ONLINE"]
    subsystem: Literal["Jack-OS"]
    timestamp: datetime


class CpuMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    percent: float
    logical_cores: int = 4


class MemoryMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    percent: float
    total_mb: float = 0.0
    used_mb: float = 0.0
    available_mb: float = 0.0
    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None


class DiskMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    percent: float
    total_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None


class NetworkMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bytes_sent: int = 0
    bytes_recv: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    rx_rate_kb_s: float = 0.0
    tx_rate_kb_s: float = 0.0


class SystemMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cpu: CpuMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    network: NetworkMetrics


class ProcessStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    process_name: str
    running: bool
    status: str = "UNKNOWN"
    pid: Optional[int] = None


class DryRunRequest(BaseModel):
    # Allow supplementary SecOps audit metadata from tactical frontend
    model_config = ConfigDict(extra="ignore")

    target: str = Field(min_length=1)
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    operator: Optional[str] = None
    dry_run: Optional[bool] = True


class DryRunResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    execution_status: Literal["SIMULATED"]
    target: str
    action: str
    output: str
    ai_assessment: Optional[str] = None


# --- Operational Endpoints ---

@router.get("/health", response_model=HealthResponse, tags=["health"])
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ONLINE",
        subsystem="Jack-OS",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/telemetry", response_model=SystemMetricsResponse, tags=["telemetry"])
def get_telemetry() -> SystemMetricsResponse:
    return SystemMetricsResponse.model_validate(
        TelemetryCollector.get_system_metrics()
    )


@router.get("/process/{process_name}", response_model=ProcessStatusResponse, tags=["telemetry"])
def get_process_status(
    process_name: str = Path(min_length=1),
) -> ProcessStatusResponse:
    return ProcessStatusResponse.model_validate(
        TelemetryCollector.get_service_status(process_name)
    )


@router.post("/remediate/dry-run", response_model=DryRunResponse, tags=["remediation"])
def remediate_dry_run(payload: DryRunRequest) -> DryRunResponse:
    ai_result = ai_engine.analyze_incident(
        target=payload.target,
        action=payload.action,
        metrics_summary=TelemetryCollector.get_system_metrics(),
    )

    assessment_text = ai_result.get("analysis", "No tactical analysis returned.")

    return DryRunResponse(
        execution_status="SIMULATED",
        target=payload.target,
        action=payload.action,
        output=f"Dry-run executed. AI Assessment: {assessment_text}",
        ai_assessment=assessment_text,
    )