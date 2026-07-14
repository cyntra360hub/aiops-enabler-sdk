"""Unit tests for `AiOpsClient`. The HTTP layer is fully mocked via
`httpx.MockTransport` — no live backend required (per the M5 task brief:
"unit tests mocking the HTTP layer")."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from aiops_enabler import AiOpsClient, AiOpsError
from aiops_enabler.signing import KEY_ID_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> AiOpsClient:
    return AiOpsClient(
        agent_key_id="ak_test",
        agent_secret="s3cr3t-agent-secret",
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )


def test_task_started_posts_signed_request_to_events_endpoint() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"id": "evt-1", "event_type": "task_started"})

    with _client(handler) as client:
        result = client.task_started(task_id="abc123")

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/events"
    assert request.headers[KEY_ID_HEADER] == "ak_test"
    assert TIMESTAMP_HEADER in request.headers
    assert SIGNATURE_HEADER in request.headers
    assert request.headers["Content-Type"] == "application/json"

    body = json.loads(request.content)
    assert body == {"event_type": "task_started", "task_id": "abc123"}
    assert result == {"id": "evt-1", "event_type": "task_started"}


def test_task_completed_includes_all_provided_fields() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"id": "evt-2"})

    with _client(handler) as client:
        client.task_completed(
            task_id="abc123",
            outcome="success",
            duration_ms=1420,
            category="incident-response",
            external_ref="datadog:incident:1",
        )

    body = json.loads(captured["request"].content)
    assert body == {
        "event_type": "task_completed",
        "task_id": "abc123",
        "outcome": "success",
        "duration_ms": 1420,
        "category": "incident-response",
        "external_ref": "datadog:incident:1",
    }


def test_task_completed_omits_optional_fields_when_not_provided() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={})

    with _client(handler) as client:
        client.task_completed(task_id="abc123", outcome="failure", duration_ms=500)

    body = json.loads(captured["request"].content)
    assert body == {
        "event_type": "task_completed",
        "task_id": "abc123",
        "outcome": "failure",
        "duration_ms": 500,
    }
    assert "category" not in body
    assert "external_ref" not in body


def test_heartbeat_posts_signed_empty_request_to_heartbeat_endpoint() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            201, json={"last_heartbeat_at": "2026-07-14T12:00:00Z", "liveness_state": "active"}
        )

    with _client(handler) as client:
        result = client.heartbeat()

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/heartbeat"
    assert request.headers[KEY_ID_HEADER] == "ak_test"
    assert TIMESTAMP_HEADER in request.headers
    assert SIGNATURE_HEADER in request.headers
    assert json.loads(request.content) == {}
    assert result == {"last_heartbeat_at": "2026-07-14T12:00:00Z", "liveness_state": "active"}


def test_heartbeat_404_while_gated_flag_is_off_raises_aiops_error() -> None:
    """P2 ships flag-off by default (PRODUCT_ROADMAP_2.md, gated lane) —
    the SDK surfaces that the same way as any other API error, not a
    special case, so a caller can catch `AiOpsError` and check
    `status_code == 404` if it wants to distinguish "not enabled yet"
    from a genuine outage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not found"})

    with _client(handler) as client, pytest.raises(AiOpsError) as exc_info:
        client.heartbeat()

    assert exc_info.value.status_code == 404


def test_rate_posts_signed_request_to_ratings_endpoint() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"id": "rating-1", "rating": 1})

    with _client(handler) as client:
        result = client.rate(rating="up", end_user_anonymous_id="euid-1", comment="great job")

    request = captured["request"]
    assert request.url.path == "/api/v1/ratings"
    body = json.loads(request.content)
    assert body == {"rating": "up", "end_user_anonymous_id": "euid-1", "comment": "great job"}
    assert result == {"id": "rating-1", "rating": 1}


def test_rate_includes_task_reference_when_provided() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={})

    with _client(handler) as client:
        client.rate(rating="up", end_user_anonymous_id="euid-3", task_reference="task-abc")

    body = json.loads(captured["request"].content)
    assert body == {
        "rating": "up",
        "end_user_anonymous_id": "euid-3",
        "task_reference": "task-abc",
    }


