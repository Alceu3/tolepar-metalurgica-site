try:
    import speech_recognition as sr
    import config
    import numpy as _np
    _recognizer = sr.Recognizer()
    _recognizer.dynamic_energy_threshold = True
    _recognizer.pause_threshold = 0.7
    _recognizer.non_speaking_duration = 0.3
    # SpeechRecognition pode importar mesmo sem PyAudio; valida explicitamente.
    try:
        sr.Microphone.get_pyaudio()
        MIC_AVAILABLE = True
        MIC_BACKEND = "pyaudio"
        MIC_ERROR = ""
    except Exception as e:
        try:
            import sounddevice as sd
            _sd = sd
            MIC_AVAILABLE = True
            MIC_BACKEND = "sounddevice"
            MIC_ERROR = ""
        except Exception as e2:
            MIC_AVAILABLE = False
            MIC_BACKEND = "none"
            MIC_ERROR = f"PyAudio indisponivel ({e}); fallback sounddevice falhou ({e2})"
except ImportError as e:
    MIC_AVAILABLE = False
    MIC_BACKEND = "none"
    MIC_ERROR = f"SpeechRecognition indisponivel: {e}"


def _get_mic_index_sr():
    if not MIC_AVAILABLE:
        return None

    # Prioridade 1: índice fixo configurado.
    configured_index = getattr(config, "MIC_DEVICE_INDEX", None)
    if configured_index is not None:
        return configured_index

    # Prioridade 2: procurar por trecho do nome do dispositivo.
    name_hint = str(getattr(config, "MIC_NAME_CONTAINS", "") or "").strip().lower()
    if name_hint:
        try:
            for idx, name in enumerate(sr.Microphone.list_microphone_names()):
                if name_hint in (name or "").lower():
                    return idx
        except Exception:
            pass

    # Prioridade 3: padrão do sistema.
    return None


def _get_mic_index_sd():
    """Escolhe índice válido para sounddevice (lista própria do PortAudio)."""
    if not MIC_AVAILABLE or MIC_BACKEND != "sounddevice":
        return None

    # Prioridade 1: índice fixo configurado.
    configured_index = getattr(config, "MIC_DEVICE_INDEX", None)
    if configured_index is not None:
        return configured_index

    # Prioridade 2: usar primeiro device com score positivo (skip default do sistema)
    try:
        devices = _sd.query_devices()
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            name = str(dev.get("name", "")).lower()
            
            # Prefer microfone, input, headset
            if any(k in name for k in ("microfone", "mic", "input")):
                if not any(k in name for k in ("output", "alto-falante", "speaker")):
                    return idx
            
            # Accept headset if has "headset"
            if "headset" in name and not any(k in name for k in ("output", "speaker")):
                return idx
            
            # Accept "grupo de microfones" que captura
            if "grupo de microfone" in name:
                return idx
    except Exception:
        pass

    # Fallback: None (tentará candidates)
    return None


def _candidate_mic_indices_sd():
    """Retorna candidatos de microfone para fallback no sounddevice."""
    if not MIC_AVAILABLE or MIC_BACKEND != "sounddevice":
        return []

    indices = []

    primary = _get_mic_index_sd()
    if isinstance(primary, int) and primary >= 0:
        indices.append(primary)

    try:
        default_in = _sd.default.device[0] if isinstance(_sd.default.device, (list, tuple)) else _sd.default.device
        if isinstance(default_in, int) and default_in >= 0 and default_in not in indices:
            indices.append(default_in)
    except Exception:
        pass

    try:
        scored = []
        for idx, dev in enumerate(_sd.query_devices()):
            if dev.get("max_input_channels", 0) <= 0 or idx in indices:
                continue
            name = str(dev.get("name", "")).lower()
            score = 0
            if any(k in name for k in ("microfone", "mic", "headset", "input")):
                score += 3
            if "realtek" in name:
                score += 2
            if any(k in name for k in ("output", "alto-falante", "speaker", "fones de ouvido", "headphone")):
                score -= 3
            scored.append((score, idx))

        for _, idx in sorted(scored, reverse=True):
            indices.append(idx)
    except Exception:
        pass

    return indices[:5]


def _capture_vad(device_index, max_secs=7):
    """Captura simples: grava até 5s se houver qualquer áudio detectado."""
    sample_rate = 16000
    try:
        dev = _sd.query_devices(device_index)
        native_sr = int(dev.get("default_samplerate", 0) or 0)
        if native_sr >= 8000:
            sample_rate = native_sr
    except Exception:
        pass

    # Grava um máximo de 5 segundos
    total_frames = int(5 * sample_rate)
    
    try:
        audio = _sd.rec(total_frames, samplerate=sample_rate, channels=1,
                        dtype="int16", device=device_index)
        _sd.wait()
    except Exception:
        return None

    # Verifica se tem qualquer som (não zero)
    peak = int(_np.abs(audio).max()) if audio.size else 0
    if peak < 10:
        return None

    raw_bytes = audio.tobytes()
    return sr.AudioData(raw_bytes, sample_rate, 2)


def _capture_with_sounddevice(timeout=10, phrase_time_limit=15):
    """Tenta capturar áudio no primary device, sem fallback confuso."""
    mic_index = _get_mic_index_sd()
    if mic_index is None:
        return None
    try:
        return _capture_vad(mic_index, max_secs=min(int(phrase_time_limit), 7))
    except Exception as e:
        print(f"[hearing] Device {mic_index} falhou: {e}")
        return None


def _capture_with_sounddevice_on_device(device_index, timeout=10, phrase_time_limit=15):
    return _capture_vad(device_index, max_secs=min(int(phrase_time_limit), 7))


def ouvir(timeout=10, phrase_time_limit=15):
    """Ouve o microfone e retorna o texto transcrito (ou None)."""
    if not MIC_AVAILABLE:
        detalhe = f" ({MIC_ERROR})" if MIC_ERROR else ""
        print(f"[hearing] Microfone indisponivel{detalhe} — modo texto ativo.")
        return None

    try:
        print("🎤  Ouvindo... (fale agora)")
        if MIC_BACKEND == "pyaudio":
            mic_index = _get_mic_index_sr()
            with sr.Microphone(device_index=mic_index) as source:
                _recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = _recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
        else:
            # Tenta no dispositivo principal e faz fallback em outros inputs.
            for dev_idx in _candidate_mic_indices_sd():
                audio = _capture_with_sounddevice_on_device(
                    dev_idx,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
                if audio is None:
                    continue
                try:
                    texto = _recognizer.recognize_google(audio, language="pt-BR")
                    print(f"Você (voz): {texto} [dev={dev_idx}]")
                    return texto
                except sr.UnknownValueError:
                    continue
            return None

        texto = _recognizer.recognize_google(audio, language="pt-BR")
        print(f"Você (voz): {texto}")
        return texto

    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        print("[hearing] Não entendi. Tente novamente.")
        return None
    except Exception as e:
        print(f"[hearing] Erro: {e}")
        return None
