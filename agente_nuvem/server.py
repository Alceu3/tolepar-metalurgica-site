"""
ARIA Web Server — FastAPI
Permite usar ARIA pelo celular ou de qualquer lugar via navegador.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Header, Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel
import uvicorn, json, asyncio
from datetime import datetime
import html

import brain, memory, config
import whatsapp, telegram_bot

app = FastAPI(title="ARIA", docs_url=None, redoc_url=None)

# Serve o chat web
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
os.makedirs(WEB_DIR, exist_ok=True)
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "resultados")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Modelos ────────────────────────────────────────────────

class MsgIn(BaseModel):
    texto: str

class MsgOut(BaseModel):
    resposta: str
    ts: str


class PedidoIn(BaseModel):
    cliente: str
    servico: str
    detalhes: str = ""
    contato: str = ""


class PedidoStatusIn(BaseModel):
    status: str
    pasta_local: str = ""
    resumo_entrega: str = ""


class WhatsAppSendIn(BaseModel):
    to: str
    texto: str


def _check_token(x_api_token: str | None):
    expected = str(getattr(config, "CLOUD_API_TOKEN", "") or "").strip()
    if expected and x_api_token != expected:
        raise HTTPException(status_code=401, detail="Token inválido")


def _check_whatsapp_webhook_key(webhook_key: str | None):
    expected = str(getattr(config, "WHATSAPP_WEBHOOK_KEY", "") or "").strip()
    if expected and webhook_key != expected:
        raise HTTPException(status_code=401, detail="Webhook key inválida")

# ── Conexões WebSocket ativas ──────────────────────────────
_conexoes: list[WebSocket] = []

# ── Rotas ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve o chat web."""
    html_path = os.path.join(WEB_DIR, "chat.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("<h2>ARIA Web — chat.html não encontrado</h2>", status_code=404)

@app.post("/chat", response_model=MsgOut)
async def chat(msg: MsgIn):
    """Processa mensagem e retorna resposta da ARIA."""
    texto = msg.texto.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    loop = asyncio.get_event_loop()
    resposta = await loop.run_in_executor(None, brain.processar, texto)
    # Intercepta tokens especiais de mic (não faz sentido no web)
    if resposta in ("__TOGGLE_MIC_ON__", "__TOGGLE_MIC_OFF__"):
        resposta = "Microfone só funciona no widget do PC."
    ts = datetime.now().strftime("%H:%M")
    return MsgOut(resposta=resposta, ts=ts)

@app.get("/historico")
async def historico(max: int = 30):
    """Retorna histórico de mensagens."""
    hist = memory.get_history(max_messages=max)
    return {"mensagens": hist}

@app.get("/projetos")
async def projetos():
    """Lista projetos/tarefas."""
    tarefas = memory._load(memory.TASKS_FILE)
    clientes = memory._load(memory.CLIENTS_FILE)
    return {"tarefas": tarefas, "clientes": clientes}


@app.post("/api/pedidos")
async def criar_pedido(payload: PedidoIn, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    pedido = memory.criar_pedido(
        cliente=payload.cliente.strip(),
        servico=payload.servico.strip(),
        detalhes=payload.detalhes.strip(),
        contato=payload.contato.strip(),
        origem="nuvem",
    )
    return {"ok": True, "pedido": pedido}


@app.get("/api/pedidos")
async def listar_pedidos(status: str | None = None, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    return {"pedidos": memory.listar_pedidos(status=status)}


@app.get("/api/pedidos/{pedido_id}")
async def obter_pedido(pedido_id: str, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    pedido = memory.obter_pedido(pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return {"pedido": pedido}


@app.patch("/api/pedidos/{pedido_id}/status")
async def atualizar_status(pedido_id: str, payload: PedidoStatusIn, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    pedido = memory.atualizar_pedido_status(
        pedido_id,
        payload.status,
        pasta_local=payload.pasta_local,
        resumo_entrega=payload.resumo_entrega,
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return {"ok": True, "pedido": pedido}


@app.post("/api/pedidos/{pedido_id}/resultado")
async def upload_resultado(
    pedido_id: str,
    arquivo: UploadFile = File(...),
    x_api_token: str | None = Header(default=None),
):
    _check_token(x_api_token)
    pedido = memory.obter_pedido(pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    safe_name = os.path.basename(arquivo.filename or "resultado.bin")
    out_name = f"{pedido_id}__{safe_name}"
    out_path = os.path.join(RESULTS_DIR, out_name)
    content = await arquivo.read()
    with open(out_path, "wb") as f:
        f.write(content)

    pedido = memory.atualizar_pedido_status(
        pedido_id,
        "resultado_recebido_nuvem",
        resultado_arquivo=out_name,
    )
    return {"ok": True, "arquivo": out_name, "pedido": pedido}


@app.get("/api/pedidos/{pedido_id}/resultado")
async def baixar_resultado(pedido_id: str, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    pedido = memory.obter_pedido(pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    nome = str(pedido.get("resultado_arquivo", "") or "")
    if not nome:
        raise HTTPException(status_code=404, detail="Pedido sem resultado")
    caminho = os.path.join(RESULTS_DIR, os.path.basename(nome))
    if not os.path.exists(caminho):
        raise HTTPException(status_code=404, detail="Arquivo de resultado não encontrado")
    return FileResponse(caminho)


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, key: str | None = None):
    """Webhook Twilio WhatsApp: recebe mensagem do cliente e responde com ARIA."""
    if not getattr(config, "WHATSAPP_ENABLED", True):
        return Response(content="<Response></Response>", media_type="application/xml")

    _check_whatsapp_webhook_key(key)

    form = await request.form()
    from_number = str(form.get("From", "")).strip()
    body = str(form.get("Body", "")).strip()

    if not body:
        twiml = "<Response><Message>Recebi sua mensagem vazia. Pode enviar novamente?</Message></Response>"
        return Response(content=twiml, media_type="application/xml")

    loop = asyncio.get_event_loop()
    resposta = await loop.run_in_executor(None, brain.processar, body)
    if resposta in ("__TOGGLE_MIC_ON__", "__TOGGLE_MIC_OFF__"):
        resposta = "No WhatsApp eu não ligo microfone, mas posso te atender por texto normalmente."

    memory.add_to_history("user", f"[whatsapp:{from_number}] {body}")
    memory.add_to_history("assistant", resposta)

    # Notifica Alceu se for o primeiro contato (pedido novo detectado)
    owner = str(getattr(config, "OWNER_WHATSAPP", "") or "").strip()
    if owner and owner != from_number:
        aviso = f"Novo contato no WhatsApp!\nDe: {from_number}\nMensagem: {body[:200]}"
        asyncio.get_event_loop().run_in_executor(None, whatsapp.enviar_whatsapp, owner, aviso)

    safe = html.escape(resposta, quote=False)
    twiml = f"<Response><Message>{safe}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")


@app.post("/api/whatsapp/send")
async def whatsapp_send(payload: WhatsAppSendIn, x_api_token: str | None = Header(default=None)):
    """Envia mensagem ativa para cliente no WhatsApp usando Twilio."""
    _check_token(x_api_token)
    to = payload.to.strip()
    texto = payload.texto.strip()
    if not to or not texto:
        raise HTTPException(status_code=400, detail="to/texto obrigatórios")
    result = whatsapp.enviar_whatsapp(to, texto)
    ok = not result.lower().startswith("erro")
    return {"ok": ok, "resultado": result}

@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    """WebSocket para chat em tempo real (resposta streaming)."""
    await ws.accept()
    _conexoes.append(ws)
    nome = str(getattr(config, "USER_NAME", "Alceu") or "Alceu")
    await ws.send_json({"tipo": "sistema", "texto": f"Olá, {nome}! Estou pronta. Pode falar.", "ts": datetime.now().strftime("%H:%M")})
    try:
        while True:
            data = await ws.receive_text()
            try:
                payload = json.loads(data)
                texto = payload.get("texto", "").strip()
            except Exception:
                texto = data.strip()
            if not texto:
                continue
            # Envia confirmação de recebimento
            await ws.send_json({"tipo": "voce", "texto": texto, "ts": datetime.now().strftime("%H:%M")})
            # Processa em thread separada para não bloquear
            loop = asyncio.get_event_loop()
            resposta = await loop.run_in_executor(None, brain.processar, texto)
            if resposta in ("__TOGGLE_MIC_ON__", "__TOGGLE_MIC_OFF__"):
                resposta = "Microfone só funciona no widget do PC."
            await ws.send_json({"tipo": "aria", "texto": resposta, "ts": datetime.now().strftime("%H:%M")})
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _conexoes:
            _conexoes.remove(ws)

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Webhook Telegram: recebe mensagens e responde com ARIA."""
    try:
        data = await request.json()
    except Exception:
        return {"ok": True}

    message = data.get("message") or data.get("edited_message") or {}
    chat_id = str((message.get("chat") or {}).get("id", "")).strip()
    texto = str(message.get("text") or "").strip()
    from_user = (message.get("from") or {}).get("first_name", "Cliente")

    if not chat_id or not texto:
        return {"ok": True}

    loop = asyncio.get_event_loop()
    resposta = await loop.run_in_executor(None, brain.processar, texto)
    if resposta in ("__TOGGLE_MIC_ON__", "__TOGGLE_MIC_OFF__"):
        resposta = "No Telegram eu não ligo microfone, mas posso te atender por texto."

    memory.add_to_history("user", f"[telegram:{chat_id}:{from_user}] {texto}")
    memory.add_to_history("assistant", resposta)

    # Responde ao cliente no Telegram
    await loop.run_in_executor(None, telegram_bot.enviar, chat_id, resposta)

    # Notifica Alceu se não for ele mesmo escrevendo
    owner_id = str(getattr(config, "TELEGRAM_OWNER_CHAT_ID", "") or "").strip()
    if owner_id and chat_id != owner_id:
        aviso = f"📩 Novo contato no Telegram!\nDe: {from_user} (id:{chat_id})\nMensagem: {texto[:200]}"
        await loop.run_in_executor(None, telegram_bot.notificar_dono, aviso)

    return {"ok": True}


@app.post("/api/telegram/send")
async def telegram_send_api(payload: WhatsAppSendIn, x_api_token: str | None = Header(default=None)):
    """Envia mensagem ativa para qualquer chat Telegram."""
    _check_token(x_api_token)
    resultado = telegram_bot.enviar(payload.to.strip(), payload.texto.strip())
    return {"ok": not resultado.lower().startswith("erro"), "resultado": resultado}


@app.post("/api/telegram/register-webhook")
async def telegram_register(x_api_token: str | None = Header(default=None)):
    """Registra o webhook do bot Telegram com a URL pública desta instância."""
    _check_token(x_api_token)
    url_publica = str(getattr(config, "CLOUD_API_URL", "") or "").strip()
    if not url_publica:
        raise HTTPException(status_code=400, detail="CLOUD_API_URL não configurado")
    result = telegram_bot.registrar_webhook(url_publica)
    return result


@app.get("/api/telegram/info")
async def telegram_info(x_api_token: str | None = Header(default=None)):
    """Retorna informações do bot Telegram (nome, username)."""
    _check_token(x_api_token)
    return telegram_bot.get_me()


# ── Main ───────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n✅  ARIA Web rodando em http://localhost:{port}")
    print(f"   Abra no celular: http://SEU-IP:{port}\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
