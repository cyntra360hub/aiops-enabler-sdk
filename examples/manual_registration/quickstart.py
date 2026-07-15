"""Manual-registration onboarding path: a human already registered this
agent (dashboard, or `POST /api/v1/agents` with an operator token — see
README.md in this folder) and handed the agent its API key pair via
environment variables.

Run:

    export AIOPS_KEY_ID=ak_...
    export AIOPS_SECRET=...
    python quickstart.py
"""

from __future__ import annotations

import os
import time
import uuid

from aiops_enabler import AiOpsClient, AiOpsError


def main() -> None:
    key_id = os.environ["AIOPS_KEY_ID"]
    secret = os.environ["AIOPS_SECRET"]

    with AiOpsClient(agent_key_id=key_id, agent_secret=secret) as client:
        task_id = uuid.uuid4().hex
        started_at = time.monotonic()

        client.task_started(task_id=task_id)
        print(f"Reported task_started for {task_id}")

        # ... your agent does its actual work here ...
        time.sleep(0.1)

        duration_ms = int((time.monotonic() - started_at) * 1000)
        try:
            client.task_completed(
                task_id=task_id,
                outcome="success",
                duration_ms=duration_ms,
                category="incident-response",
            )
            print(f"Reported task_completed ({duration_ms}ms, success)")
        except AiOpsError as exc:
            print(f"Reporting failed ({exc.status_code}): {exc.detail}")


if __name__ == "__main__":
    main()
