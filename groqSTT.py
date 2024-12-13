import asyncio
from typing import AsyncGenerator, Optional, Dict, Any
import tempfile
import wave
import io
from groq import Groq
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TranscriptionFrame,
    AudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame
)
from pipecat.utils.time import time_now_iso8601
from pipecat.services.ai_services import STTService
from pipecat.processors.frame_processor import FrameDirection
from pipecat.transcriptions.language import Language
from loguru import logger

class GroqSTTService(STTService):
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3",
        language: str = "en",
        temperature: float = 0.0,
        sample_rate: int = 16000,
        num_channels: int = 1,
        audio_passthrough: bool = False,
        **kwargs
    ):
        super().__init__(audio_passthrough=audio_passthrough, **kwargs)
        self.client = Groq(api_key=api_key)
        self.model = model
        self.language = language
        self.temperature = temperature
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        
        # For VAD handling
        self._is_speaking = False
        self._current_audio_buffer = None
        self._current_wave = None

    async def set_model(self, model: str):
        """Set the model for transcription."""
        self.model = model
        self.set_model_name(model)

    async def set_language(self, language: Language):
        """Set the language for transcription."""
        self.language = language

    def _initialize_wave(self):
        """Initialize wave file writer"""
        self._current_audio_buffer = io.BytesIO()
        self._current_wave = wave.open(self._current_audio_buffer, 'wb')
        self._current_wave.setsampwidth(2)
        self._current_wave.setnchannels(self._num_channels)
        self._current_wave.setframerate(self._sample_rate)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Handle both VAD frames and direct audio frames"""
        if isinstance(frame, UserStartedSpeakingFrame):
            self._is_speaking = True
            self._initialize_wave()
            await self.push_frame(frame, direction)
            
        elif isinstance(frame, UserStoppedSpeakingFrame):
            if self._is_speaking and self._current_wave:
                self._is_speaking = False
                self._current_wave.close()
                self._current_audio_buffer.seek(0)
                
                if not self._muted:
                    audio_data = self._current_audio_buffer.read()
                    if len(audio_data) >= 8000:  # Check for minimum duration
                        await self.process_generator(self.run_stt(audio_data))
                
                self._current_wave = None
                self._current_audio_buffer = None
            await self.push_frame(frame, direction)
            
        elif isinstance(frame, AudioRawFrame):
            if self._is_speaking and self._current_wave:
                self._current_wave.writeframes(frame.audio)
            else:
                # Process direct audio frames through base class
                await super().process_frame(frame, direction)
        else:
            await super().process_frame(frame, direction)

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Process audio using Groq's Whisper API"""
        if not self.client:
            logger.error("Groq client not available")
            yield ErrorFrame("Groq client not available")
            return

        await self.start_processing_metrics()
        await self.start_ttfb_metrics()

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
            with wave.open(temp_file.name, 'wb') as wf:
                wf.setsampwidth(2)
                wf.setnchannels(self._num_channels)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio)
            
            try:
                with open(temp_file.name, 'rb') as audio_file:
                    file_content = audio_file.read()
                    transcription = await asyncio.to_thread(
                        self.client.audio.transcriptions.create,
                        file=("audio.wav", file_content),
                        model=self.model,
                        language=self.language,
                        temperature=self.temperature,
                        response_format="json"
                    )
                    
                    await self.stop_ttfb_metrics()
                    
                    if transcription and hasattr(transcription, 'text'):
                        text = transcription.text.strip()
                        if text:
                            logger.info(f"Transcription completed: '{text}'")
                            frame = TranscriptionFrame(
                                text=text,
                                user_id="",
                                timestamp=time_now_iso8601(),
                                language=Language(self.language) if self.language else None
                            )
                            yield frame
                    
            except Exception as e:
                logger.error(f"Groq transcription error: {str(e)}")
                yield ErrorFrame(f"Transcription error: {str(e)}")
            finally:
                await self.stop_processing_metrics()
