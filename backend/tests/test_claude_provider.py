"""Contract tests for the Claude adapter using a stubbed HTTP layer (no network, no API key needed)."""
import httpx
import pytest

from app.services.ai.base import AIProviderError, TripContext
from app.services.ai.claude import ClaudeVisionProvider

CTX = TripContext("TRP-1", "LR-66141", "Indore Warehouse", "Company D")
VALID = {
    "lr_number": {"value": "LR-66141", "confidence": 0.98}, "consignee": {"value": "Indore Warehouse", "confidence": 0.94},
    "delivered_quantity": {"value": 94, "unit": "cartons", "confidence": 0.97}, "delivery_date": {"value": "2026-11-03", "confidence": 0.91},
    "signature_visible": True, "stamp_visible": True, "shortage_detected": True, "damage_detected": False,
    "remarks": "Short by 6 cartons", "document_readable": True, "observations": [],
}


def fake(monkeypatch, status=200, body=None, exc=None, capture=None):
    def post(url, json=None, headers=None, timeout=None):
        if capture is not None:
            capture.update(url=url, json=json, headers=headers, timeout=timeout)
        if exc:
            raise exc
        return httpx.Response(status, json=body if body is not None else {}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)


def tool_use(inp):
    return {"content": [{"type": "text", "text": "ok"}, {"type": "tool_use", "name": "record_pod_extraction", "input": inp}]}


def test_success_parses_and_request_shape(monkeypatch):
    cap = {}
    fake(monkeypatch, body=tool_use(VALID), capture=cap)
    res = ClaudeVisionProvider(api_key="k", model="claude-test").analyze_pod(b"\xff\xd8img", "image/jpeg", CTX)
    assert res.delivered_quantity.value == 94 and res.shortage_detected is True
    body = cap["json"]
    assert body["model"] == "claude-test" and body["tools"][0]["name"] == "record_pod_extraction" and body["tool_choice"] == {"type": "auto"}
    assert body["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"
    assert cap["headers"]["x-api-key"] == "k"
    assert "LR-66141" not in str(body["messages"])  # expected values are not leaked to the model as hints


@pytest.mark.parametrize("kw,kind", [
    (dict(status=429), "rate_limit"), (dict(status=500), "unavailable"), (dict(status=529), "unavailable"),
    (dict(status=401), "not_configured"), (dict(status=400), "unsupported_image"),
    (dict(exc=httpx.ReadTimeout("t")), "timeout"), (dict(exc=httpx.ConnectError("x")), "network"),
    (dict(body={"content": [{"type": "text", "text": "I cannot read this"}]}), "invalid_output"),
    (dict(body=tool_use({**VALID, "invented_field": 1})), "invalid_output"),
    (dict(body=tool_use({**VALID, "lr_number": {"value": "x", "confidence": 3}})), "invalid_output"),
])
def test_failures_map_to_typed_errors(monkeypatch, kw, kind):
    fake(monkeypatch, **kw)
    with pytest.raises(AIProviderError) as e:
        ClaudeVisionProvider(api_key="k").analyze_pod(b"x", "image/jpeg", CTX)
    assert e.value.kind == kind


def test_missing_key_and_unsupported_type():
    with pytest.raises(AIProviderError) as e:
        ClaudeVisionProvider(api_key="").analyze_pod(b"x", "image/jpeg", CTX)
    assert e.value.kind == "not_configured"
    with pytest.raises(AIProviderError) as e:
        ClaudeVisionProvider(api_key="k").analyze_pod(b"x", "application/pdf", CTX)
    assert e.value.kind == "unsupported_image"
