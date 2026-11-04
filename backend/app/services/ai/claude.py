import base64

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.services.ai.base import AIProvider, AIProviderError, TripContext
from app.services.ai.schema import EXTRACTION_TOOL, SYSTEM_PROMPT, PodExtractionResult

API_URL = "https://api.anthropic.com/v1/messages"
SUPPORTED = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _api_message(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:300]
    except ValueError:
        return ""


class ClaudeVisionProvider(AIProvider):
    """Calls the Anthropic Messages API directly over HTTPS (no SDK dependency) with forced tool use for structured JSON."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float | None = None):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.ai_api_key
        self.model = model or s.ai_model
        self.timeout = timeout or s.ai_timeout_seconds

    def analyze_pod(self, image_bytes: bytes, media_type: str, context: TripContext) -> PodExtractionResult:
        if not self.api_key:
            raise AIProviderError("not_configured", "AI_API_KEY is not configured")
        if media_type not in SUPPORTED:
            raise AIProviderError("unsupported_image", f"Unsupported image type {media_type}")
        # Expected values are deliberately NOT sent: the model should read the document, not confirm our expectations.
        body = {
            "model": self.model,
            "max_tokens": 1500,
            "system": SYSTEM_PROMPT,
            "tools": [EXTRACTION_TOOL],
            "tool_choice": {"type": "auto"},  # this model rejects forced tool_choice; the system prompt mandates the tool call and output is schema-validated
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                 "data": base64.b64encode(image_bytes).decode()}},
                    {"type": "text", "text": "Extract the proof-of-delivery fields from this photograph."},
                ],
            }],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            r = httpx.post(API_URL, json=body, headers=headers, timeout=self.timeout)
        except httpx.TimeoutException as e:
            raise AIProviderError("timeout", "AI provider timed out") from e
        except httpx.HTTPError as e:
            raise AIProviderError("network", f"Network error contacting AI provider: {type(e).__name__}") from e
        if r.status_code == 429:
            raise AIProviderError("rate_limit", "AI provider rate limit reached")
        if r.status_code >= 500 or r.status_code == 529:
            raise AIProviderError("unavailable", f"AI provider unavailable ({r.status_code})")
        if r.status_code == 400:
            raise AIProviderError("unsupported_image", f"AI provider rejected the request: {_api_message(r)}")
        if r.status_code in (401, 403):
            raise AIProviderError("not_configured", "AI provider rejected credentials")
        if r.status_code != 200:
            raise AIProviderError("unavailable", f"Unexpected AI provider status {r.status_code}")
        try:
            blocks = r.json().get("content", [])
            tool_input = next(b["input"] for b in blocks if b.get("type") == "tool_use")
            return PodExtractionResult.model_validate(tool_input)
        except (StopIteration, KeyError, ValueError, ValidationError) as e:
            raise AIProviderError("invalid_output", "AI returned output that failed schema validation") from e
