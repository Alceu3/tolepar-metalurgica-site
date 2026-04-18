"""
hearing.py â€” Captura de voz com VAD eficiente + transcriÃ§Ã£o via OpenAI Whisper.
"""
import io
import os
import threading
import wave

import config

# --------------------------------------------------------------------------- #
# InicializaÃ§Ã£o do backend de Ã¡udio                                            #
# --------------------------------------------------------------------------- #
try:
    import sounddevice as _sd
    import numpy as _np
    _AUDIO_AVAILABLE = True
    _AUDIO_ERROR = ""
except Exception as _e:
    _AUDIO_AVAILABLE = False
    _AUDIO_ERROR = f"sounddevice indisponÃ­vel: {_e}"

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

MIC_AVAILABLE = _AUDIO_AVAILABLE
MIC_BACKEND   = "sounddevice" if _AUDIO_AVAILABLE else "none"
MIC_ERROR     = _AUDIO_ERROR


# --------------------------------------------------------------------------- #
# SeleÃ§Ã£o do microfone                                                         #
# --------------------------------------------------------------------------- #
def _device_works(idx):
    """Verifica rapidamente se o device abre sem erro."""
    try:
        audio = _sd.rec(int(16000 * 0.1), samplerate=16000, channels=1,
                        dtype="int16", device=idx)
        _sd.wait()
        return True
    except Exception:
        return False


def _device_peak(idx, timeout=2.0):
    """Retorna nÃ­vel de pico do device usando sd.rec() com timeout."""
    result = [-1]
    def _run():
        try:
            dev = _sd.query_devices(idx)
            ch = min(int(dev.get("max_input_channels", 1)), 2)
            sr = int(dev.get("default_samplerate", 16000) or 16000)
            audio = _sd.rec(int(sr * 0.15), samplerate=sr,
                            channels=ch, dtype="int16", device=idx)
            _sd.wait()
            result[0] = int(_np.abs(audio).max())
        except Exception:
            result[0] = -1
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


_cached_mic_idx = [None]


def _best_mic_index():
    """Retorna o Ã­ndice do melhor microfone disponÃ­vel (testado de verdade)."""
    # Recarrega do config em tempo real (pode ter mudado sem reiniciar)
    idx_cfg = getattr(config, "MIC_DEVICE_INDEX", None)
    if idx_cfg is not None:
        _cached_mic_idx[0] = int(idx_cfg)
        return _cached_mic_idx[0]

    # Com MIC_DEVICE_INDEX=None, sempre refaz detecÃ§Ã£o â€” nunca usa cache fixo
    _cached_mic_idx[0] = None

    try:
        devices = _sd.query_devices()
    except Exception:
        return None

    # Hint manual de config
    hint = str(getattr(config, "MIC_NAME_CONTAINS", "") or "").strip().lower()
    if hint:
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) > 0 and hint in d.get("name", "").lower():
                if _device_peak(i) >= 0:
                    _cached_mic_idx[0] = i
                    return i

    # Palavras-chave que identificam loopback/saÃ­da disfarÃ§ada de input
    LOOPBACK_KEYS = ("alto-falante", "speaker", "mixagem", "stereo mix",
                     "mixagem estÃ©reo", "what u hear", "wave out",
                     "btha2dp", "2nd output", "stereo input")
    # Palavras-chave que identificam microfones reais
    MIC_KEYS = ("microfone", "microphone", "mic", "headset",
                "grupo de microfones")

    # Filtra sÃ³ inputs, sem canais de saÃ­da
    all_inputs = [
        i for i, d in enumerate(devices)
        if d.get("max_input_channels", 0) > 0
        and d.get("max_output_channels", 0) == 0
    ]

    # Separar em "mic real" vs "suspeito de loopback"
    def _is_loopback(d):
        name = d.get("name", "").lower()
        return any(k in name for k in LOOPBACK_KEYS)

    def _is_real_mic(d):
        name = d.get("name", "").lower()
        return any(k in name for k in MIC_KEYS)

    real_mics = [i for i in all_inputs if _is_real_mic(devices[i])
                 and not _is_loopback(devices[i])]
    others    = [i for i in all_inputs if i not in real_mics
                 and not _is_loopback(devices[i])]

    # Prefere mic real; se nÃ£o achar, tenta outros nÃ£o-loopback
    for pool in (real_mics, others):
        best_idx  = None
        best_peak = -1
        for i in pool:
            peak = _device_peak(i)
            if peak > best_peak:
                best_peak = peak
                best_idx  = i
        if best_idx is not None and best_peak > 0:
            _cached_mic_idx[0] = best_idx
            return best_idx

    _cached_mic_idx[0] = None
    return None


def transcrever_arquivo_whisper(file_bytes, filename="audio.webm", content_type="audio/webm"):
    """Envia um arquivo de audio (webm/ogg/wav/mp4) direto para Whisper."""
    api_key = getattr(config, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key or not _REQUESTS_OK:
        return None

    if not file_bytes:
        return None

    try:
        resp = _requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, file_bytes, content_type or "application/octet-stream")},
            data={"model": "whisper-1", "language": "pt"},
            timeout=20,
        )
        if resp.status_code == 200:
            return (resp.json().get("text") or "").strip()
        print(f"[hearing] Whisper arquivo erro {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[hearing] Whisper arquivo exceção: {e}")
    return None


