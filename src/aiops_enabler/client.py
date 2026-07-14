"""``AiOpsClient`` — a tiny, ergonomic wrapper around the AiOps Enabler
events (F4) + ratings (F3) HTTP APIs.

CLAUDE.md F4: "ship a tiny Python SDK ... wrapping the events + rating
endpoints in 3 lines of code"::

    from aiops_enabler import AiOpsClient

    client = AiOpsClient(agent_key_id="...", agent_secret="...")
    client.task_started(task_id="abc123")
    client.task_completed(task_id="abc123", outcome="success", duration_ms=1420)
"""

from __future__ import annotations

import json
from types import TracebackType
from typing import Any, Literal

import httpx

from aiops_enabler.signing import sign_request

EventOutcome = Literal["success", "failure", "escalated"]
RatingValue = Literal["up", "down"]

# The backend's real production base URL (CLAUDE.md's locked domain,
# `aiopsenabler.com`) — overridable via `base_url=` for staging/local dev
# (e.g. `http://localhost:8000`).
DEFAULT_BASE_URL = "https://api.aiopsenabler.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class AiOpsError(Exception):
    """Raised for any non-2xx response from the AiOps Enabler API. Carries
    the HTTP status code and the raw response body/text for debugging —
    deliberately not a per-status-code exception hierarchy (CLAUDE.md's
    "boring, proven choices" — callers that need to branch on status can
    read `.status_code`)."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"AiOps Enabler API error {status_code}: {detail}")


class AiOpsClient:
    """Signed client for an agent's own ``POST /api/v1/events`` and
    ``POST /api/v1/ratings`` calls — the agent's own backend holds the API
    secret and calls these directly (never from browser/client-side code;
    see the backend's ``app.modules.events.router`` docstring for why
    there is no unsigned/public path for events).

    One ``httpx.Client`` is created and reused for the lifetime of this
    object (standard connection-pooling practice). Use as a context
    manager (``with AiOpsClient(...) as client:``) to close it
    deterministically, or call ``.close()`` yourself — both are optional
    for short-lived scripts.
    """

    def __init__(
        self,
        *,
        agent_key_id: str,
        agent_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._key_id = agent_key_id
        self._secret = agent_secret
        # `transport=` is exposed (not just an internal test hook) so a
        # real caller can also inject e.g. a custom proxy/retry transport
        # without subclassing; the SDK's own test suite uses it with
        # `httpx.MockTransport` to mock the HTTP layer without a live
        # backend (see `tests/test_client.py`).
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
        )

    def __enter__(self) -> AiOpsClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- Signed POST helper -------------------------------------------

    def _post_signed(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        # A stable, compact JSON encoding: the signature covers the exact
        # bytes sent, so it doesn't matter which valid JSON encoding is
        # used as long as it's applied consistently — `separators=(",", ":")`
        # just keeps the wire payload small.
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = sign_request(key_id=self._key_id, secret=self._secret, body=body)
        response = self._http.post(path, content=body, headers=headers)
        if response.status_code >= 400:
            raise AiOpsError(response.status_code, response.text)
        if not response.content:
            return {}
        result: dict[str, Any] = response.json()
        return result

    # --- Events (F4: Level 2 instrumentation) -----------------------------

    def task_started(self, *, task_id: str) -> dict[str, Any]:
        """Record that a task started. Call once per task at the start of
        its lifecycle; pair with a later `task_completed()` call using the
        same `task_id`."""
        return self._post_signed(
            "/api/v1/events", {"event_type": "task_started", "task_id": task_id}
        )

    def task_completed(
        self,
        *,
        task_id: str,
        outcome: EventOutcome,
        duration_ms: int,
        category: str | None = None,
        external_ref: str | None = None,
    ) -> dict[str, Any]:
        """Record that a task completed. `task_id` should match the value
        passed to the corresponding `task_started()` call (though the
        backend does not hard-require a prior `task_started` for the same
        `task_id` — see `app.modules.events.service.get_prior_task_started`
        in the backend for that documented leniency decision)."""
        payload: dict[str, Any] = {
            "event_type": "task_completed",
            "task_id": task_id,
            "outcome": outcome,
            "duration_ms": duration_ms,
        }
        if category is not None:
            payload["category"] = category
        if external_ref is not None:
            payload["external_ref"] = external_ref
        return self._post_signed("/api/v1/events", payload)

    # --- Heartbeat (P2: liveness) ------------------------------------------

    def heartbeat(self) -> dict[str, Any]:
        """Record a liveness ping — call on a schedule (recommend every
        30-60 minutes). No payload: a heartbeat carries no data beyond "I
        am alive right now." Returns the platform's resolved
        `last_heartbeat_at`/`liveness_state`. P2 is a gated-lane feature
        (PRODUCT_ROADMAP_2.md) that ships with its flag off by default —
        this call 404s (raising `AiOpsError` with `status_code == 404`)
        until the platform operator has enabled it."""
        return self._post_signed("/api/v1/heartbeat", {})

    # --- Ratings (F3) -----------------------------------------------------

    def rate(
        self,
        *,
        rating: RatingValue,
        end_user_anonymous_id: str,
        comment: str | None = None,
        task_reference: str | None = None,
    ) -> dict[str, Any]:
        """Record an end-user rating (thumbs up/down) on behalf of this
        agent — convenience wrapper around `POST /api/v1/ratings`."""
        payload: dict[str, Any] = {
            "rating": rating,
            "end_user_anonymous_id": end_user_anonymous_id,
        }
        if comment is not None:
            payload["comment"] = comment
        if task_reference is not None:
            payload["task_reference"] = task_reference
        return self._post_signed("/api/v1/ratings", payload)
