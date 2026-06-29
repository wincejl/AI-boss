# Recruitment Agent Service

This service is the Python agent layer for Recruitment Agent1. The current Go backend remains the main business system; this service owns the LangGraph-style candidate workflow:

```text
candidate input
-> normalize context
-> score match
-> draft first message
-> return human approval task
```

Run locally:

```powershell
cd E:\postgraduate_project\aihr-boss\AI-CS-master\AI-CS-master\agent-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Then point the Go backend at it:

```powershell
$env:RECRUITMENT_AGENT_URL="http://127.0.0.1:8090"
```

For Kimi, set these in `agent-service\.env` before starting the service:

```text
AGENT_LLM_API_URL=https://api.moonshot.cn/v1/chat/completions
AGENT_LLM_API_KEY=your-key
AGENT_LLM_MODEL=kimi-k2.6
AGENT_LLM_TEMPERATURE=1
```

The service never sends messages to BOSS directly. It returns a draft and `requires_human_approval=true`; the human operator still confirms before sending.
