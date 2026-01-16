# Supermemory x Pipecat

Voice assistant with persistent memory powered by [Supermemory](https://supermemory.ai) and [Pipecat](https://pipecat.ai).

## Quick Start

```bash
bun install && cd backend && pip install -r requirements.txt
```

```bash
# backend/.env
OPENAI_API_KEY=sk-...
SUPERMEMORY_API_KEY=sm-...
```

```bash
bun run start:backend  # Terminal 1
bun run dev            # Terminal 2
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
