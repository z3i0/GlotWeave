import logging
import threading
import tempfile
import os
from typing import Optional
# pyrefly: ignore [missing-import]
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Try to import speech_recognition
try:
    # pyrefly: ignore [missing-import]
    import speech_recognition as sr
except ImportError:
    sr = None

# Try to import sounddevice + scipy as pyaudio replacement
try:
    # pyrefly: ignore [missing-import]
    import sounddevice as sd
    # pyrefly: ignore [missing-import]
    import scipy.io.wavfile as wav
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False


def _has_pyaudio() -> bool:
    """Check if pyaudio package is installed without static import."""
    try:
        import importlib.util
        return importlib.util.find_spec("pyaudio") is not None
    except Exception:
        return False


# Monkey-patch speech_recognition to use sounddevice if pyaudio is missing
def _patch_sr_with_sounddevice() -> bool:
    """
    Patches speech_recognition.Microphone to use sounddevice as backend.
    Returns True if the patch is applied successfully.
    """
    if not _SD_AVAILABLE or sr is None:
        return False

    if _has_pyaudio():
        return True  # pyaudio is available, no patch needed

    # pyrefly: ignore [missing-import]
    import numpy as np
    import io

    class SoundDeviceMicrophone:
        """A drop-in replacement for sr.Microphone that uses sounddevice."""

        def __init__(self, device_index=None, sample_rate=16000, chunk_size=1024):
            self.device_index = device_index
            self.SAMPLE_RATE = sample_rate
            self.CHUNK = chunk_size
            self._audio_data = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    # Override sr.Microphone with our sounddevice-based one
    sr.Microphone = SoundDeviceMicrophone  # type: ignore[attr-defined]
    logger.info("Patched speech_recognition to use sounddevice backend.")
    return True


