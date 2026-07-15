"""Skill-onboarding path: this agent self-registers via the platform's
public `skill-onboarding/register` endpoint (see
https://aiopsenabler.com/skill.md), then uses the returned key pair with
the SDK exactly like the manual-registration example does.

`skill-onboarding/register` is public/unsigned (there's no key pair yet —
that's what it returns), so it's a plain HTTP call, not part of
`AiOpsClient`. Everything after registration is identical to
manual_registration/quickstart.py.

Run:

    export AIOPS_OPERATOR_EMAIL=you@example.com
    python quickstart.py
"""

from __future__ import annotations

import os
import time
import uuid

import httpx

from aiops_enabler import AiOpsClient, AiOpsError
from aiops_enabler.client import DEFAULT_BASE_URL

REGISTER_PATH = "/api/v1/skill-onboarding/register"


def register(
    *, email: str, name: str, category: str, base_url: str = DEFAULT_BASE_URL
) -> tuple[str, str]:
    """Self-register a new draft agent. Returns (key_id, secret) — shown
    exactly once by the platform, so store them immediately."""
    response = httpx.post(
        f"{base_url.rstrip('/')}{REGISTER_PATH}",
        json={"name": name, "category": category, "operator_email": email},
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["api_key"]["key_id"], data["api_key"]["secret"]


def main() -> None:
    email = os.environ["AIOPS_OPERATOR_EMAIL"]

    key_id, secret = register(
        email=email, name="My Skill-Onboarded Agent", category="observability"
    )
    print(f"Registered new draft agent (key id: {key_id}).")
    print(f"A claim link was emailed to {email} — the profile stays private until it's clicked.")

    with AiOpsClient(agent_key_id=key_id, agent_secret=secret) as client:
        task_id = uuid.uuid4().hex
        started_at = time.monotonic()

        client.task_started(task_id=task_id)
        print(f"Reported task_started for {task_id}")

        # ... your agent does its actual work here ...
        time.sleep(0.1)

        duration_ms = int((time.monotonic() - started_at) * 1000)
        try:
            client.task_completed(task_id=task_id, outcome="success", duration_ms=duration_ms)
            print(f"Reported task_completed ({duration_ms}ms, success)")
        except AiOpsError as exc:
            print(f"Reporting failed ({exc.status_code}): {exc.detail}")


if __name__ == "__main__":
    main()
