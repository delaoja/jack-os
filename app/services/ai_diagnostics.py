import os
from google import genai
from app.config import settings


class AIDiagnosticEngine:
    """Evaluates telemetry spikes and generates tactical remediation recommendations."""

    def __init__(self):
        self.api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY")
        self.model_name = settings.gemini_model
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def analyze_incident(self, target: str, action: str, metrics_summary: dict) -> dict:
        if not self.client:
            return {
                "engine": "SIMULATED_HEURISTIC",
                "analysis": "Google API Key not detected. Falling back to rule-based evaluation.",
                "recommendation": "Check API key configuration in .env.",
            }

        prompt = f"""
        Act as an autonomous SecOps and Site Reliability Engineer for a bare-metal hypervisor cluster.
        Analyze the following remediation action:
        - Target Subsystem: {target}
        - Action Requested: {action}
        - Current Metrics: {metrics_summary}

        Provide a concise tactical assessment:
        1. Blast radius risk (LOW, MEDIUM, HIGH, CRITICAL).
        2. Expected impact on node stability.
        3. Recommended pre-flight validation check.
        Keep the response brief, technical, and formatted in clear bullet points.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            return {
                "engine": f"GEMINI ({self.model_name})",
                "analysis": response.text.strip(),
            }
        except Exception as e:
            return {
                "engine": "AI_DISPATCH_ERROR",
                "analysis": f"Diagnostic call failed: {str(e)}",
            }