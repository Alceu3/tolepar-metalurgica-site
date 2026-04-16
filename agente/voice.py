import queue
import threading
import config

_speech_queue = queue.Queue()
TTS_AVAILABLE = True


def _falar_agora(texto: str):
    """Cria engine nova, fala e destrói — evita bug SAPI5 em chamadas repetidas."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", config.VOICE_RATE)
    engine.setProperty("volume", 0.9)
    for v in engine.getProperty("voices"):
        if any(k in v.id.lower() for k in ("brazil", "pt_br", "portuguese")):
            engine.setProperty("voice", v.id)
            break
    engine.say(texto)
    engine.runAndWait()
    engine.stop()


def _voice_worker():
    global TTS_AVAILABLE
    # Testa se pyttsx3 está disponível
    try:
        _falar_agora("")
    except Exception as e:
        print(f"[voice] pyttsx3 indisponível: {e}")
        TTS_AVAILABLE = False
        while True:
            _speech_queue.get()
            _speech_queue.task_done()
        return

    while True:
        texto = _speech_queue.get()
        if texto is None:
            _speech_queue.task_done()
            break
        try:
            _falar_agora(texto)
        except Exception as e:
            print(f"[voice] Erro TTS: {e}")
        finally:
            _speech_queue.task_done()


threading.Thread(target=_voice_worker, daemon=True).start()


def falar(texto, silent=False):
    """Enfileira o texto para falar."""
    print(f"\n{config.AGENT_NAME}: {texto}\n")
    if silent or not config.VOICE_ENABLED or not TTS_AVAILABLE:
        return
    t = (texto or "").strip()
    if not t:
        return
    _speech_queue.put(t)
