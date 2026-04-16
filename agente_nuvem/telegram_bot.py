"""
Integração Telegram Bot — ARIA Nuvem
Envia mensagens e processa mensagens recebidas via webhook.
"""
import requests as _req
import config

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    t = str(getattr(config, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    if not t:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado no .env")
    return t


def enviar(chat_id: str | int, texto: str) -> str:
    """Envia mensagem de texto para um chat/usuário Telegram."""
    try:
        url = _BASE.format(token=_token(), method="sendMessage")
        r = _req.post(url, json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}, timeout=20)
        if r.status_code == 200:
            return "Mensagem enviada no Telegram."
        return f"Erro Telegram ({r.status_code}): {r.text[:300]}"
    except Exception as ex:
        return f"Erro Telegram: {ex}"


def notificar_dono(texto: str) -> str:
    """Notifica o dono (Alceu) sobre pedido novo ou evento importante."""
    chat_id = str(getattr(config, "TELEGRAM_OWNER_CHAT_ID", "") or "").strip()
    if not chat_id:
        return "TELEGRAM_OWNER_CHAT_ID não configurado ainda."
    return enviar(chat_id, texto)


def registrar_webhook(url_publica: str) -> dict:
    """Registra webhook no Telegram para receber mensagens em tempo real."""
    try:
        endpoint = f"{url_publica.rstrip('/')}/telegram/webhook"
        r = _req.post(
            _BASE.format(token=_token(), method="setWebhook"),
            json={"url": endpoint, "allowed_updates": ["message"]},
            timeout=20,
        )
        return r.json()
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def get_me() -> dict:
    """Retorna informações do bot (nome, username)."""
    try:
        r = _req.get(_BASE.format(token=_token(), method="getMe"), timeout=10)
        return r.json()
    except Exception as ex:
        return {"ok": False, "error": str(ex)}
