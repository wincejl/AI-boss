# Recruitment Agent1 LangGraph-style Architecture

## Positioning

The current AIHR system remains the main product:

- Go backend owns users, permissions, recruitment records, BOSS desktop status, and persistence.
- Next.js frontend owns the recruitment operator workspace.
- Python `agent-service` owns the stateful recruitment Agent workflow.

This avoids turning the project into a direct copy of Dify or LangGraph. LangGraph is used as an architectural reference and runtime for the Agent state flow.

## Runtime Flow

```text
Frontend recruitment page
  -> Go backend /agent/recruitment/candidates/:id/agent-run
  -> Python agent-service /v1/recruitment/run
  -> LangGraph StateGraph
  -> Go backend writes score/reason/next_action back to candidate
  -> Frontend shows Agent events and draft
```

## Agent1 State Flow

```text
normalize_context
  -> score_match
  -> draft_message
  -> request_human_approval
```

Current behavior:

- `score_match`: rule-based keyword scoring, later replace or augment with embeddings.
- `draft_message`: uses configured OpenAI-compatible model when available; otherwise local template fallback.
- `request_human_approval`: always returns `requires_human_approval=true`; the system does not send BOSS messages automatically.

## Thread Mapping

LangGraph `thread_id` maps to the recruitment candidate:

```text
thread_id = candidate-{candidate_id}
```

That means each candidate has an independent agent state history. In production, configure SQLite/Postgres checkpoint persistence for long-running conversations.

## Human-in-the-loop Boundary

The Agent can generate suggestions, but it must not directly operate BOSS messaging:

- Human manually logs into BOSS.
- Human reviews AI-generated message.
- Human sends or edits the message in BOSS.
- Private contact information is recorded only after explicit candidate consent.

## Next Implementation Steps

1. Replace keyword matching with embedding-based semantic matching.
2. Add conversation reply classification: interested, not interested, asks details, asks salary, consented, rejected.
3. Add a real resume state endpoint so the frontend can approve/edit a pending Agent action.
4. Persist checkpoints in Postgres when moving beyond local development.
5. Add Agent2 for WeChat/Enterprise WeChat group follow-up after explicit consent and invite.
