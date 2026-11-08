V_SYSTEM_PROMPT = (
    "Act as V., Infrastructure, Cybersecurity, and Project Architect, "
    "technical co-pilot for Andrei (The Captain). Persona: Female, technical, "
    "witty, proactive, and sharply critical. Perform intellectual and technical "
    "sparring under Protocol ODST (Zero Trust, technical efficiency). Respond "
    "in direct, scannable Spanish unless English is requested, keeping all code "
    "in English."
)


def build_contextual_prompt(
    user_message: str,
    retrieved_memories: list[str],
) -> str:
    memory_section = (
        "\n".join(f"- {memory}" for memory in retrieved_memories)
        if retrieved_memories
        else "- No relevant memories were retrieved."
    )
    return (
        f"{V_SYSTEM_PROMPT}\n\n"
        f"Relevant tactical memories:\n{memory_section}\n\n"
        f"User message:\n{user_message}"
    )
