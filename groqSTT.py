import asyncio
from typing import AsyncGenerator, Optional
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
    """GroqSTTService uses Groq's Whisper API for speech-to-text transcription."""
    
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3",
        language: str = "en",
        temperature: float = 0.0,
        sample_rate: int = 16000,  # Changed default to 16kHz
        num_channels: int = 1,
        audio_passthrough: bool = False,
        min_audio_length: int = 4000,  # Minimum audio length in bytes
        **kwargs
    ):
        super().__init__(audio_passthrough=audio_passthrough, **kwargs)
        self.client = Groq(api_key=api_key)
        self.model = model
        self.language = language
        self.temperature = temperature
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        self.min_audio_length = min_audio_length
        
        # VAD state
        self._is_speaking = False
        self._current_audio_buffer = None
        self._current_wave = None
        
    def _initialize_wave(self):
        """Initialize wave file writer with 16-bit PCM format"""
        self._current_audio_buffer = io.BytesIO()
        self._current_wave = wave.open(self._current_audio_buffer, 'wb')
        self._current_wave.setsampwidth(2)  # 16-bit
        self._current_wave.setnchannels(self._num_channels)
        self._current_wave.setframerate(self._sample_rate)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames including VAD frames"""
        if not isinstance(frame, (UserStartedSpeakingFrame, UserStoppedSpeakingFrame, AudioRawFrame)):
            await self.push_frame(frame, direction)
            return

        await super().process_frame(frame, direction)
        
        if isinstance(frame, UserStartedSpeakingFrame):
            if not self._is_speaking:
                self._is_speaking = True
                self._initialize_wave()
            
        elif isinstance(frame, UserStoppedSpeakingFrame):
            if self._is_speaking and self._current_wave:
                self._is_speaking = False
                self._current_wave.close()
                
                # Check audio length
                audio_size = self._current_audio_buffer.tell()
                self._current_audio_buffer.seek(0)
                
                if not self._muted and audio_size >= self.min_audio_length:
                    audio_data = self._current_audio_buffer.read()
                    await self.process_generator(self.run_stt(audio_data))
                else:
                    logger.debug(f"Skipping audio segment, length {audio_size} bytes")
                
                self._current_wave = None
                self._current_audio_buffer = None
            
        elif isinstance(frame, AudioRawFrame) and self._is_speaking and self._current_wave:
            self._current_wave.writeframes(frame.audio)
            
            if self._audio_passthrough:
                await self.push_frame(frame, direction)

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Process audio using Groq's Whisper API"""
        if not self.client:
            logger.error("Groq client not available")
            yield ErrorFrame("Groq client not available")
            return

        await self.start_processing_metrics()
        await self.start_ttfb_metrics()

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
            # Write audio to temp file
            with wave.open(temp_file.name, 'wb') as wf:
                wf.setsampwidth(2)
                wf.setnchannels(self._num_channels)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio)
            
            try:
                with open(temp_file.name, 'rb') as audio_file:
                    transcription = await asyncio.to_thread(
                        self.client.audio.transcriptions.create,
                        file=temp_file.name,
                        model=self.model,
                        language=self.language,
                        temperature=self.temperature,
                        response_format="json"
                    )
                    
                    await self.stop_ttfb_metrics()
                    
                    if transcription and hasattr(transcription, 'text'):
                        text = transcription.text.strip()
                        
                        # Basic validation
                        if text and len(text) > 1:
                            logger.info(f"Transcription: '{text}'")
                            
                            frame = TranscriptionFrame(
                                text=text,
                                user_id="",
                                timestamp=time_now_iso8601(),
                                language=Language(self.language) if self.language else None
                            )
                            yield frame
                        else:
                            logger.debug("Empty or invalid transcription")
                    
            except Exception as e:
                logger.error(f"Groq transcription error: {str(e)}")
                yield ErrorFrame(f"Transcription error: {str(e)}")
            finally:
                await self.stop_processing_metrics()