class VoiceService(QObject):
    """Handles speech-to-text recording using the system microphone."""
    recording_started = Signal()
    transcribing_started = Signal()
    recording_finished = Signal(str)  # Emits transcribed text
    recording_stopped = Signal()
    error_occurred = Signal(str)

    # Language code mapping: app code -> Google Speech API BCP-47 tag
    _LANG_MAP = {
        "auto": None,        # None = try multiple languages
        "en": "en-US",
        "ar": "ar-SA",
        "fr": "fr-FR",
        "es": "es-ES",
        "de": "de-DE",
        "zh": "zh-CN",
        "ja": "ja-JP",
        "tr": "tr-TR",
        "it": "it-IT",
        "pt": "pt-PT",
        "ru": "ru-RU",
        "ko": "ko-KR",
        "hi": "hi-IN",
        "nl": "nl-NL",
        "pl": "pl-PL",
        "uk": "uk-UA",
        "id": "id-ID",
        "sv": "sv-SE",
        "da": "da-DK",
        "fi": "fi-FI",
        "el": "el-GR",
        "he": "he-IL",
        "th": "th-TH",
        "vi": "vi-VN",
    }

    # Languages tried (in order) when source is set to Auto
    _AUTO_LANGS = ["ar-SA", "en-US", "fr-FR", "es-ES", "de-DE", "zh-CN", "ja-JP"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_recording = False
        self._thread: Optional[threading.Thread] = None
        # Attempt to patch sr with sounddevice on startup
        _patch_sr_with_sounddevice()

    def is_available(self) -> bool:
        """Check if required libraries are installed."""
        if sr is None:
            return False
        if _has_pyaudio():
            return True
        return _SD_AVAILABLE

    def start_recording(self, language: str = "en", continuous: bool = False,
                        silence_duration: float = 2.0, start_timeout: float = 5.0,
                        sensitivity: str = "medium") -> None:
        """Start listening to the microphone in a background thread."""
        if not self.is_available():
            self.error_occurred.emit(
                "Voice input unavailable. Install dependencies:\n"
                "pip install SpeechRecognition sounddevice scipy"
            )
            return

        if self._is_recording:
            return

        self._is_recording = True
        self._thread = threading.Thread(
            target=self._record_and_transcribe,
            args=(language, continuous, silence_duration, start_timeout, sensitivity),
            daemon=True
        )
        self._thread.start()

    def stop_recording(self) -> None:
        """Signal the recording thread to stop."""
        self._is_recording = False

    def _record_sounddevice_raw(self, silence_duration: float = 2.0, start_timeout: float = 5.0,
                                sensitivity: str = "medium"):
        """
        Record from microphone using sounddevice.
        Returns (numpy_audio_data, sample_rate) for further processing.
        """
        if sr is None:
            raise RuntimeError("speech_recognition library is not available.")

        # pyrefly: ignore [missing-import]
        import numpy as np

        SAMPLE_RATE = 16000
        DURATION = 30  # seconds max
        START_TIMEOUT = start_timeout  # seconds to wait for speech to start
        SILENCE_DURATION = silence_duration  # seconds of continuous silence after speech started
        
        # Map sensitivity string to float threshold
        sens_map = {
            "high": 0.0015,
            "medium": 0.003,
            "low": 0.006
        }
        SILENCE_THRESHOLD = sens_map.get(sensitivity, 0.003)

        logger.info("sounddevice: Starting microphone capture...")
        self.recording_started.emit()

        frames = []
        silence_chunks = 0
        chunk_size = int(SAMPLE_RATE * 0.05)  # 50ms chunks for high responsiveness
        silence_limit = int(SILENCE_DURATION / 0.05)
        has_spoken = False

        def callback(indata, frame_count, time_info, status):
            frames.append(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                            blocksize=chunk_size, callback=callback):
            logger.info("sounddevice: Listening...")
            elapsed = 0
            while elapsed < DURATION and self._is_recording:
                sd.sleep(50)  # 50ms check interval
                elapsed += 0.05
                if frames:
                    last = frames[-1]
                    
                    # Convert to float to prevent overflow/underflow during mean subtraction
                    last_float = last.astype(np.float32)
                    # Remove DC offset to normalize across different mics/soundcards
                    last_zero_mean = last_float - np.mean(last_float)
                    amplitude = np.abs(last_zero_mean).mean() / 32768.0
                    
                    if amplitude > SILENCE_THRESHOLD:
                        if not has_spoken:
                            has_spoken = True
                            logger.info("sounddevice: Speech detected, starting recording.")
                        silence_chunks = 0
                    else:
                        silence_chunks += 1
                    
                    # If the user hasn't spoken and start timeout is reached, stop early
                    if not has_spoken and elapsed > START_TIMEOUT:
                        logger.info("sounddevice: No speech detected within timeout, stopping.")
                        break
                        
                    # Once they have spoken, stop early if silence persists for SILENCE_DURATION
                    if has_spoken and silence_chunks >= silence_limit:
                        logger.info("sounddevice: Silence detected after speech, stopping early.")
                        break

        if not frames:
            raise sr.WaitTimeoutError()  # type: ignore[attr-defined]

        # If we exited due to start timeout and never detected speech, and it wasn't a manual stop
        if not has_spoken and self._is_recording:
            raise sr.WaitTimeoutError()

        audio_data = np.concatenate(frames, axis=0)
        return audio_data, SAMPLE_RATE

    def _recognize_with_fallback(self, recognizer, audio, lang_tag: str | None) -> str:
        """
        Try to transcribe audio with the given language.
        If lang_tag is Arabic ('ar', 'ar-SA', 'ar-EG'), queries Arabic dialects in parallel.
        If lang_tag is None (Auto mode), queries candidates concurrently and prioritizes Arabic script.
        """
        if sr is None:
            raise RuntimeError("speech_recognition library is not available.")

        from concurrent.futures import ThreadPoolExecutor

        def _try_lang(candidate):
            try:
                res = recognizer.recognize_google(audio, language=candidate)
                if res and res.strip():
                    return candidate, res.strip()
            except Exception:
                pass
            return None

        if lang_tag is not None:
            if lang_tag in ("ar", "ar-SA", "ar-EG"):
                ar_candidates = ["ar-EG", "ar-SA", "ar-AE", "ar-JO"]
                with ThreadPoolExecutor(max_workers=len(ar_candidates)) as executor:
                    futures = [executor.submit(_try_lang, lang) for lang in ar_candidates]
                    for future in futures:
                        res = future.result()
                        if res:
                            return res[1]
                raise sr.UnknownValueError()
            else:
                return recognizer.recognize_google(audio, language=lang_tag)

        # Auto mode: query candidates concurrently
        candidates = ["ar-EG", "ar-SA", "en-US", "fr-FR", "es-ES"]
        results = []
        with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
            futures = [executor.submit(_try_lang, lang) for lang in candidates]
            for future in futures:
                res = future.result()
                if res:
                    results.append(res)

        if not results:
            raise sr.UnknownValueError()

        # Prioritize Arabic script if present in any returned candidate!
        for lang, text in results:
            if any('\u0600' <= char <= '\u06FF' for char in text):
                logger.info(f"Auto-detected Arabic speech ({lang}): {text}")
                return text

        # Otherwise return the first successful result
        lang, text = results[0]
        logger.info(f"Auto-detected speech ({lang}): {text}")
        return text

    def _record_and_transcribe(self, language: str, continuous: bool = False,
                                silence_duration: float = 2.0, start_timeout: float = 5.0,
                                sensitivity: str = "medium") -> None:
        """Background thread worker: record from microphone and transcribe."""
        if sr is None:
            logger.error("speech_recognition library is not available.")
            self.error_occurred.emit("Speech recognition library not installed.")
            self._is_recording = False
            self.recording_stopped.emit()
            return

        assert sr is not None
        lang_tag = self._LANG_MAP.get(language)  # None = auto multi-language

        while self._is_recording:
            try:
                # Prefer sounddevice path if pyaudio is unavailable
                use_sd = _SD_AVAILABLE and not _has_pyaudio()

                if use_sd:
                    try:
                        audio_data, sample_rate = self._record_sounddevice_raw(
                            silence_duration=silence_duration,
                            start_timeout=start_timeout,
                            sensitivity=sensitivity
                        )
                    except sr.WaitTimeoutError:
                        if continuous and self._is_recording:
                            continue
                        raise

                    recognizer = sr.Recognizer()

                    import io
                    # pyrefly: ignore [missing-import]
                    import scipy.io.wavfile as wav
                    buf = io.BytesIO()
                    wav.write(buf, sample_rate, audio_data)
                    buf.seek(0)

                    with sr.AudioFile(buf) as src:
                        audio_obj = recognizer.record(src)
                    self.transcribing_started.emit()
                    text = self._recognize_with_fallback(recognizer, audio_obj, lang_tag)

                    logger.info(f"Speech transcribed (sounddevice): {text}")
                    self.recording_finished.emit(text)
                    
                    if not continuous:
                        break

                else:
                    # Standard pyaudio path via speech_recognition
                    self.recording_started.emit()
                    recognizer = sr.Recognizer()
                    with sr.Microphone() as source:
                        logger.info("Microphone open, adjusting for ambient noise...")
                        recognizer.adjust_for_ambient_noise(source, duration=0.8)
                        logger.info("Listening for speech...")
                        try:
                            audio = recognizer.listen(source, timeout=5.0, phrase_time_limit=10.0)
                        except sr.WaitTimeoutError:
                            if continuous and self._is_recording:
                                continue
                            raise

                    if not self._is_recording:
                        break

                    logger.info("Speech captured. Sending for transcription...")
                    self.transcribing_started.emit()
                    text = self._recognize_with_fallback(recognizer, audio, lang_tag)
                    logger.info(f"Speech transcribed: {text}")
                    self.recording_finished.emit(text)
                    
                    if not continuous:
                        break

            except OSError as e:
                logger.error(f"Microphone access error: {e}")
                self.error_occurred.emit(
                    "Could not access microphone.\n"
                    "Ensure sounddevice is installed: pip install sounddevice scipy"
                )
                break
            except sr.WaitTimeoutError:
                logger.info("Listening timed out. No speech detected.")
                break
            except sr.UnknownValueError:
                logger.info("Could not understand audio or no speech detected.")
                if not continuous:
                    break
            except sr.RequestError as e:
                logger.error(f"Speech API request error: {e}")
                self.error_occurred.emit(f"Speech API error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected speech recognition failure: {e}")
                self.error_occurred.emit(f"Recording error: {e}")
                break
        
        self._is_recording = False
        self.recording_stopped.emit()
        logger.info("Voice recording thread finished.")
