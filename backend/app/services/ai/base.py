from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.services.ai.schema import PodExtractionResult


@dataclass
class TripContext:
    """Expected trip values given to the provider purely as context; validation is done separately."""

    trip_reference: str
    lr_number: str
    consignee_name: str | None
    client_name: str


class AIProviderError(Exception):
    """kind: timeout | rate_limit | unavailable | invalid_output | unsupported_image | network | not_configured"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def analyze_pod(self, image_bytes: bytes, media_type: str, context: TripContext) -> PodExtractionResult:
        """Return strictly-validated structured extraction or raise AIProviderError."""
