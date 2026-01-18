import os
import sys
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.genai.types import EndSensitivity, StartSensitivity
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frameworks.rtvi import (
    RTVIConfig,
    RTVIObserver,
    RTVIProcessor,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.google.gemini_live.llm import (
    GeminiLiveLLMService,
    GeminiVADParams,
    InputParams,
)
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from supermemory_pipecat import SupermemoryPipecatService

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

app = FastAPI(title="Pipecat + Supermemory Voice Bot")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are a helpful voice assistant with memory capabilities.
You remember information from past conversations and use it to provide personalized responses.
Keep your responses brief and conversational - one or two sentences at most.
Your output will be converted to audio so don't include special characters. Ask for their name and greet them. Only speak when you need to. When giving an introduction, just say something along the lines of 'I am a memory assistant powered by supermemory'. What's your name? (don't ask the name if you already know it but you get the point)"""


async def run_bot(websocket_client, user_id: str, session_id: str):
    logger.info(f"Starting bot for user: {user_id}, session: {session_id}")

    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=ProtobufFrameSerializer(),
        ),
    )

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set")

    llm = GeminiLiveLLMService(
        api_key=gemini_api_key,
        voice_id="Puck",
        system_instruction=SYSTEM_PROMPT,
        inference_on_context_initialization=True,
        params=InputParams(
            vad=GeminiVADParams(
                disabled=False,
                start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                prefix_padding_ms=300,
                silence_duration_ms=500,
            ),
        ),
    )

    memory = SupermemoryPipecatService(
        api_key=os.getenv("SUPERMEMORY_API_KEY"),
        user_id=user_id,
        session_id=session_id,
        params=SupermemoryPipecatService.InputParams(
            search_limit=10,
            search_threshold=0.1,
            mode="full",
        ),
    )

    context = LLMContext([{"role": "system", "content": SYSTEM_PROMPT}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    # Pipeline: RTVI before output transport for proper client communication
    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            user_aggregator,
            memory,  # Memory receives context frames with user messages
            llm,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info(f"Client ready for user: {user_id}")
        await rtvi.set_bot_ready()
        await task.queue_frames(
            [
                LLMMessagesFrame(
                    [
                        {
                            "role": "system",
                            "content": "Greet the user warmly and ask them a question (like their name) don't say much please.",
                        }
                    ]
                )
            ]
        )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected: {client} (user: {user_id})")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected: {client} (user: {user_id})")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


@app.post("/connect")
async def connect(
    request: Request,
    userId: str = Query(None),
    sessionId: str = Query(None),
):
    user_id = userId or f"user-{uuid.uuid4().hex[:12]}"
    session_id = sessionId or f"session-{uuid.uuid4().hex[:8]}"

    ws_host = os.getenv("WS_HOST", request.headers.get("host", "localhost:8001"))
    ws_protocol = "wss" if os.getenv("USE_SSL", "false").lower() == "true" else "ws"

    return JSONResponse(
        {
            "wsUrl": f"{ws_protocol}://{ws_host}/ws?userId={user_id}&sessionId={session_id}",
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    userId: str = Query(None),
    sessionId: str = Query(None),
):
    await websocket.accept()

    user_id = userId or f"user-{uuid.uuid4().hex[:12]}"
    session_id = sessionId or f"session-{uuid.uuid4().hex[:8]}"

    logger.info(f"WebSocket connection for user: {user_id}, session: {session_id}")

    try:
        await run_bot(websocket, user_id, session_id)
    except Exception as e:
        logger.error(f"Bot error for user {user_id}: {e}")
    finally:
        logger.info(f"WebSocket connection closed for user: {user_id}")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": "supermemory",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8001))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
