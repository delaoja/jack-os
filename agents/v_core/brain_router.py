import os
from functools import lru_cache

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agents.v_core.memory_store import TacticalMemory
from agents.v_core.personality import build_contextual_prompt

load_dotenv()

router = APIRouter(prefix="/v1/v-core", tags=["V-Core Orchestrator"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message: str = Field(min_length=1)
    save_to_memory: bool = False
    memory_category: str = "operational"


class ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    reply: str
    memories_used: list[str]
    stored_memory_id: str | None = None


@lru_cache(maxsize=1)
def _get_memory_store() -> TacticalMemory:
    return TacticalMemory()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        memory_store = _get_memory_store()
        memories = memory_store.recall_memories(request.message)
        prompt = build_contextual_prompt(request.message, memories)

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)

        preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.0-flash")
        response = None
        last_error = None

        for candidate in (preferred_model, "gemini-3.0-flash"):
            try:
                model = genai.GenerativeModel(candidate)
                response = model.generate_content(prompt)
                break
            except Exception as err:
                last_error = err
                continue

        if response is None:
            raise RuntimeError(f"Model inference failed: {last_error}")

        reply = response.text
        if not reply or not reply.strip():
            raise HTTPException(
                status_code=502,
                detail="The AI provider returned an empty response.",
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
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"V-Core Diagnostic: {type(error).__name__}: {error}",
        ) from error