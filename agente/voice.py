import queue
import threading
import subprocess
import sys
import os
import re
import config

_speech_queue = queue.Queue()
TTS_AVAILABLE = True
_parar_flag = threading.Event()
_proc_ref = [None]  # processo de fala atual (backend Windows)
is_speaking = False  # True enquanto Evelyn está falando (usado para silenciar mic)


def _split_text_for_tts(texto: str, max_chars: int = 280):
    """Divide textos longos em blocos menores para evitar truncamento no TTS."""
    raw = re.sub(r"\s+", " ", (texto or "").strip())
    if not raw:
        return []

    sentences = re.split(r"(?<=[\.!\?;:])\s+", raw)
    chunks = []
    current = ""

    for sent in sentences:
        s = sent.strip()
        if not s:
            continue

        # Frases muito longas: corta em fatias para manter estabilidade.
        if len(s) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(s), max_chars):
                part = s[i:i + max_chars].strip()
                if part:
                    chunks.append(part)
            continue

        if not current:
            current = s
            continue

        if len(current) + 1 + len(s) <= max_chars:
            current = f"{current} {s}"
        else:
            chunks.append(current)
            current = s

    if current:
        chunks.append(current)
    return chunks


def _estimate_timeout_seconds(texto: str, min_timeout: int = 20, max_timeout: int = 180) -> int:
    """Calcula timeout aproximado com base no tamanho do texto e velocidade de fala."""
    words = max(1, len((texto or "").split()))
    rate = max(90, int(getattr(config, "VOICE_RATE", 150) or 150))
    speaking_seconds = int((words / rate) * 60)
    timeout = speaking_seconds + 15
    return max(min_timeout, min(max_timeout, timeout))


def _map_rate_to_sapi(rate_wpm: int) -> int:
    # pyttsx3 usa wpm (~120-220); SAPI usa -10..10
    # Mapeamento ajustado para evitar voz lenta demais no Windows.
    return max(-2, min(8, int(round((int(rate_wpm) - 145) / 6))))


def _falar_windows(texto: str):
    """Usa SAPI nativo via PowerShell com voz em português se disponível."""
    global TTS_AVAILABLE
    txt = (texto or "").replace("'", "''")
    sapi_rate = _map_rate_to_sapi(getattr(config, "VOICE_RATE", 150))
    cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$voices = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | "
        "Where-Object { $_.Culture.Name -like 'pt-*' -or $_.Name -like '*Maria*' -or $_.Name -like '*Helena*' }; "
        "if ($voices) { $s.SelectVoice($voices[0].Name) }; "
        f"$s.Rate = {sapi_rate}; "
        "$s.Volume = 100; "
        f"$s.Speak('{txt}')"
    )
    startupinfo = None
    creationflags = 0
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    _proc_ref[0] = proc
    try:
        rc = proc.wait(timeout=_estimate_timeout_seconds(texto))
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass
        _proc_ref[0] = None
        TTS_AVAILABLE = False
        raise RuntimeError("Timeout no backend SAPI")
    stderr_out = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    _proc_ref[0] = None
    if rc != 0:
        TTS_AVAILABLE = False
        raise RuntimeError(f"Falha no backend de voz (exit={rc}): {stderr_out[:200]}")
    TTS_AVAILABLE = True


def _falar_pyttsx3(texto: str):
    """Executa pyttsx3 num subprocesso para evitar problemas de COM threading."""
    global TTS_AVAILABLE
    rate = getattr(config, "VOICE_RATE", 150)
    # Sanitiza o texto para uso dentro de string Python
    txt = texto.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    code = (
        "import pyttsx3; e=pyttsx3.init(); "
        f'e.setProperty("rate",{rate}); e.setProperty("volume",0.9); '
        f'e.say("{txt}"); e.runAndWait(); e.stop()'
    )
    # Garante uso de python.exe (não pythonw.exe) para que o subprocesso funcione
    python_exe = sys.executable.replace("pythonw.exe", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    startupinfo = None
    creationflags = 0
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(
        [python_exe, "-c", code],
        timeout=_estimate_timeout_seconds(texto),
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    TTS_AVAILABLE = True
    if proc.returncode != 0:
        raise RuntimeError(f"pyttsx3 subprocess falhou (exit={proc.returncode})")


def _falar_agora(texto: str):
    global is_speaking
    is_speaking = True
    try:
        for chunk in _split_text_for_tts(texto):
            if _parar_flag.is_set():
                break
            if sys.platform.startswith("win"):
                _falar_windows(chunk)
            else:
                _falar_pyttsx3(chunk)
    finally:
        is_speaking = False


def _voice_worker():
    global TTS_AVAILABLE
    while True:
        texto = _speech_queue.get()
        if texto is None:
            _speech_queue.task_done()
            break
        try:
            # Descarta itens acumulados, fala só o mais recente
            textos = [texto]
            while not _speech_queue.empty():
                try:
                    textos.append(_speech_queue.get_nowait())
                    _speech_queue.task_done()
                except Exception:
                    break
            falar_texto = textos[-1]

            if _parar_flag.is_set():
                _parar_flag.clear()
                continue

            TTS_AVAILABLE = True  # reseta antes de tentar
            _falar_agora(falar_texto)
            _parar_flag.clear()
        except Exception as e:
            TTS_AVAILABLE = True  # reseta para tentar na próxima
            print(f"[voice] Erro TTS: {e}")
        finally:
            _speech_queue.task_done()


threading.Thread(target=_voice_worker, daemon=True).start()


def parar():
    """Para a fala imediatamente e limpa a fila."""
    _parar_flag.set()
    while not _speech_queue.empty():
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
        except Exception:
            break
    proc = _proc_ref[0]
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    _proc_ref[0] = None


def falar(texto, silent=False):
    """Enfileira o texto para falar."""
    print(f"\n{config.AGENT_NAME}: {texto}\n")
    if silent or not config.VOICE_ENABLED:
        return
    t = (texto or "").strip()
    if not t:
        return
    _speech_queue.put(t)
