import logging
import sys
import threading
import time
import io
import queue
from typing import Optional, List, Tuple, Any

import numpy as np
import scipy.io.wavfile as wav
from PySide6.QtCore import QObject, Signal

from core.translator import TranslationManager
from services.voice_service import VoiceService, _patch_sr_with_sounddevice, _SD_AVAILABLE, _has_pyaudio
from services.vad_service import VoiceActivityDetector

logger = logging.getLogger(__name__)

# Try to import pyaudiowpatch for WASAPI Loopback system audio capture on Windows
_HAS_PYAUDIOWPATCH = False
try:
    import pyaudiowpatch as pyaudio
    sys.modules["pyaudio"] = pyaudio
    _HAS_PYAUDIOWPATCH = True
    logger.info("pyaudiowpatch initialized for Windows System Audio loopback capture.")
except ImportError:
    _HAS_PYAUDIOWPATCH = False
    logger.info("pyaudiowpatch not installed; system audio capture will fallback to default mic.")

try:
    import speech_recognition as sr
except ImportError:
    sr = None


class LiveCaptionService(QObject):
    """
    Producer-Consumer Real-Time Live Caption Service.
    
    Audio Producer Thread: Captures system/mic audio, runs WebRTC VAD & phrase segmentation, enqueues audio tasks.
    Parallel Consumer Worker Pool: Consumes tasks concurrently, performs WAV decimation/vocal filtering, handles Google API with retry logic.
    """
    caption_updated = Signal(str, str, str, str)  # (original_text, translated_text, source_lang, target_lang)
    status_changed = Signal(str)                   # Status string e.g. "Listening...", "Recognizing..."
    error_occurred = Signal(str)

    def __init__(self, translation_manager: TranslationManager, parent=None):
        super().__init__(parent)
        self.translation_mgr = translation_manager
        self.voice_service = VoiceService()
        
        self._lock = threading.Lock()
        self._is_running = False
        
        self._audio_thread: Optional[threading.Thread] = None
        self._worker_threads: List[threading.Thread] = []
        self._recog_queue: queue.Queue = queue.Queue(maxsize=10)
        
        self.vad = VoiceActivityDetector(mode=2)
        
        self.source_lang = "auto"
        self.target_lang = "ar"
        self.audio_source = "system"
        self.enable_translation = False
        self.provider = "google_free"
        self.api_key = ""
        
        # Performance tuning parameters
        self.vad_aggressiveness = 2
        self.silence_timeout = 0.25
        self.max_phrase_duration = 1.8
        self.queue_maxsize = 10
        self.overlap_duration = 0.25
        self.retry_delay = 0.1
        self.num_workers = 3
        
        self._last_emitted_text = ""

        _patch_sr_with_sounddevice()

    def is_available(self) -> bool:
        """Check if audio recording dependencies are present."""
        return self.voice_service.is_available() or _HAS_PYAUDIOWPATCH

    def start_captioning(self, source_lang: str = "auto", target_lang: str = "ar",
                         audio_source: str = "system", enable_translation: bool = False,
                         provider: str = "google_free", api_key: str = "",
                         vad_aggressiveness: int = 2, silence_timeout: float = 0.25,
                         max_phrase_duration: float = 1.8, queue_maxsize: int = 10,
                         overlap_duration: float = 0.25, retry_delay: float = 0.1,
                         num_workers: int = 3) -> None:
        """Start real-time parallel producer-consumer speech captioning."""
        if not self.is_available():
            self.error_occurred.emit(
                "Live Caption unavailable. Required dependencies missing:\n"
                "pip install SpeechRecognition pyaudiowpatch sounddevice scipy"
            )
            return

        with self._lock:
            if self._is_running:
                return

            self.source_lang = source_lang
            self.target_lang = target_lang
            self.audio_source = audio_source
            self.enable_translation = enable_translation
            self.provider = provider
            self.api_key = api_key
            
            self.vad_aggressiveness = vad_aggressiveness
            self.silence_timeout = silence_timeout
            self.max_phrase_duration = max_phrase_duration
            self.queue_maxsize = queue_maxsize
            self.overlap_duration = overlap_duration
            self.retry_delay = retry_delay
            self.num_workers = num_workers
            self._last_emitted_text = ""
            
            self.vad.set_aggressiveness(vad_aggressiveness)
            self._recog_queue = queue.Queue(maxsize=queue_maxsize)
            self._is_running = True

        # 1. Spawn Parallel Consumer Worker Pool
        self._worker_threads = []
        for i in range(num_workers):
            t = threading.Thread(
                target=self._recognition_worker_loop,
                name=f"LiveCaptionWorker-{i+1}",
                daemon=True
            )
            t.start()
            self._worker_threads.append(t)

        # 2. Audio Producer Thread
        self._audio_thread = threading.Thread(
            target=self._audio_producer_loop,
            name="LiveCaptionAudioProducer",
            daemon=True
        )
        self._audio_thread.start()
        
        self.status_changed.emit("Listening...")
        logger.info(f"Parallel Producer-Consumer started (Source: {audio_source}, Workers: {num_workers}, VAD: {vad_aggressiveness}).")

    def stop_captioning(self) -> None:
        """Stop audio producer and recognition worker threads cleanly."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False

        # Put poison pill sentinels into queue for all workers to exit cleanly
        for _ in range(self.num_workers):
            try:
                self._recog_queue.put_nowait(None)
            except Exception:
                pass

        self.status_changed.emit("Stopped")
        logger.info("Live Caption service stopped cleanly.")

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def update_settings(self, source_lang: str, target_lang: str, audio_source: str = "system",
                        enable_translation: bool = False, vad_aggressiveness: int = 2) -> None:
        """Update language, audio source, VAD, and translation mode on the fly."""
        with self._lock:
            self.source_lang = source_lang
            self.target_lang = target_lang
            self.audio_source = audio_source
            self.enable_translation = enable_translation
            self.vad_aggressiveness = vad_aggressiveness
            self.vad.set_aggressiveness(vad_aggressiveness)

    def _convert_and_resample_mono(self, audio_data: np.ndarray, channels: int, source_rate: int) -> bytes:
        """Fast conversion of raw audio array to 16kHz 16-bit mono WAV bytes with peak volume normalization."""
        if channels > 1:
            audio_data = audio_data.reshape(-1, channels)
            mono = audio_data.mean(axis=1).astype(np.float32)
        else:
            mono = audio_data.astype(np.float32)

        target_rate = 16000
        if source_rate == 48000:
            resampled = mono[::3]  # Fast 3x decimation 48kHz -> 16kHz
        elif source_rate != target_rate:
            import scipy.signal as signal
            num_samples = int(len(mono) * target_rate / source_rate)
            resampled_out = signal.resample(mono, num_samples)
            if isinstance(resampled_out, tuple):
                resampled_out = resampled_out[0]
            resampled = resampled_out.astype(np.float32)
        else:
            resampled = mono

        # Dynamic Peak Volume Normalization (brings singing vocals to clear 85% peak scale)
        max_val = np.max(np.abs(resampled))
        if max_val > 50.0:
            resampled = (resampled / max_val) * 28000.0

        resampled_int16 = resampled.astype(np.int16)

        buf = io.BytesIO()
        wav.write(buf, target_rate, resampled_int16)
        buf.seek(0)
        return buf.getvalue()

    def _recognize_with_retry(self, recognizer, audio_obj, lang_tag: Optional[str]) -> str:
        """
        Executes Google Speech recognition with 1-time retry on network API errors.
        Does NOT retry on UnknownValueError (non-speech audio).
        """
        if sr is None:
            raise RuntimeError("speech_recognition module is not installed")

        attempts = 0
        max_attempts = 2
        
        while attempts < max_attempts:
            attempts += 1
            try:
                return self.voice_service._recognize_with_fallback(recognizer, audio_obj, lang_tag)
            except sr.UnknownValueError:
                raise
            except (sr.RequestError, Exception) as err:
                if attempts < max_attempts:
                    logger.warning(f"Google Speech API network error (attempt {attempts}): {err}. Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    raise
        return ""

    def _recognition_worker_loop(self) -> None:
        """Consumer Worker Loop: pulls audio tasks from queue and transcribes via Google Speech API in parallel."""
        thread_name = threading.current_thread().name
        logger.info(f"Consumer Worker thread {thread_name} started.")
        
        while True:
            try:
                task = self._recog_queue.get(timeout=1.0)
            except queue.Empty:
                with self._lock:
                    if not self._is_running:
                        break
                continue

            if task is None:
                self._recog_queue.task_done()
                break  # Sentinel received -> terminate worker thread

            if sr is None:
                self._recog_queue.task_done()
                continue

            audio_data, channels, source_rate, lang_tag = task
            start_t = time.time()

            try:
                wav_bytes = self._convert_and_resample_mono(audio_data, channels, source_rate)
                buf = io.BytesIO(wav_bytes)

                recognizer = sr.Recognizer()
                with sr.AudioFile(buf) as src:
                    audio_obj = recognizer.record(src)

                self.status_changed.emit("Recognizing...")
                original_text = self._recognize_with_retry(recognizer, audio_obj, lang_tag)
                
                if original_text and original_text.strip():
                    cleaned_original = original_text.strip()
                    
                    # Prevent Duplicate Update Emissions
                    with self._lock:
                        if cleaned_original == self._last_emitted_text:
                            self.status_changed.emit("Listening...")
                            continue
                        self._last_emitted_text = cleaned_original
                        source_l = self.source_lang
                        target_l = self.target_lang
                        do_trans = self.enable_translation
                        prov = self.provider
                        key = self.api_key

                    latency_ms = int((time.time() - start_t) * 1000)
                    logger.info(f"Speech recognized ({source_l}) in {latency_ms}ms: {cleaned_original}")
                    
                    translated_text = ""
                    if do_trans:
                        try:
                            translated_text = self.translation_mgr.translate(
                                text=cleaned_original,
                                source_lang=source_l,
                                target_lang=target_l,
                                provider_name=prov,
                                api_key=key
                            )
                        except Exception as te:
                            logger.warning(f"Translation failed: {te}")
                            translated_text = cleaned_original

                    self.caption_updated.emit(cleaned_original, translated_text, source_l, target_l)

            except sr.UnknownValueError:
                pass
            except Exception as e:
                logger.debug(f"Recognition worker exception: {e}")
            finally:
                self.status_changed.emit("Listening...")
                self._recog_queue.task_done()


        logger.info(f"Consumer Worker thread {thread_name} finished.")

    def _enqueue_audio_chunk(self, audio_data: np.ndarray, channels: int, source_rate: int, lang_tag: Optional[str]) -> None:
        """Safe non-blocking producer enqueue with queue overflow protection."""
        task = (audio_data, channels, source_rate, lang_tag)
        try:
            self._recog_queue.put_nowait(task)
        except queue.Full:
            logger.warning("Recognition queue overflow! Dropping oldest pending audio chunk to maintain real-time latency.")
            try:
                self._recog_queue.get_nowait()
                self._recog_queue.task_done()
            except Exception:
                pass
            try:
                self._recog_queue.put_nowait(task)
            except Exception:
                pass

    def _audio_producer_loop(self) -> None:
        """Producer Loop: Continuous audio capture and WebRTC VAD phrase segmentation."""
        if sr is None:
            self.error_occurred.emit("speech_recognition library not installed.")
            with self._lock:
                self._is_running = False
            return

        while True:
            with self._lock:
                if not self._is_running:
                    break
                src_lang = self.source_lang
                audio_src = self.audio_source

            lang_tag = VoiceService._LANG_MAP.get(src_lang)
            if src_lang != "auto" and lang_tag is None:
                lang_tag = src_lang

            # ── WASAPI Loopback Capture (Desktop / Speakers) ─────────────────
            if audio_src == "system" and _HAS_PYAUDIOWPATCH:
                p = None
                stream = None
                try:
                    p = pyaudio.PyAudio()
                    loopback_dev = p.get_default_wasapi_loopback()
                    rate = int(loopback_dev.get("defaultSampleRate", 48000))
                    channels = int(loopback_dev.get("maxInputChannels", 2))
                    dev_index = loopback_dev.get("index")

                    chunk_size = 1024
                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=dev_index,
                        frames_per_buffer=chunk_size
                    )

                    audio_buffer: List[np.ndarray] = []
                    has_spoken = False
                    current_samples = 0
                    silence_samples = 0
                    
                    min_samples = int(rate * 0.5)
                    max_samples = int(rate * self.max_phrase_duration)
                    silence_limit = int(rate * self.silence_timeout)

                    while True:
                        with self._lock:
                            if not self._is_running or self.audio_source != "system":
                                break

                        try:
                            data = stream.read(chunk_size, exception_on_overflow=False)
                            if not data:
                                time.sleep(0.01)
                                continue

                            chunk_np = np.frombuffer(data, dtype=np.int16)
                            
                            # Downmix chunk to mono for VAD evaluation
                            if channels > 1:
                                mono_chunk = chunk_np.reshape(-1, channels).mean(axis=1).astype(np.int16)
                            else:
                                mono_chunk = chunk_np

                            is_speech = self.vad.is_speech(mono_chunk.tobytes(), frame_sample_rate=rate)

                            if is_speech:
                                if not has_spoken:
                                    has_spoken = True
                                    self.status_changed.emit("Listening...")
                                silence_samples = 0
                                audio_buffer.append(chunk_np)
                                current_samples += len(chunk_np)
                            elif has_spoken:
                                audio_buffer.append(chunk_np)
                                current_samples += len(chunk_np)
                                silence_samples += len(chunk_np)

                                if silence_samples >= silence_limit:
                                    if current_samples >= min_samples:
                                        concat_audio = np.concatenate(audio_buffer, axis=0)
                                        self._enqueue_audio_chunk(concat_audio, channels, rate, lang_tag)
                                    
                                    audio_buffer = []
                                    current_samples = 0
                                    silence_samples = 0
                                    has_spoken = False

                            if current_samples >= max_samples:
                                concat_audio = np.concatenate(audio_buffer, axis=0)
                                self._enqueue_audio_chunk(concat_audio, channels, rate, lang_tag)
                                
                                overlap_n = int((rate * self.overlap_duration) / chunk_size)
                                overlap_chunks = audio_buffer[-overlap_n:] if len(audio_buffer) >= overlap_n else audio_buffer
                                audio_buffer = list(overlap_chunks)
                                current_samples = sum(len(c) for c in audio_buffer)
                                silence_samples = 0

                        except Exception as read_err:
                            logger.debug(f"WASAPI read exception: {read_err}")
                            break

                except Exception as loop_init_err:
                    logger.warning(f"WASAPI stream error: {loop_init_err}")
                finally:
                    if stream is not None:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except Exception:
                            pass
                    if p is not None:
                        try:
                            p.terminate()
                        except Exception:
                            pass

            # ── Microphone Capture (Fallback or Mic mode) ────────────────────
            with self._lock:
                if not self._is_running:
                    break
                curr_audio_source = self.audio_source

            if curr_audio_source == "mic" or not _HAS_PYAUDIOWPATCH:
                try:
                    self.status_changed.emit("Listening...")
                    use_sd = _SD_AVAILABLE and not _has_pyaudio()
                    if use_sd:
                        try:
                            audio_data, sample_rate = self.voice_service._record_sounddevice_raw(
                                silence_duration=self.silence_timeout,
                                start_timeout=2.0,
                                sensitivity="medium"
                            )
                            with self._lock:
                                running = self._is_running
                            if running:
                                self._enqueue_audio_chunk(audio_data, 1, sample_rate, lang_tag)
                        except sr.WaitTimeoutError:
                            pass
                    else:
                        recognizer = sr.Recognizer()
                        with sr.Microphone() as source:
                            recognizer.adjust_for_ambient_noise(source, duration=0.2)
                            try:
                                audio = recognizer.listen(source, timeout=1.8, phrase_time_limit=self.max_phrase_duration)
                            except sr.WaitTimeoutError:
                                audio = None

                        if audio:
                            with self._lock:
                                running = self._is_running
                            if running:
                                self.status_changed.emit("Recognizing...")
                                try:
                                    original_text = self._recognize_with_retry(recognizer, audio, lang_tag)
                                    if original_text and original_text.strip():
                                        cleaned = original_text.strip()
                                        translated = ""
                                        if self.enable_translation:
                                            translated = self.translation_mgr.translate(
                                                text=cleaned,
                                                source_lang=self.source_lang,
                                                target_lang=self.target_lang,
                                                provider_name=self.provider,
                                                api_key=self.api_key
                                            )
                                        self.caption_updated.emit(cleaned, translated, self.source_lang, self.target_lang)
                                except Exception as rec_err:
                                    logger.debug(f"Mic recognition exception: {rec_err}")
                except Exception as mic_err:
                    logger.debug(f"Mic loop exception: {mic_err}")
                    time.sleep(0.3)

        logger.info("Live Caption Audio Producer thread finished.")
