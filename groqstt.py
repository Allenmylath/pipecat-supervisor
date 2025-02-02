import asyncio
from typing import AsyncGenerator, Optional
import tempfile
import wave
import numpy as np
from groq import Groq
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.utils.time import time_now_iso8601
from pipecat.services.ai_services import SegmentedSTTService
from loguru import logger


class GroqSTTService(SegmentedSTTService):
    """GroqSTTService uses Groq's remote Whisper API to perform speech-to-text
    transcription on audio segments.
    """
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3",
        language: str = "en",
        temperature: float = 0.0,
        prompt: Optional[str] = None,
        no_speech_prob: float = 0.4,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.client = Groq(api_key=api_key)
        self.model = model
        self.language = language
        self.temperature = temperature
        self.prompt = prompt
        self._no_speech_prob = no_speech_prob

    def can_generate_metrics(self) -> bool:
        return True

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Process audio data using Groq's Whisper API and yield transcription frames.
        
        Args:
            audio: Raw audio data in bytes
            
        Yields:
            TranscriptionFrame or ErrorFrame objects
        """
        if not self.client:
            logger.error(f"{self} error: Groq client not available")
            yield ErrorFrame("Groq client not available")
            return

        await self.start_processing_metrics()
        await self.start_ttfb_metrics()

        # Create a temporary WAV file to store the audio data
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
            # Write the audio data to the temporary file
            with wave.open(temp_file.name, 'wb') as wf:
                wf.setsampwidth(2)  # 16-bit audio
                wf.setnchannels(self._num_channels)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio)
            
            # Read the temporary file and send it to Groq
            with open(temp_file.name, 'rb') as audio_file:
                try:
                    transcription = await asyncio.to_thread(
                        self.client.audio.transcriptions.create,
                        file=(temp_file.name, audio_file.read()),
                        model=self.model,
                        language=self.language,
                        temperature=self.temperature,
                        prompt=self.prompt,
                        response_format="json"
                    )

                    await self.stop_ttfb_metrics()
                    
                    if transcription and transcription.text:
                        logger.debug(f"Transcription: [{transcription.text}]")
                        yield TranscriptionFrame(
                            transcription.text.strip(),
                            "",  # No speaker ID for now
                            time_now_iso8601()
                        )
                    
                except Exception as e:
                    logger.error(f"Error during Groq transcription: {str(e)}")
                    yield ErrorFrame(f"Groq transcription error: {str(e)}")
                finally:
                    await self.stop_processing_metrics()
