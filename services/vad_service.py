import logging
import numpy as np
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Try to import webrtcvad
_HAS_WEBRTCVAD = False
try:
    import webrtcvad  # type: ignore  # pyrefly: ignore [missing-import]
    _HAS_WEBRTCVAD = True
    logger.info("webrtcvad package is available for Voice Activity Detection.")
except ImportError:
    _HAS_WEBRTCVAD = False
    logger.info("webrtcvad not installed. Using adaptive energy fallback VAD.")


class VoiceActivityDetector:
    """
    Voice Activity Detector (VAD) supporting WebRTC VAD (aggressiveness 0-3)
    with adaptive spectral energy fallback.
    """

    def __init__(self, mode: int = 2, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.mode = max(0, min(3, mode))
        self._vad: Optional[Any] = None

        if _HAS_WEBRTCVAD:
            try:
                self._vad = webrtcvad.Vad(self.mode)
            except Exception as e:
                logger.warning(f"Failed to initialize WebRTC VAD: {e}")
                self._vad = None

        # Fallback energy threshold
        self._adaptive_threshold = 0.0004

    def set_aggressiveness(self, mode: int) -> None:
        """Update WebRTC VAD aggressiveness mode (0 to 3)."""
        self.mode = max(0, min(3, mode))
        if self._vad is not None:
            try:
                self._vad.set_mode(self.mode)
            except Exception as e:
                logger.warning(f"Error setting WebRTC VAD mode: {e}")

    def is_speech(self, pcm_frame_bytes: bytes, frame_sample_rate: int = 16000) -> bool:
        """
        Evaluates whether a PCM audio frame contains human speech.
        
        For WebRTC VAD:
        Frame duration must be 10ms, 20ms, or 30ms.
        At 16kHz 16-bit mono PCM:
          - 10ms = 160 samples = 320 bytes
          - 20ms = 320 samples = 640 bytes
          - 30ms = 480 samples = 960 bytes
        """
        if self._vad is not None and frame_sample_rate in (8000, 16000, 32000, 48000):
            # Ensure frame byte length matches WebRTC VAD valid frame sizes (10ms, 20ms, or 30ms)
            bytes_per_sample = 2
            samples = len(pcm_frame_bytes) // bytes_per_sample
            duration_ms = (samples / frame_sample_rate) * 1000.0
            
            if duration_ms in (10.0, 20.0, 30.0):
                try:
                    if self._vad.is_speech(pcm_frame_bytes, frame_sample_rate):
                        return True
                except Exception as e:
                    logger.debug(f"webrtcvad.is_speech exception: {e}")

        # Fallback to vocal energy VAD so song vocals & music audio are also captured cleanly
        return self._is_speech_fallback(pcm_frame_bytes)

    def _is_speech_fallback(self, pcm_bytes: bytes) -> bool:
        """Fallback VAD using RMS energy calculation."""
        if not pcm_bytes:
            return False
            
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(audio_np) == 0:
            return False
            
        rms = float(np.abs(audio_np).mean() / 32768.0)
        
        # Slowly adapt baseline threshold to ambient noise
        if rms < self._adaptive_threshold:
            self._adaptive_threshold = 0.95 * self._adaptive_threshold + 0.05 * rms
            
        dynamic_cutoff = max(0.00015, self._adaptive_threshold * 1.3)
        return rms > dynamic_cutoff

