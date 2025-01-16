#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import websockets
import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import BotInterruptionFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.azure import AzureTTSService, AzureSTTService
from pipecat.services.azure import AzureLLMService

from pipecat.transports.network.websocket_server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class SessionTimeoutHandler:
    """Handles actions to be performed when a session times out.
    Inputs:
    - task: Pipeline task (used to queue frames).
    - tts: TTS service (used to generate speech output).
    """

    def __init__(self, task, tts):
        self.task = task
        self.tts = tts
        self.background_tasks = set()

    async def handle_timeout(self, client_address):
        """Handles the timeout event for a session."""
        try:
            logger.info(f"Connection timeout for {client_address}")

            # Queue a BotInterruptionFrame to notify the user
            await self.task.queue_frames([BotInterruptionFrame()])

            # Send the TTS message to inform the user about the timeout
            await self.tts.say(
                "I'm sorry, we are ending the call now. Please feel free to reach out again if you need assistance."
            )

            # Start the process to gracefully end the call in the background
            end_call_task = asyncio.create_task(self._end_call())
            self.background_tasks.add(end_call_task)
            end_call_task.add_done_callback(self.background_tasks.discard)
        except Exception as e:
            logger.error(f"Error during session timeout handling: {e}")

    async def _end_call(self):
        """Completes the session termination process after the TTS message."""
        try:
            # Wait for a duration to ensure TTS has completed
            await asyncio.sleep(15)

            # Queue both BotInterruptionFrame and EndFrame to conclude the session
            await self.task.queue_frames([BotInterruptionFrame(), EndFrame()])

            logger.info("TTS completed and EndFrame pushed successfully.")
        except Exception as e:
            logger.error(f"Error during call termination: {e}")


async def main(port):
    transport = WebsocketServerTransport(
        port=port,
        params=WebsocketServerParams(
            audio_out_sample_rate=24000,
            audio_out_enabled=True,
            add_wav_header=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            session_timeout=60 * 3,  # 3 minutes
        )
    )

    llm = AzureLLMService(
    api_key=os.getenv("AZURE_API_KEY"),
    endpoint="https://lalpathlabs-openai.openai.azure.com",
    model="gpt-4o-mini"  # e.g., "gpt-4o"
)


    stt = AzureSTTService(
    api_key=os.getenv("AZURE_SPEECH_API_KEY"),
    region="centralindia",
    language="hi-IN",
    sample_rate=24000,
    channels=1
    )
    
    tts = AzureTTSService(
        api_key=os.getenv("AZURE_SPEECH_API_KEY"),
        region="centralindia",
        voice="hi-IN-SwaraNeural",
        params=AzureTTSService.InputParams(
            language="hi-IN",
            rate="1",
            style="cheerful"
        )
    )
    
    messages = [
        {
            "role": "system",
            "content": """You are a polite and professional multilingual female customer care representative for Doctor Lal Pathlabs, specializing in pathology services. You communicate primarily in Hindi AND ENGLISH. Reply in Hindi if the user asks in Hindi. And Reply in English if the user asks in English. Your role is to assist customers with their queries. If a customer requests to book a test, ensure that you collect the name of the test, name of the user, user's address and preferred appointment time. Once all the required details are provided, confirm the booking by informing the customer that their appointment has been successfully scheduled. Your responses will be converted into audio speech. If the user asks for status of their report, ask for their order reference number. If the user has provided the number, tell them that their repost will be ready by today evening. If the user asks for Senior citizen discount, tell them Senior citizens get 5 percent discount. The cost for Fasting blood sugar test is Rupees 400, for CRP test it is Rupees 600, for Thyroid Function test it is Rs. 500, for Liver Function Test it is Rs. 600. Rest for all tests, tell the price is Rupees 500. Begin each interaction with a brief and professional self-introduction in a brief single sentence in Hindi.""",
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation.
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    # @transport.event_handler("on_session_timeout")
    # async def on_session_timeout(transport, client):
    #     logger.info(f"Entering in timeout for {client.remote_address}")

    #     timeout_handler = SessionTimeoutHandler(task, tts)

    #     await timeout_handler.handle_timeout(client)

    runner = PipelineRunner()

    await runner.run(task)


# async def killServer(port):
#     await asyncio.sleep(10)
#     logger.info(f"Shutting down websocket server on port {port}")
#     server = await websockets.serve(None, port=port)
#     server.close()
#     await server.wait_closed()
    