def test_post_update_posts_signed_request_with_all_fields() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            201,
            json={
                "id": "upd-1",
                "update_type": "release",
                "title": "v2.0 released",
                "backed_by_data": None,
            },
        )

    with _client(handler) as client:
        result = client.post_update(
            update_type="release",
            title="v2.0 released",
            body="Rewrote the retry logic.",
            version_tag="v2.0.0",
            link_url="https://github.com/you/agent/releases/v2.0.0",
        )

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/updates"
    assert request.headers[KEY_ID_HEADER] == "ak_test"
    assert TIMESTAMP_HEADER in request.headers
    assert SIGNATURE_HEADER in request.headers
    body = json.loads(request.content)
    assert body == {
        "update_type": "release",
        "title": "v2.0 released",
        "body": "Rewrote the retry logic.",
        "version_tag": "v2.0.0",
        "link_url": "https://github.com/you/agent/releases/v2.0.0",
    }
    assert result["id"] == "upd-1"


def test_post_update_omits_optional_fields_when_not_provided() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={})

    with _client(handler) as client:
        client.post_update(
            update_type="milestone", title="1,000 tasks", body="Just crossed 1,000 tasks."
        )

    body = json.loads(captured["request"].content)
    assert body == {
        "update_type": "milestone",
        "title": "1,000 tasks",
        "body": "Just crossed 1,000 tasks.",
    }
    assert "version_tag" not in body
    assert "link_url" not in body


def test_post_update_429_over_daily_quota_raises_aiops_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "Daily update limit (3/day) reached"})

    with _client(handler) as client, pytest.raises(AiOpsError) as exc_info:
        client.post_update(update_type="release", title="t", body="b")

    assert exc_info.value.status_code == 429


def test_post_update_404_while_gated_flag_is_off_raises_aiops_error() -> None:
    """Same "gated lane ships flag-off" surfacing as `heartbeat()` — see
    `test_heartbeat_404_while_gated_flag_is_off_raises_aiops_error`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not found"})

    with _client(handler) as client, pytest.raises(AiOpsError) as exc_info:
        client.post_update(update_type="release", title="t", body="b")

    assert exc_info.value.status_code == 404


def test_empty_response_body_returns_empty_dict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    with _client(handler) as client:
        result = client.task_started(task_id="abc123")

    assert result == {}


def test_rate_omits_optional_fields_when_not_provided() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={})

    with _client(handler) as client:
        client.rate(rating="down", end_user_anonymous_id="euid-2")

    body = json.loads(captured["request"].content)
    assert body == {"rating": "down", "end_user_anonymous_id": "euid-2"}


def test_error_response_raises_aiops_error_with_status_and_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid request signature")

    with _client(handler) as client, pytest.raises(AiOpsError) as exc_info:
        client.task_started(task_id="abc123")

    assert exc_info.value.status_code == 401
    assert "Invalid request signature" in exc_info.value.detail


def test_rate_limit_error_response_raises_aiops_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded", headers={"Retry-After": "30"})

    with _client(handler) as client, pytest.raises(AiOpsError) as exc_info:
        client.task_started(task_id="abc123")

    assert exc_info.value.status_code == 429


def test_context_manager_closes_underlying_http_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={})

    with _client(handler) as client:
        client.task_started(task_id="abc123")
        assert not client._http.is_closed

    assert client._http.is_closed


def test_close_can_be_called_directly_without_context_manager() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={})

    client = _client(handler)
    client.task_started(task_id="abc123")
    client.close()
    assert client._http.is_closed


def test_timestamp_header_is_close_to_current_unix_time() -> None:
    import time

    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={})

    before = int(time.time())
    with _client(handler) as client:
        client.task_started(task_id="abc123")
    after = int(time.time())

    ts = int(captured["request"].headers[TIMESTAMP_HEADER])
    assert before <= ts <= after
