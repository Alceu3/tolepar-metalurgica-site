"""
ARIA Web Server — FastAPI
Permite usar ARIA pelo celular ou de qualquer lugar via navegador.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Header
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn, json, asyncio
from datetime import datetime

import brain, memory, config, hearing

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


def _check_token(x_api_token: str | None):
    expected = str(getattr(config, "CLOUD_API_TOKEN", "") or "").strip()
    if expected and x_api_token != expected:
        raise HTTPException(status_code=401, detail="Token inválido")

# ── Conexões WebSocket ativas ──────────────────────────────
_conexoes: list[WebSocket] = []

# ── Rotas ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve o chat web."""
    html_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("<h2>ARIA Web — index.html não encontrado</h2>", status_code=404)

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

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcreve áudio para texto via Whisper."""
    try:
        audio_data = await audio.read()
        if not audio_data:
            return {"error": "Arquivo vazio"}
        
        loop = asyncio.get_event_loop()
        filename = str(audio.filename or "audio.webm")
        content_type = str(audio.content_type or "audio/webm")
        texto = await loop.run_in_executor(
            None,
            hearing.transcrever_arquivo_whisper,
            audio_data,
            filename,
            content_type,
        )
        
        if not texto:
            return {"error": "Não entendi o áudio. Tente novamente."}
        
        return {"texto": texto}
    except Exception as e:
        return {"error": str(e)}

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

# ── Main ───────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n[OK] ARIA Web rodando em http://localhost:{port}")
    print(f"   Abra no celular: http://SEU-IP:{port}\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
