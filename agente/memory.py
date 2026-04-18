import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

CLIENTS_FILE = os.path.join(DATA_DIR, "clients.json")
TASKS_FILE   = os.path.join(DATA_DIR, "tasks.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
ORDERS_FILE  = os.path.join(DATA_DIR, "orders.json")
FILES_LOG    = os.path.join(DATA_DIR, "files_log.json")


def _load(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except (json.JSONDecodeError, Exception):
            # Arquivo corrompido — faz backup e começa do zero
            try:
                import shutil
                shutil.copy(path, path + ".bak")
            except Exception:
                pass
            return []
    return []


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Clientes ──────────────────────────────────────────────

def salvar_cliente(nome, contato="", projeto="", notas=""):
    clients = _load(CLIENTS_FILE)
    existing = next((c for c in clients if c["nome"].lower() == nome.lower()), None)
    if existing:
        existing["contato"]    = contato  or existing.get("contato", "")
        existing["projeto"]    = projeto  or existing.get("projeto", "")
        existing["notas"]      = notas    or existing.get("notas", "")
        existing["atualizado"] = datetime.now().isoformat()
    else:
        clients.append({
            "id":       len(clients) + 1,
            "nome":     nome,
            "contato":  contato,
            "projeto":  projeto,
            "notas":    notas,
            "criado":   datetime.now().isoformat(),
        })
    _save(CLIENTS_FILE, clients)
    return f"Cliente '{nome}' salvo com sucesso."


def listar_clientes():
    clients = _load(CLIENTS_FILE)
    if not clients:
        return "Nenhum cliente cadastrado ainda."
    return json.dumps(clients, ensure_ascii=False, indent=2)


# ── Tarefas / Projetos ────────────────────────────────────

def salvar_tarefa(titulo, cliente="", descricao="", status="pendente", prioridade="media"):
    tasks = _load(TASKS_FILE)
    existing = next((t for t in tasks if t["titulo"].lower() == titulo.lower()), None)
    if existing:
        existing["status"]     = status
        existing["descricao"]  = descricao  or existing.get("descricao", "")
        existing["atualizado"] = datetime.now().isoformat()
    else:
        tasks.append({
            "id":        len(tasks) + 1,
            "titulo":    titulo,
            "cliente":   cliente,
            "descricao": descricao,
            "status":    status,
            "prioridade": prioridade,
            "criado":    datetime.now().isoformat(),
        })
    _save(TASKS_FILE, tasks)
    return f"Tarefa '{titulo}' salva — status: {status}."


def listar_tarefas(status=None):
    tasks = _load(TASKS_FILE)
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if not tasks:
        return "Nenhuma tarefa encontrada."
    return json.dumps(tasks, ensure_ascii=False, indent=2)


# ── Histórico de conversa ─────────────────────────────────

def add_to_history(role, content):
    history = _load(HISTORY_FILE)
    history.append({"role": role, "content": content, "ts": datetime.now().isoformat()})
    if len(history) > 60:
        history = history[-60:]
    _save(HISTORY_FILE, history)


def get_history(max_messages=20):
    history = _load(HISTORY_FILE)
    return [{"role": h["role"], "content": h["content"]} for h in history[-max_messages:]]


def clear_history():
    _save(HISTORY_FILE, [])
    return "Histórico limpo."


# ── Fluxo Nuvem <-> Local (pedidos) ──────────────────────

def criar_pedido(cliente, servico, detalhes="", contato="", origem="nuvem"):
    orders = _load(ORDERS_FILE)
    now = datetime.now().isoformat()
    pid = f"PED-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(orders) + 1:03d}"
    pedido = {
        "id": pid,
        "cliente": cliente,
        "servico": servico,
        "detalhes": detalhes,
        "contato": contato,
        "origem": origem,
        "status": "novo",
        "pasta_local": "",
        "resultado_arquivo": "",
        "resumo_entrega": "",
        "criado": now,
        "atualizado": now,
    }
    orders.append(pedido)
    _save(ORDERS_FILE, orders)
    return pedido


def listar_pedidos(status=None):
    orders = _load(ORDERS_FILE)
    if status:
        orders = [o for o in orders if str(o.get("status", "")).lower() == str(status).lower()]
    return orders


def obter_pedido(pedido_id):
    orders = _load(ORDERS_FILE)
    return next((o for o in orders if o.get("id") == pedido_id), None)


def atualizar_pedido_status(pedido_id, status, **updates):
    orders = _load(ORDERS_FILE)
    pedido = next((o for o in orders if o.get("id") == pedido_id), None)
    if not pedido:
        return None
    pedido["status"] = status
    for k, v in updates.items():
        pedido[k] = v
    pedido["atualizado"] = datetime.now().isoformat()
    _save(ORDERS_FILE, orders)
    return pedido


# ── Log de arquivos e pastas criados ──────────────────────

def registrar_arquivo(caminho: str, tipo: str = "arquivo", descricao: str = ""):
    """Registra um arquivo/pasta criado para que Evelyn nunca esqueça onde está."""
    entries = _load(FILES_LOG)
    nome = os.path.basename(caminho)
    # Atualiza se já existe com mesmo caminho
    existing = next((e for e in entries if e["caminho"].lower() == caminho.lower()), None)
    if existing:
        existing["descricao"] = descricao or existing.get("descricao", "")
        existing["atualizado"] = datetime.now().isoformat()
    else:
        entries.append({
            "id":        len(entries) + 1,
            "nome":      nome,
            "caminho":   caminho,
            "tipo":      tipo,
            "descricao": descricao,
            "criado":    datetime.now().isoformat(),
        })
    _save(FILES_LOG, entries)


def buscar_arquivo(nome_ou_trecho: str) -> list:
    """Busca no log pelo nome do arquivo/pasta (parcial, case-insensitive)."""
    entries = _load(FILES_LOG)
    termo = nome_ou_trecho.lower()
    return [e for e in entries if termo in e["nome"].lower() or termo in e["caminho"].lower() or termo in e.get("descricao", "").lower()]


def listar_arquivos_criados() -> str:
    entries = _load(FILES_LOG)
    if not entries:
        return "Nenhum arquivo registrado ainda."
    linhas = []
    for e in reversed(entries[-30:]):  # mostra os 30 mais recentes
        tipo = e.get("tipo", "arquivo")
        linhas.append(f"[{tipo}] {e['nome']} → {e['caminho']} ({e['criado'][:10]})")
    return "\n".join(linhas)

