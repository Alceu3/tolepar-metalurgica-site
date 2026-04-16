import base64
import os
import time

import requests
from PIL import ImageGrab

import config

_TEMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_screen_temp.png")


def capturar_base64(max_w=1280):
    img = ImageGrab.grab()
    # Reduz resolução para acelerar inferência de visão local.
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)))
    # JPEG deixa payload menor e acelera envio para o modelo.
    img = img.convert("RGB")
    img.save(_TEMP, format="JPEG", optimize=True, quality=68)
    with open(_TEMP, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _descrever_tela_ollama(pergunta):
    # Dois passes: tenta resolução média e depois menor caso retorne vazio/timeout.
    last_error = ""
    for max_w in (960, 640):
        imagem_b64 = capturar_base64(max_w=max_w)
        payload = {
            "model": config.OLLAMA_MODEL_VISION,
            "messages": [{
                "role": "user",
                "content": pergunta,
                "images": [imagem_b64],
            }],
            "stream": False,
            "keep_alive": "30m",
        }
        try:
            resp = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=12,
            )
        except requests.exceptions.Timeout:
            last_error = "timeout"
            continue
        except Exception as e:
            last_error = f"erro: {e}"
            continue

        if resp.status_code != 200:
            last_error = f"erro {resp.status_code}"
            continue

        content = (resp.json().get("message", {}).get("content", "") or "").strip()
        if content:
            return content
        last_error = "resposta vazia"

    return (
        "Nao consegui analisar a tela agora "
        f"({last_error}). Tente novamente em alguns segundos."
    )


def _groq_retry_after_seconds(resp):
    try:
        msg = (resp.json().get("error", {}) or {}).get("message", "")
        if "try again in" in msg:
            return float(msg.split("try again in ")[1].split("s")[0]) + 0.5
    except Exception:
        pass
    return 4.0


def descrever_tela(pergunta="O que está na tela? Descreva detalhadamente em português."):
    try:
        provider = str(getattr(config, "PROVIDER", "groq")).lower().strip()

        if provider == "ollama":
            return _descrever_tela_ollama(pergunta)

        if provider == "groq":
            imagem_b64 = capturar_base64(max_w=1024)
            headers = {
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{imagem_b64}"},
                        },
                        {"type": "text", "text": pergunta},
                    ],
                }],
                "max_tokens": 512,
                "temperature": 0.3,
            }

            for tentativa in range(4):
                try:
                    resp = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=20,
                    )
                except Exception:
                    if tentativa < 3:
                        time.sleep(min(2 ** tentativa, 6))
                        continue
                    # Fallback para Ollama quando a nuvem falhar
                    return _descrever_tela_ollama(pergunta)

                if resp.status_code == 200:
                    return (resp.json()["choices"][0]["message"]["content"] or "").strip()

                if resp.status_code == 429:
                    wait_s = min(_groq_retry_after_seconds(resp), 20.0)
                    time.sleep(wait_s)
                    continue

                if resp.status_code >= 500 and tentativa < 3:
                    time.sleep(min(2 ** tentativa, 6))
                    continue

                # Erro não recuperável do Groq: tenta fallback local.
                return _descrever_tela_ollama(pergunta)

            # Excedeu retries do Groq: fallback local.
            return _descrever_tela_ollama(pergunta)

        # openrouter
        imagem_b64 = capturar_base64(max_w=960)
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.MODEL_VISION,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{imagem_b64}"},
                    },
                    {"type": "text", "text": pergunta},
                ],
            }],
        }
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
        return f"Nao consegui analisar a tela agora (erro {resp.status_code})."
    except Exception:
        return "Nao consegui analisar a tela agora. Tente novamente ou descreva o que precisa fazer."
