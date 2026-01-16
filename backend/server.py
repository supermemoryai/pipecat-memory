"""
Pipecat + Supermemory Voice Bot Server

This server uses Supermemory for memory storage.
Works with the official @pipecat-ai/client-js SDK.
Supports multiple users via query params.
"""

import os
import sys
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.genai import types
from google.genai.types import EndSensitivity, StartSensitivity
from loguru import logger
from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import (
    RTVIConfig,
    RTVIObserver,
    RTVIObserverParams,
    RTVIProcessor,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.google.gemini_live.llm import (
    GeminiLiveContext,
    GeminiLiveLLMService,
    GeminiVADParams,
    InputParams,
)
from pipecat.services.google.google import LLMContext
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_start.external_user_turn_start_strategy import (
    ExternalUserTurnStartStrategy,
)
from pipecat.turns.user_stop.external_user_turn_stop_strategy import (
    ExternalUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from supermemory_pipecat import SupermemoryPipecatService

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

app = FastAPI(title="Pipecat + Supermemory Voice Bot")

# Get allowed origins from env or default to all
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
    """Run the voice bot pipeline with Supermemory for a specific user."""

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
        transcribe_user_audio=True,
        transcribe_model_audio=True,
        inference_on_context_initialization=True,
        params=InputParams(
            vad=GeminiVADParams(
                disabled=False,
                start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,  # Detect speech quickly
                end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,  # Allow longer pauses
                prefix_padding_ms=300,  # Keep 300ms before speech
                silence_duration_ms=500,  # Allow longer pauses
            ),
        ),
    )

    # Supermemory service with user-specific context
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

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[ExternalUserTurnStartStrategy()],
                stop=[ExternalUserTurnStopStrategy()],
            ),
        ),
    )
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    pipeline = Pipeline(
        [
            transport.input(),
            memory,
            rtvi,
            user_aggregator,
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
        observers=[
            RTVIObserver(
                rtvi,
                params=RTVIObserverParams(
                    bot_tts_enabled=True,
                    bot_llm_enabled=True,
                    bot_output_enabled=True,
                    bot_speaking_enabled=True,
                    user_transcription_enabled=True,
                    user_speaking_enabled=True,
                ),
            )
        ],
        enable_turn_tracking=True,
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
    """
    Client calls this to get WebSocket connection info.
    Pass userId and sessionId to maintain user context.
    """
    # Generate IDs if not provided
    user_id = userId or f"user-{uuid.uuid4().hex[:12]}"
    session_id = sessionId or f"session-{uuid.uuid4().hex[:8]}"

    # Get the host from request or use env
    ws_host = os.getenv("WS_HOST", request.headers.get("host", "localhost:8001"))
    ws_protocol = "wss" if os.getenv("USE_SSL", "false").lower() == "true" else "ws"

    # Pipecat client only expects wsUrl in response - embed userId/sessionId in URL
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

    # Generate IDs if not provided
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
