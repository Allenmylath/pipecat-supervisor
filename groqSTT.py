import asyncio
import io
import wave
import numpy as np
import onnxruntime
import importlib.resources
from typing import AsyncGenerator, Optional, Tuple
from groq import Groq
import tempfile
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame, AudioRawFrame
from pipecat.services.ai_services import STTService
from pipecat.utils.time import time_now_iso8601
from pipecat.transcriptions.language import Language
from pipecat.processors.frame_processor import FrameDirection
from loguru import logger
from SileroVADSTTService import SileroVADSTTService

class GroqVADSTTService(SileroVADSTTService):
    """GroqSTTService that uses Silero VAD for speech detection before running
    speech-to-text on detected speech segments.
    """
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3",
        language: str = "en",
        temperature: float = 0.0,
        sample_rate: int = 16000,
        num_channels: int = 1,
        vad_threshold: float = 0.5,
        audio_passthrough: bool = False,
        **kwargs
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            language=language,
            temperature=temperature,
            sample_rate=sample_rate,
            num_channels=num_channels,
            audio_passthrough=audio_passthrough,
            **kwargs
        )
        self._vad_threshold = vad_threshold
        self._vad_model = self._initialize_vad()
        self._is_speaking = False
        self._current_audio_buffer = None
        self._current_wave = None

    def _initialize_vad(self):
        """Initialize the Silero VAD ONNX model."""
        model_name = "silero_vad.onnx"
        package_path = "pipecat.audio.vad.data"
        model_path = importlib.resources.files(package_path) / model_name
        return onnxruntime.InferenceSession(
            str(model_path),
            providers=['CPUExecutionProvider']
        )

    def _audio_to_input(self, audio_data: bytes) -> np.ndarray:
        """Convert raw audio bytes to model input format."""
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        audio_np = audio_np.astype(np.float32) / 32768.0
        return np.expand_dims(audio_np, axis=(0, 1))

    def _run_vad(self, audio_input: np.ndarray) -> float:
        """Run VAD inference using ONNX runtime."""
        ort_inputs = {
            'input': audio_input,
            'sr': np.array([self._sample_rate], dtype=np.int64)
        }
        ort_outputs = self._vad_model.run(None, ort_inputs)
        return ort_outputs[0][0][0]

    def _initialize_wave(self):
        """Initialize wave file writer"""
        self._current_audio_buffer = io.BytesIO()
        self._current_wave = wave.open(self._current_audio_buffer, 'wb')
        self._current_wave.setsampwidth(2)
        self._current_wave.setnchannels(self._num_channels)
        self._current_wave.setframerate(self._sample_rate)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames using VAD for speech detection"""
        if isinstance(frame, AudioRawFrame):
            audio_input = self._audio_to_input(frame.audio)
            speech_prob = self._run_vad(audio_input)
            is_speech = speech_prob >= self._vad_threshold

            if is_speech and not self._is_speaking:
                # Speech started
                self._is_speaking = True
                self._initialize_wave()
                
            if self._is_speaking:
                if is_speech:
                    # Continue recording speech
                    self._current_wave.writeframes(frame.audio)
                else:
                    # Speech ended, process the audio
                    self._is_speaking = False
                    self._current_wave.close()
                    self._current_audio_buffer.seek(0)
                    
                    if not self._muted:
                        audio_data = self._current_audio_buffer.read()
                        if len(audio_data) >= 8000:  # Check for minimum duration
                            async for transcription_frame in self.run_stt(audio_data):
                                await self.push_frame(transcription_frame, direction)
                    
                    self._current_wave = None
                    self._current_audio_buffer = None

        await super().process_frame(frame, direction)

    async def cancel(self):
        """Clean up resources when canceling."""
        if self._current_wave:
            self._current_wave.close()
        self._is_speaking = False
        self._current_wave = None
        self._current_audio_buffer = None
