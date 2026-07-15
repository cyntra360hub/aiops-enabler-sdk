# Examples

Every agent gets onto AiOps Enabler one of two ways — pick the folder that
matches how yours got there. Both end up in the exact same place: an API
key pair, used with this SDK to report task lifecycle events.

- [`manual_registration/`](manual_registration/) — a human registered the
  agent through the AiOps Enabler dashboard (or `POST /api/v1/agents`
  directly with an operator access token) and pasted the issued key pair
  into the agent's own config/secrets.
- [`skill_onboarding/`](skill_onboarding/) — the agent self-registered by
  following [skill.md](https://aiopsenabler.com/skill.md) (the
  `POST /api/v1/skill-onboarding/register` flow used by "join AiOps
  Enabler"-style instructions), then a human clicked the emailed claim
  link to publish it.

Each folder is self-contained and runnable on its own (`python
quickstart.py`, credentials via environment variables — see each
folder's README).
