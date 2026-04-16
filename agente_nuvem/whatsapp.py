import requests

import config


def enviar_whatsapp(to_number: str, texto: str) -> str:
    """Envia mensagem WhatsApp via Twilio API."""
    sid = str(getattr(config, "TWILIO_ACCOUNT_SID", "") or "").strip()
    token = str(getattr(config, "TWILIO_AUTH_TOKEN", "") or "").strip()
    from_number = str(getattr(config, "TWILIO_WHATSAPP_FROM", "") or "").strip()

    if not sid or not token:
        return "Erro: TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN não configurados."

    if not to_number.lower().startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"

    if not from_number:
        from_number = "whatsapp:+14155238886"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = {
        "From": from_number,
        "To": to_number,
        "Body": texto,
    }

    try:
        resp = requests.post(url, data=data, auth=(sid, token), timeout=30)
        if resp.status_code >= 400:
            return f"Erro Twilio ({resp.status_code}): {resp.text[:300]}"
        return "Mensagem enviada no WhatsApp com sucesso."
    except Exception as ex:
        return f"Erro ao enviar WhatsApp: {ex}"
