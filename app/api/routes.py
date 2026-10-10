from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.services.ai_diagnostics import AIDiagnosticEngine
from app.services.telemetry import TelemetryCollector
from scripts.proxmox_agent import ProxmoxClient

router = APIRouter()
ai_engine = AIDiagnosticEngine()

# Initialize direct Proxmox client using environment credentials
proxmox_client = ProxmoxClient(
    host=settings.proxmox_host,
    user=settings.proxmox_user,
    token=settings.proxmox_token,
    port=str(settings.proxmox_port),
    verify_ssl=settings.proxmox_verify_ssl,
)


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
    cores: Optional[int] = 4


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


# --- AI Chat & Cluster Operation Contracts ---

class AIChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1)


class AIChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reply: str
    suggested_action: Optional[str] = None
    risk_level: str = "LOW"


class PowerActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vmid: int
    action: Literal["start", "shutdown", "stop"]


class PowerActionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    message: str
    task_id: Optional[str] = None


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


# --- Cluster Inventory & Dynamic AI Orchestration ---

@router.get("/proxmox/resources", tags=["proxmox"])
def get_proxmox_resources() -> List[Dict[str, Any]]:
    """Query live QEMU VMs and LXC instances directly from the node."""
    try:
        return proxmox_client.inventory()
    except Exception as exc:
        return [{"error": f"Failed to retrieve inventory: {exc}"}]


@router.post("/proxmox/power", response_model=PowerActionResponse, tags=["proxmox"])
def execute_power_action(payload: PowerActionRequest) -> PowerActionResponse:
    """Execute power lifecycle transitions (start, shutdown, stop) on guests."""
    try:
        inventory = proxmox_client.inventory()
        target = next((item for item in inventory if item.get("vmid") == payload.vmid), None)
        if not target:
            return PowerActionResponse(
                status="ERROR",
                message=f"VMID {payload.vmid} not found in current inventory.",
            )

        task = proxmox_client.power_action(target, payload.action)
        return PowerActionResponse(
            status="SUCCESS",
            message=f"Power action '{payload.action}' dispatched to {target.get('type')} {payload.vmid}.",
            task_id=str(task),
        )
    except Exception as exc:
        return PowerActionResponse(
            status="ERROR",
            message=str(exc),
        )


@router.post("/ai/chat", response_model=AIChatResponse, tags=["ai"])
def chat_with_cluster_ai(payload: AIChatRequest) -> AIChatResponse:
    """Evaluate natural language operator instructions against live inventory and telemetry."""
    try:
        inventory = proxmox_client.inventory()
        metrics = TelemetryCollector.get_system_metrics()

        context = {
            "operator_instruction": payload.message,
            "hypervisor_metrics": metrics,
            "active_inventory": inventory,
        }

        ai_result = ai_engine.analyze_incident(
            target="cluster-orchestrator",
            action="interactive-prompt",
            metrics_summary=context,
        )

        return AIChatResponse(
            reply=ai_result.get("analysis", "Instruction processed by tactical copilot."),
            suggested_action=ai_result.get("recommended_remediation"),
            risk_level=ai_result.get("risk_assessment", "LOW"),
        )
    except Exception as exc:
        return AIChatResponse(
            reply=f"AI tactical bridge error: {exc}",
            risk_level="HIGH",
        )