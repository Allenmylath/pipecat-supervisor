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
    UserStoppedSpeakingFrame,
    STTUpdateSettingsFrame,
    STTMuteFrame
)
from pipecat.utils.time import time_now_iso8601
from pipecat.services.ai_services import STTService
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transcriptions.language import Language
from loguru import logger

class GroqSTTService(STTService):
    """GroqSTTService uses Groq's remote Whisper API to perform speech-to-text
    transcription on audio segments with VAD support.
    """
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3",
        language: str = "en",
        temperature: float = 0.0,
        prompt: Optional[str] = None,
        sample_rate: int = 24000,
        num_channels: int = 1,
        audio_passthrough: bool = False,
        **kwargs
    ):
        super().__init__(audio_passthrough=audio_passthrough, **kwargs)
        self.client = Groq(api_key=api_key)
        self.model = model
        self.language = language
        self.temperature = temperature
        self.prompt = prompt
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        
        # VAD-related state
        self._is_speaking = False
        self._current_audio_buffer = io.BytesIO()
        self._current_wave = None

    def can_generate_metrics(self) -> bool:
        return True

    async def set_model(self, model: str):
        """Set the model to use for transcription."""
        self.model = model
        self.set_model_name(model)

    async def set_language(self, language: str):
        """Set the language for transcription."""
        self.language = language

    def _initialize_wave(self):
        """Initialize a new wave file writer"""
        self._current_audio_buffer = io.BytesIO()
        self._current_wave = wave.open(self._current_audio_buffer, 'wb')
        self._current_wave.setsampwidth(2)  # 16-bit audio
        self._current_wave.setnchannels(self._num_channels)
        self._current_wave.setframerate(self._sample_rate)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
    """Process incoming frames including VAD frames"""
    # First pass through any non-audio frame that isn't VAD related
        if not isinstance(frame, (UserStartedSpeakingFrame, UserStoppedSpeakingFrame, AudioRawFrame)):
            await self.push_frame(frame, direction)
            return

        await super().process_frame(frame, direction)
    
        if isinstance(frame, UserStartedSpeakingFrame):
            self._is_speaking = True
            self._initialize_wave()
        
        elif isinstance(frame, UserStoppedSpeakingFrame):
            if self._is_speaking and self._current_wave:
                self._is_speaking = False
                self._current_wave.close()
                self._current_audio_buffer.seek(0)
            
                if not self._muted:
                    audio_data = self._current_audio_buffer.read()
                    await self.process_generator(self.run_stt(audio_data))
            
                # Cleanup
                self._current_wave = None
                self._current_audio_buffer = None
            
        elif isinstance(frame, AudioRawFrame):
        # Handle audio collection if speaking
            if self._is_speaking and self._current_wave:
                self._current_wave.writeframes(frame.audio)
        
            # Handle audio passthrough regardless of speaking state
            if self._audio_passthrough:
                await self.push_frame(frame, direction)
                
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Process audio data using Groq's Whisper API and yield transcription frames."""
        if not self.client:
            logger.error(f"{self} error: Groq client not available")
            yield ErrorFrame("Groq client not available")
            return

        await self.start_processing_metrics()
        await self.start_ttfb_metrics()

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
            with wave.open(temp_file.name, 'wb') as wf:
                wf.setsampwidth(2)  # 16-bit audio
                wf.setnchannels(self._num_channels)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio)
            
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
                        # Add detailed logging before creating the frame
                        logger.info(f"Transcription completed. Text: '{transcription.text.strip()}'")
                        logger.debug(f"Transcription details - Model: {self.model}, Language: {self.language}")
                        
                        # Create TranscriptionFrame with all required fields
                        frame = TranscriptionFrame(
                            text=transcription.text.strip(),
                            user_id="",  # User ID should be set based on your application's user tracking
                            timestamp=time_now_iso8601(),
                            language=Language(self.language) if self.language else None
                        )
                        logger.debug(f"Created transcription frame: {str(frame)}")
                        yield frame
                    
                except Exception as e:
                    logger.error(f"Error during Groq transcription: {str(e)}")
                    yield ErrorFrame(f"Groq transcription error: {str(e)}")
                finally:
                    await self.stop_processing_metrics()
