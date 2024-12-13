import io
import wave
import numpy as np
import onnxruntime
import importlib.resources
from typing import Tuple

from pipecat.services.ai_services import STTService

class SileroVADSTTService(STTService):
    """STTService that uses Silero VAD (ONNX) for speech detection before running
    speech-to-text on detected speech segments.
    """
    def __init__(
        self,
        *,
        threshold: float = 0.5,
        sampling_rate: int = 24000,
        num_channels: int = 1,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._threshold = threshold
        self._sample_rate = sampling_rate
        self._num_channels = num_channels
        self._vad_model = self._initialize_vad()
        (self._content, self._wave) = self._new_wave()
        self._is_speech = False
        
    def _initialize_vad(self):
        """Initialize the Silero VAD ONNX model."""
        model_path = importlib.resources.files(package_path) / model_name
        return onnxruntime.InferenceSession(
            str(model_path),
            providers=['CPUExecutionProvider']
        )
        
    def _audio_to_input(self, audio_data: bytes) -> np.ndarray:
        """Convert raw audio bytes to model input format."""
        # Convert bytes to numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        # Normalize to float between -1 and 1
        audio_np = audio_np.astype(np.float32) / 32768.0
        # Reshape for model input (batch_size=1, channels=1, time)
        return np.expand_dims(audio_np, axis=(0, 1))

    def _run_vad(self, audio_input: np.ndarray) -> float:
        """Run VAD inference using ONNX runtime."""
        ort_inputs = {
            'input': audio_input,
            'sr': np.array([self._sample_rate], dtype=np.int64)
        }
        ort_outputs = self._vad_model.run(None, ort_inputs)
        return ort_outputs[0][0][0]  # Extract probability from output

    async def process_audio_frame(self, frame: AudioRawFrame):
        audio_input = self._audio_to_input(frame.audio)
        
        # Get speech probability from Silero VAD
        speech_prob = self._run_vad(audio_input)
        is_speech = speech_prob >= self._threshold
        
        if is_speech:
            # If speech is detected, write frame to wave file
            self._wave.writeframes(frame.audio)
            self._is_speech = True
        elif self._is_speech:
            # Speech ended, process the accumulated audio
            self._wave.close()
            self._content.seek(0)
            
            # Run STT on the accumulated audio
            await self.process_generator(self.run_stt(self._content.read()))
            
            # Reset for next segment
            self._is_speech = False
            (self._content, self._wave) = self._new_wave()

    async def stop(self, frame: EndFrame):
        if self._is_speech:
            # Process any remaining audio
            self._wave.close()
            self._content.seek(0)
            await self.process_generator(self.run_stt(self._content.read()))
        self._wave.close()

    async def cancel(self, frame: CancelFrame):
        self._wave.close()
        self._is_speech = False

    def _new_wave(self) -> Tuple[io.BytesIO, wave.Wave_write]:
        """Create a new wave file in memory."""
        content = io.BytesIO()
        ww = wave.open(content, "wb")
        ww.setsampwidth(2)
        ww.setnchannels(self._num_channels)
        ww.setframerate(self._sample_rate)
        return (content, ww)
