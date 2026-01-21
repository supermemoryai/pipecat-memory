<img width="590" height="98" alt="Screenshot 2026-01-15 at 5 49 27 PM" src="https://github.com/user-attachments/assets/87e590e3-d372-4d0a-ad27-5b76b4cfeccf" />

Voice assistant with persistent memory powered by [Supermemory](https://supermemory.ai) and [Pipecat](https://pipecat.ai).

## Quick Start

```bash
bun i && bun run setup:backend
```

```bash
# backend/.env
OPENAI_API_KEY=
SUPERMEMORY_API_KEY=
```

```bash
bun run dev:backend
bun run dev
```

## Pipecat Memory Integration

Add persistent memory to your Pipecat voice AI agent. Remember user preferences, past conversations, and context across sessions.

Supermemory integrates with Pipecat, providing long-term memory capabilities for voice AI agents. Your Pipecat applications will remember past conversations and provide personalized responses based on user history.

### Installation

```bash
pip install supermemory-pipecat
```

### Configuration

```python
from supermemory_pipecat import SupermemoryPipecatService, InputParams

memory = SupermemoryPipecatService(
    api_key=os.getenv("SUPERMEMORY_API_KEY"),
    user_id="user_123",
    params=InputParams(mode="full", search_limit=10),
)
```

**Modes:** `profile` (user facts) | `query` (search) | `full` (both)

### Pipeline Integration

```python
pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    memory,  # Supermemory
    llm,
    tts,
    transport.output(),
    context_aggregator.assistant(),
])
```

## Links

- [Supermemory Docs](https://supermemory.ai/docs)
- [Pipecat Docs](https://docs.pipecat.ai)