# --------------------------------------------------------------------------- #
# Captura com VAD via sd.rec() â€” Ãºnico mÃ©todo que funciona em WDM-KS          #
# --------------------------------------------------------------------------- #
def _capturar_audio(device_index, max_secs=10):
    """
    Grava com VAD usando sd.rec(). Para ao detectar silÃªncio.
    Retorna (pcm_bytes, 16000) ou None.
    """
    SAMPLE_RATE  = 16000
    CHUNK_MS     = 100
    SILENCE_MS   = 700
    SILENCE_N    = int(SILENCE_MS / CHUNK_MS)
    MAX_CHUNKS   = int(max_secs * 1000 / CHUNK_MS)
    MIN_SPEECH_N = 2

    try:
        dev_info = _sd.query_devices(device_index)
        dev_ch = min(int(dev_info.get("max_input_channels", 1)), 2)
        dev_sr = int(dev_info.get("default_samplerate", 16000) or 16000)
    except Exception:
        dev_ch = 1
        dev_sr = 16000

    CHUNK_FRAMES = int(dev_sr * CHUNK_MS / 1000)

    # Calibra ruÃ­do com 2 chunks iniciais
    noise_level = 120
    try:
        calib = _sd.rec(CHUNK_FRAMES * 2, samplerate=dev_sr,
                        channels=dev_ch, dtype="int16", device=device_index)
        _sd.wait()
        # Em vÃ¡rios notebooks/headsets o nÃ­vel mÃ©dio fica baixo (<100),
        # entÃ£o um limiar mÃ­nimo alto fazia a fala nunca ser detectada.
        calib_mean = int(_np.abs(calib).mean())
        noise_level = max(calib_mean * 2, 40)  # limiar mais sensível para notebook
    except Exception:
        pass

    frames_buf = []
    silent_n   = 0
    speech_n   = 0
    started    = False

    for _ in range(MAX_CHUNKS):
        try:
            chunk = _sd.rec(CHUNK_FRAMES, samplerate=dev_sr,
                            channels=dev_ch, dtype="int16", device=device_index)
            _sd.wait()
        except Exception as e:
            print(f"[hearing] erro ao gravar chunk: {e}")
            break  # para no primeiro erro, nÃ£o fica em loop infinito

        mono = chunk.mean(axis=1).astype("int16") if dev_ch > 1 else chunk.flatten()
        level = int(_np.abs(mono).mean())
        is_speech = level > noise_level

        if is_speech:
            speech_n += 1
            silent_n = 0
            if not started and speech_n >= 2:
                started = True
            if started:
                frames_buf.append(mono)
        else:
            if started:
                frames_buf.append(mono)
                silent_n += 1
                if silent_n >= SILENCE_N:
                    break

    if not frames_buf or speech_n < MIN_SPEECH_N:
        return None

    audio = _np.concatenate(frames_buf).astype("int16")
    if dev_sr != SAMPLE_RATE:
        ratio = SAMPLE_RATE / dev_sr
        new_len = int(len(audio) * ratio)
        indices = _np.clip((_np.arange(new_len) / ratio).astype(int), 0, len(audio) - 1)
        audio = audio[indices]
    return audio.tobytes(), SAMPLE_RATE


# --------------------------------------------------------------------------- #
# TranscriÃ§Ã£o via OpenAI Whisper                                               #
# --------------------------------------------------------------------------- #
def _transcrever_whisper(pcm_bytes, sample_rate):
    """Envia Ã¡udio PCM para OpenAI Whisper e retorna texto."""
    api_key = getattr(config, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key or not _REQUESTS_OK:
        return None

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)

    try:
        resp = _requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.wav", buf, "audio/wav")},
            data={"model": "whisper-1", "language": "pt"},
            timeout=15,
        )
        if resp.status_code == 200:
            return (resp.json().get("text") or "").strip()
        print(f"[hearing] Whisper erro {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[hearing] Whisper exceÃ§Ã£o: {e}")
    return None


# --------------------------------------------------------------------------- #
# API pÃºblica                                                                  #
# --------------------------------------------------------------------------- #
def ouvir(timeout=10, phrase_time_limit=12):
    """Ouve o microfone e retorna o texto transcrito (ou None)."""
    if not MIC_AVAILABLE:
        print(f"[hearing] Microfone indisponÃ­vel ({MIC_ERROR}) â€” modo texto.")
        return None

    mic_idx = _best_mic_index()
    if mic_idx is None:
        print("[hearing] Nenhum microfone encontrado.")
        return None

    print("ðŸŽ¤  Ouvindo... (fale agora)")
    result = _capturar_audio(mic_idx, max_secs=min(phrase_time_limit, 12))
    if result is None:
        return None

    pcm_bytes, sample_rate = result
    print("[hearing] Transcrevendo com Whisper...")
    texto = _transcrever_whisper(pcm_bytes, sample_rate)
    if texto:
        print(f"VocÃª (voz): {texto}")
    return texto or None
