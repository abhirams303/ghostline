#
# Pipecat Cloud voice agent for the OPSEC command deck — GHOSTLINE integration.
#
# This is a faithful copy of teammate's
# ~/Desktop/bang_sec/pipecat-dummy-agent/bot.py with additive hooks:
#   - imports `INTELLIGENCE_TOOLS` and `register_intelligence_tools` from
#     pipecat_tools.py and slots them in alongside his SET_ACTIVE_LOCATION_TOOL.
#   - extends KNOWN_LOCATIONS to cover all 5 GHOSTLINE-populated targets
#     (his fort-liberty + norfolk-naval + creech-afb plus our missing JBLM,
#     Naval Base San Diego, Shack15).
#   - extends the system prompt to tell the LLM about the new intelligence
#     tools without changing the navigation language.
#
# All Deepgram / OpenAI / Cartesia / RTVI / Daily plumbing is preserved
# as-is. To deploy this in place of his bot.py, point the Pipecat Cloud
# entry point at `backend.ai.integrated_bot:bot` (a one-line pcc-deploy.toml
# change in his repo, no edits to bot.py).
#

import os
from typing import Any, Mapping

from dotenv import load_dotenv
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.runner.types import DailyRunnerArguments, RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_mute.base_user_mute_strategy import BaseUserMuteStrategy

from .pipecat_tools import INTELLIGENCE_TOOLS, register_intelligence_tools

load_dotenv(override=True)

DEFAULT_CARTESIA_VOICE_ID = "ec1e269e-9ca0-402f-8a18-58e0e022355a"
REQUIRED_VOICE_KEYS = ("DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY")
VAD_PARAMS = VADParams(confidence=0.65, start_secs=0.15, stop_secs=0.35, min_volume=0.55)

# Teammate's existing 3 + our 3 missing GHOSTLINE-populated targets.
# Aliases stay broad — the LLM sometimes picks shorthand the operator used.
KNOWN_LOCATIONS = {
    "fort-liberty": {
        "label": "Fort Liberty",
        "aliases": ("fort liberty", "liberty", "ft liberty", "fort bragg", "bragg"),
    },
    "norfolk-naval": {
        "label": "Norfolk Naval",
        "aliases": ("norfolk naval", "norfolk", "naval station norfolk", "naval"),
    },
    "creech-afb": {
        "label": "Creech AFB",
        "aliases": ("creech afb", "creech", "creech air force base", "air force base creech"),
    },
    "jblm": {
        "label": "Joint Base Lewis-McChord",
        "aliases": ("jblm", "joint base lewis mcchord", "lewis mcchord", "lewis-mcchord", "fort lewis"),
    },
    "naval-base-san-diego": {
        "label": "Naval Base San Diego",
        "aliases": ("naval base san diego", "san diego", "nbsd", "32nd street naval station"),
    },
    "shack15": {
        "label": "Shack15",
        "aliases": ("shack15", "shack 15", "shack fifteen"),
    },
}

SET_ACTIVE_LOCATION_TOOL = FunctionSchema(
    name="set_active_location",
    description=(
        "Move the command-deck map to a location. Use this whenever the operator asks "
        "to show, open, focus, switch, change location, go to, analyze, or asks about one "
        "of the known locations or any other place name."
    ),
    properties={
        "location_id": {
            "type": "string",
            "enum": list(KNOWN_LOCATIONS.keys()),
            "description": "Optional known command-deck location id when the place is one of the known targets.",
        },
        "location_name": {
            "type": "string",
            "description": "The exact location or place name the operator asked about.",
        },
        "spoken_reference": {
            "type": "string",
            "description": "Optional exact phrase the operator used for the location.",
        },
    },
    required=["location_name"],
)

SYSTEM_PROMPT = """You are the command voice inside a Gradient Bang-style Palantir AIP cockpit.
You help the operator triage live mission data, background agent tasks, and hackathon build work.
Keep spoken answers short, operational, and specific. Never claim you can access Palantir,
Pipecat, or external systems unless tool context or the operator explicitly provides it.

You have access to pre-computed OPSEC cascade intelligence from Palantir Foundry covering:
- Fort Liberty (formerly Fort Bragg, NC)
- Naval Station Norfolk (VA)
- Joint Base Lewis-McChord / JBLM (WA)
- Naval Base San Diego (CA)
- Shack15 (San Francisco, civilian venue)

Tool selection guide:
- When the operator asks to show, open, focus, switch, move to, change location, or asks
  to navigate the map: call set_active_location with location_name. Use location_id too
  only when the place matches a known command-deck location.
- When the operator asks about exposure, risk, threat level, or wants the threat brief
  for a base: call get_location_assessment.
- When the operator asks about cascade risk, downstream compromise, what intelligence
  the adversary could infer, or how surface exposure amplifies through linked entities:
  call get_cascade_analysis.
- When the operator asks what an adversary would DO, what attacks are predicted, or
  what targets are at risk: call get_adversary_actions.
- When the operator asks which base is most exposed, for a leaderboard, or any cross-
  location comparison: call compare_all_locations.
- When the operator asks what's happening right now, about live aircraft, satellite
  passes, or current news at a location: call get_live_situation.

When summarizing intelligence results, lead with the headline number (exposure score,
cascade score, count of actions), then quote the specific entity names you got back.
Never invent unit names, platform IDs, or sensor designations — use what the tools
return."""

READY_GREETING = (
    "Voice link online. I can hear you now. Give me a command for the AIP operations deck."
)


class FirstBotSpeechMuteStrategy(BaseUserMuteStrategy):
    """Mute user audio until the first bot utterance completes.

    This mirrors Gradient Bang's startup guard. It prevents the bot's own
    greeting or speaker echo from being treated as the first user turn.
    """

    def __init__(self):
        super().__init__()
        self._first_speech_finished = False

    async def process_frame(self, frame: Frame) -> bool:
        await super().process_frame(frame)

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._first_speech_finished = True

        return not self._first_speech_finished


