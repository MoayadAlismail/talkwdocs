import re
import json
import random
import logging
import aiohttp
from datetime import datetime
from typing import Annotated, Optional

from dotenv import load_dotenv
from livekit.agents import ( AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli, llm, metrics, )
from livekit.agents.pipeline import AgentCallContext, VoicePipelineAgent
from livekit.plugins import openai, deepgram, elevenlabs, silero, turn_detector

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-assistant")

class DocumentAssistant(llm.FunctionContext):
    """Handles document-related operations and utility functions for the voice assistant"""
    
    def __init__(self):
        super().__init__()
        self.document_content = None
        self.document_name = None

    def load_document_from_metadata(self, metadata: str) -> None:
        """Attempts to parse and load document data from participant metadata"""
        try:
            parsed_data = json.loads(metadata)
            if uploaded_file := parsed_data.get('uploadedFile'):
                self.document_content = uploaded_file['content']
                self.document_name = uploaded_file['filename']
                logger.info(f"Successfully loaded document: '{self.document_name}'")
        except Exception as e:
            logger.error(f"Failed to load document from metadata: {e}")

    @llm.ai_callable()
    def get_document_content(self) -> str:
        """Retrieves the content of the uploaded document"""
        if not self.document_content:
            return "No document has been uploaded at this time."
        return f"Contents of '{self.document_name}':\n{self.document_content}"

    @llm.ai_callable()
    def get_document_summary(self) -> str:
        """Generates a summary of the uploaded document"""
        if not self.document_content:
            return "No document has been uploaded at this time."
        return f"Summary of '{self.document_name}':\n{self.document_content}"

    @llm.ai_callable()
    async def fetch_weather(
        self,
        location: Annotated[
            str, llm.TypeInfo(description="Location to retrieve weather information for")
        ],
    ):
        """Retrieves current weather information for the specified location"""
        sanitized_location = re.sub(r"[^a-zA-Z0-9]+", " ", location).strip()
        current_agent = AgentCallContext.get_current().agent

        # Send acknowledgment message if needed
        if (not current_agent.chat_ctx.messages or 
            current_agent.chat_ctx.messages[-1].role != "assistant"):
            status_msg = f"Checking weather conditions in {sanitized_location}..."
            logger.info(f"Sending status message: {status_msg}")
            await current_agent.say(status_msg, add_to_chat_ctx=True)

        # Fetch weather data
        logger.info(f"Requesting weather data for: {sanitized_location}")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://wttr.in/{sanitized_location}?format=%C+%t"
            ) as response:
                if response.status == 200:
                    weather_info = await response.text()
                    result = f"The weather in {sanitized_location} is {weather_info}."
                    logger.info(f"Weather data received: {result}")
                    return result
                else:
                    raise RuntimeError(f"Weather API request failed: {response.status}")
    
    @llm.ai_callable()
    def get_current_time(self):
        """Returns the current local time"""
        return datetime.now().strftime("%H:%M:%S")


# Voice Assistant Setup
# ===============================

def prewarm(proc: JobProcess):
    """Initializes voice activity detection model"""
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    """Main entry point for the voice assistant application"""
    
    # Initialize chat context
    base_context = llm.ChatContext().append(
        role="system",
        text=(
            "Interactive voice assistant powered by LiveKit. "
            "Responses should be concise and conversational. "
            "For document queries, check content first using get_document_content()."
        ),
    )

    # Room connection setup
    logger.info(f"Establishing connection to room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for participant and initialize
    participant = await ctx.wait_for_participant()
    logger.info(f"Initializing assistant for user: {participant.identity}")
    logger.info(f"User name: {participant.name}")
    logger.info(f"User metadata: {participant.metadata}")

    # Setup document handling
    doc_handler = DocumentAssistant()
    if participant.metadata:
        doc_handler.load_document_from_metadata(participant.metadata)

    # Initialize voice assistant
    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(),
        turn_detector=turn_detector.EOUModel(),
        min_endpointing_delay=0.5,
        max_endpointing_delay=5.0,
        chat_ctx=base_context,
        fnc_ctx=doc_handler,
    )

    # Setup metrics collection
    metrics_collector = metrics.UsageCollector()

    @assistant.on("metrics_collected")
    def handle_metrics(assistant_metrics: metrics.AgentMetrics):
        metrics.log_metrics(assistant_metrics)
        metrics_collector.collect(assistant_metrics)

    async def log_final_usage():
        usage_summary = metrics_collector.get_summary()
        logger.info(f"Final Usage Summary: {usage_summary}")

    ctx.add_shutdown_callback(log_final_usage)

    # Start assistant
    assistant.start(ctx.room, participant)

    # Send welcome message
    welcome_msg = (
        f"Hello! I see you've uploaded '{doc_handler.document_name}'. Let's discuss it!"
        if doc_handler.document_name
        else "Hello! How can I help you today?"
    )
    await assistant.say(welcome_msg, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
