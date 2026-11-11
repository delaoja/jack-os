import os
import requests
from functools import lru_cache

from google import genai
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agents.v_core.memory_store import TacticalMemory
from agents.v_core.personality import build_contextual_prompt
from agents.v_core.sensors import get_local_telemetry, get_proxmox_telemetry, get_gpu_telemetry

load_dotenv()

router = APIRouter(prefix="/v1/v-core", tags=["V-Core Orchestrator"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message: str = Field(min_length=1)
    save_to_memory: bool = False
    memory_category: str = "operational"
    provider: str = "gemini"  # Inversión táctica: Nube por defecto para fluidez
    local_model: str = "llama3.1"


class ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    reply: str
    memories_used: list[str]
    stored_memory_id: str | None = None
    provider_used: str


@lru_cache(maxsize=1)
def _get_memory_store() -> TacticalMemory:
    return TacticalMemory()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        memory_store = _get_memory_store()
        
        # 1. Retrieve Vector Memories (Qdrant)
        memories = memory_store.recall_memories(request.message)
        
        # 2. Fetch Live Telemetry (La Legion + the-banished)
        local_data = get_local_telemetry()
        gpu_data = get_gpu_telemetry()
        proxmox_data = get_proxmox_telemetry()
        
        # 3. Build Base Prompt
        base_prompt = build_contextual_prompt(request.message, memories)
        
        # 4. Inject Telemetry & ODST Tactical Lock
        telemetry_inject = (
            f"\n\n[SYSTEM BACKGROUND DATA - SILENT INGESTION]\n"
            f"La Legion (Local): {local_data} | {gpu_data}\n"
            f"the-banished (HQ): {proxmox_data}\n\n"
            f"CRITICAL DIRECTIVE: You are V. Execute Protocol ODST. "
            f"DO NOT use generic greetings (e.g., 'Hola', 'Me alegra verte'). DO NOT be chatty. "
            f"CONDITIONAL TELEMETRY RULE: You currently hold live system data in context. ONLY output hardware telemetry, temperatures, or node status if the user EXPLICITLY asks for a status report, diagnostic, or system update. "
            f"If the user asks about non-technical topics (e.g., food, casual conversation, advice), IGNORE the telemetry entirely and answer directly, maintaining the cold, tactical ODST persona. "
            f"If telemetry is requested, use strict scannable bullet points."
        )
        prompt = base_prompt + telemetry_inject

        reply = ""
        actual_provider = request.provider

        # --- ROUTE A: LOCAL INFERENCE (RTX 4060) ---
        if request.provider == "ollama":
            ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434/api/generate")
            payload = {
                "model": request.local_model,
                "prompt": prompt,
                "stream": False
            }
            try:
                res = requests.post(ollama_url, json=payload, timeout=120)
                res.raise_for_status()
                reply = res.json().get("response", "")
            except Exception as e:
                print(f"[V-Core Warning] Ollama node offline or failed ({e}). Re-routing to Gemini Cloud...")
                actual_provider = "gemini_fallback"

        # --- ROUTE B: CLOUD INFERENCE (GEMINI FALLBACK OR PRIMARY) ---
        if actual_provider in ["gemini", "gemini_fallback"]:
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            
            # Nuevo cliente de la API google.genai
            client = genai.Client(api_key=api_key)
            preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.0-flash")
            
            response = client.models.generate_content(
                model=preferred_model,
                contents=prompt
            )
            reply = response.text

        if not reply or not reply.strip():
            raise HTTPException(
                status_code=502,
                detail="The selected AI provider returned an empty response.",
            )

        stored_memory_id = None
        if request.save_to_memory:
            stored_memory_id = memory_store.store_memory(
                request.message,
                category=request.memory_category,
            )

        return ChatResponse(
            reply=reply.strip(),
            memories_used=memories,
            stored_memory_id=stored_memory_id,
            provider_used=actual_provider
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"V-Core Diagnostic: {type(error).__name__}: {error}",
        ) from error