def _missing_voice_keys() -> list[str]:
    return [key for key in REQUIRED_VOICE_KEYS if not os.getenv(key)]


def _normalize_location_text(text: str) -> str:
    return " ".join("".join(char.lower() if char.isalnum() else " " for char in text).split())


def _string_arg(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _resolve_location(arguments: Mapping[str, Any]) -> tuple[str, str] | None:
    location_id = _string_arg(arguments, "location_id")
    if location_id in KNOWN_LOCATIONS:
        return location_id, KNOWN_LOCATIONS[location_id]["label"]

    search_text = " ".join(
        value
        for key in ("location_name", "spoken_reference", "location", "target", "query")
        if (value := _string_arg(arguments, key))
    )
    normalized = _normalize_location_text(search_text)
    if not normalized:
        return None

    for candidate_id, definition in KNOWN_LOCATIONS.items():
        aliases = (definition["label"], *definition["aliases"])
        if any(_normalize_location_text(alias) in normalized for alias in aliases):
            return candidate_id, definition["label"]

    return None


def _extract_location_name(arguments: Mapping[str, Any]) -> str | None:
    for key in ("location_name", "spoken_reference", "location", "target", "query"):
        value = _string_arg(arguments, key)
        if value:
            return value

    return None


def _make_set_active_location_handler(rtvi: RTVIProcessor):
    async def handle_set_active_location(params: FunctionCallParams):
        location = _resolve_location(params.arguments)
        location_name = _extract_location_name(params.arguments)

        if location:
            location_id, label = location
            await rtvi.send_server_message(
                {
                    "type": "command-deck.location",
                    "surfaceId": location_id,
                    "targetId": location_id,
                    "label": label,
                    "text": f"Moving map to {label}.",
                }
            )
            await params.result_callback(
                {
                    "success": True,
                    "surfaceId": location_id,
                    "targetId": location_id,
                    "label": label,
                }
            )
            return

        if location_name:
            await rtvi.send_server_message(
                {
                    "type": "command-deck.location-request",
                    "locationName": location_name,
                    "text": f"Looking up {location_name}.",
                }
            )
            await params.result_callback(
                {
                    "success": True,
                    "locationName": location_name,
                    "message": f"The command deck is looking up {location_name}.",
                }
            )
            return

        await params.result_callback(
            {
                "success": False,
                "error": "No location name was provided.",
                "known_location_ids": list(KNOWN_LOCATIONS.keys()),
            }
        )

    return handle_set_active_location


def _build_voice_pipeline(transport: DailyTransport, rtvi: RTVIProcessor) -> Pipeline:
    missing = _missing_voice_keys()
    if missing:
        raise RuntimeError(
            "Voice providers are not configured. Missing Pipecat Cloud secrets: "
            + ", ".join(missing)
            + "."
        )

    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        live_options=LiveOptions(
            language=Language.EN,
            model=os.getenv("DEEPGRAM_MODEL", "nova-3-general"),
            smart_format=True,
            interim_results=True,
        ),
    )
    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(
            model=os.getenv("OPENAI_LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.4")),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "180")),
        ),
    )
    llm.register_function("set_active_location", _make_set_active_location_handler(rtvi))
    register_intelligence_tools(llm, rtvi)
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id=os.getenv("CARTESIA_VOICE_ID", DEFAULT_CARTESIA_VOICE_ID),
        model=os.getenv("CARTESIA_MODEL", "sonic-3"),
    )

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": os.getenv("COMMAND_DECK_AGENT_PROMPT", SYSTEM_PROMPT),
            }
        ],
        tools=ToolsSchema(standard_tools=[SET_ACTIVE_LOCATION_TOOL, *INTELLIGENCE_TOOLS]),
    )
    startup_mute = FirstBotSpeechMuteStrategy()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VAD_PARAMS),
            user_mute_strategies=[startup_mute],
            user_turn_stop_timeout=1.2,
            audio_idle_timeout=0.6,
        ),
    )
    if hasattr(user_aggregator, "_user_is_muted"):
        user_aggregator._user_is_muted = True

    return Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )


def _build_unconfigured_pipeline(transport: DailyTransport) -> Pipeline:
    return Pipeline(
        [
            transport.input(),
            transport.output(),
        ]
    )


async def run_bot(transport):
    """Run an RTVI-compatible Daily voice pipeline."""
    voice_config_error = None
    rtvi = RTVIProcessor(transport=transport)
    try:
        pipeline = _build_voice_pipeline(transport, rtvi)
        logger.info("Command-deck voice pipeline configured with STT, LLM, TTS, and intelligence tools")
    except RuntimeError as error:
        voice_config_error = str(error)
        pipeline = _build_unconfigured_pipeline(transport)
        logger.warning(voice_config_error)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        rtvi_processor=rtvi,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Command-deck client connected")

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        if voice_config_error:
            await rtvi.send_server_message(
                {
                    "type": "command-deck.voice-config-missing",
                    "text": voice_config_error,
                }
            )
            return

        await rtvi.send_server_message(
            {
                "type": "command-deck.voice-ready",
                "text": READY_GREETING,
            }
        )
        await task.queue_frame(TTSSpeakFrame(text=READY_GREETING, append_to_context=False))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Command-deck client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Pipecat Cloud entry point."""
    match runner_args:
        case DailyRunnerArguments():
            transport = DailyTransport(
                runner_args.room_url,
                runner_args.token,
                "Gradient Bang AIP",
                params=DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                ),
            )
        case _:
            logger.error(f"Unsupported runner arguments type: {type(runner_args)}")
            return

    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
