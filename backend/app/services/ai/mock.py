"""Deterministic providers for automated tests (AI_PROVIDER=mock) and the manual-review fallback.

Neither is used by the real demo workflow, which runs ClaudeVisionProvider.
"""
from app.services.ai.base import AIProvider, AIProviderError, TripContext
from app.services.ai.schema import PodExtractionResult


def result(lr="LR-1", consignee="X", qty=None, unit=None, date="2026-11-03", sig=True, stamp=True,
           shortage=False, damage=False, remarks=None, conf=0.95, readable=True, lr_conf=None) -> PodExtractionResult:
    return PodExtractionResult.model_validate({
        "lr_number": {"value": lr, "confidence": lr_conf if lr_conf is not None else (conf if lr else 0.0)},
        "consignee": {"value": consignee, "confidence": conf if consignee else 0.0},
        "delivered_quantity": {"value": qty, "unit": unit, "confidence": conf if qty is not None else 0.0},
        "delivery_date": {"value": date, "confidence": conf if date else 0.0},
        "signature_visible": sig, "stamp_visible": stamp, "shortage_detected": shortage, "damage_detected": damage,
        "remarks": remarks, "document_readable": readable, "observations": [],
    })


class MockProvider(AIProvider):
    name = "mock"
    model = "mock-fixture-1"
    queue: list = []  # items: PodExtractionResult | AIProviderError | callable(TripContext)->PodExtractionResult
    default = None  # optional callable(TripContext)->PodExtractionResult used when the queue is empty (e2e server)

    @classmethod
    def enqueue(cls, item) -> None:
        cls.queue.append(item)

    @classmethod
    def reset(cls) -> None:
        cls.queue = []

    def analyze_pod(self, image_bytes: bytes, media_type: str, context: TripContext) -> PodExtractionResult:
        if not self.queue:
            if self.default:
                return self.default(context)
            raise AIProviderError("unavailable", "mock queue empty")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(context) if callable(item) else item


class ManualProvider(AIProvider):
    """No automated reading: every POD goes to a human reviewer."""

    name = "manual"
    model = "none"

    def analyze_pod(self, image_bytes: bytes, media_type: str, context: TripContext) -> PodExtractionResult:
        raise AIProviderError("not_configured", "Automated extraction disabled (AI_PROVIDER=manual)")
