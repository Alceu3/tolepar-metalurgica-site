import json
import vision
import hands
import memory

_DANGEROUS_TOOL_NAMES = {"pressionar_tecla", "atalho", "digitar"}
_DANGEROUS_TEXT_MARKERS = (
    "enviar",
    "submit",
    "confirmar",
    "confirm",
    "pagar",
    "payment",
    "comprar",
    "buy",
    "finalizar",
)

# ── Definições (formato OpenAI function-calling) ──────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ver_tela",
            "description": "Tira um screenshot e analisa o que está na tela. Use ANTES de clicar em qualquer coisa para entender o estado atual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pergunta": {
                        "type": "string",
                        "description": "O que quer saber sobre a tela? Ex: 'Quais campos tem no formulário?' ou 'Qual é o botão de enviar?'",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clicar",
            "description": "Clica em uma coordenada (x, y) na tela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Coordenada X"},
                    "y": {"type": "integer", "description": "Coordenada Y"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clicar_duplo",
            "description": "Duplo clique em uma coordenada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "digitar",
            "description": "Digita (cola) texto no campo ativo. Funciona com acentos e caracteres especiais.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a digitar"},
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pressionar_tecla",
            "description": "Pressiona uma tecla. Ex: 'enter', 'tab', 'escape', 'backspace', 'f5'",
            "parameters": {
                "type": "object",
                "properties": {
                    "tecla": {"type": "string", "description": "Nome da tecla"},
                },
                "required": ["tecla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "atalho",
            "description": "Executa atalho de teclado. Ex: 'ctrl+c', 'ctrl+v', 'ctrl+t', 'alt+tab', 'ctrl+shift+t'",
            "parameters": {
                "type": "object",
                "properties": {
                    "teclas": {"type": "string", "description": "Teclas separadas por +"},
                },
                "required": ["teclas"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Rola a página. Positivo = cima, Negativo = baixo. Ex: 3 ou -5",
            "parameters": {
                "type": "object",
                "properties": {
                    "quantidade": {"type": "integer"},
                },
                "required": ["quantidade"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_site",
            "description": "Abre um site no navegador padrão.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa ou domínio"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_cliente",
            "description": "Salva ou atualiza informações de um cliente na memória local.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome":     {"type": "string", "description": "Nome do cliente"},
                    "contato":  {"type": "string", "description": "Email, WhatsApp ou telefone"},
                    "projeto":  {"type": "string", "description": "Projeto ou serviço contratado"},
                    "notas":    {"type": "string", "description": "Anotações importantes"},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_clientes",
            "description": "Lista todos os clientes salvos na memória.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_tarefa",
            "description": "Salva ou atualiza uma tarefa ou projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo":    {"type": "string"},
                    "cliente":   {"type": "string"},
                    "descricao": {"type": "string"},
                    "status":    {
                        "type": "string",
                        "enum": ["pendente", "em_andamento", "concluido", "cancelado"],
                    },
                    "prioridade": {
                        "type": "string",
                        "enum": ["baixa", "media", "alta", "urgente"],
                    },
                },
                "required": ["titulo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_tarefas",
            "description": "Lista tarefas salvas, com filtro opcional por status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "pendente | em_andamento | concluido | cancelado",
                    }
                },
                "required": [],
            },
        },
    },
    # ── Arquivos e sistema ────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "listar_arquivos",
            "description": "Lista arquivos e pastas de um diretório. Use '.' para o diretório atual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho da pasta, ex: C:\\Users\\ACER\\Desktop"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": "Lê o conteúdo de um arquivo de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho completo do arquivo"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escrever_arquivo",
            "description": "Cria ou sobrescreve um arquivo com o conteúdo informado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                    "conteudo": {"type": "string"},
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deletar_arquivo",
            "description": "Deleta um arquivo ou pasta vazia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_arquivo",
            "description": "Abre um arquivo ou pasta com o programa padrão do sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executar_comando",
            "description": "Executa um comando no sistema operacional (PowerShell/cmd). Use com cautela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando a executar"},
                },
                "required": ["comando"],
            },
        },
    },
]


def is_dangerous_tool(nome: str, argumentos) -> bool:
    if nome not in _DANGEROUS_TOOL_NAMES:
        return False
    args = argumentos if isinstance(argumentos, dict) else json.loads(argumentos)
    text = " ".join(str(v).lower() for v in args.values())
    return any(marker in text for marker in _DANGEROUS_TEXT_MARKERS)


# ── Executor ──────────────────────────────────────────────

def executar(nome: str, argumentos):
    args = argumentos if isinstance(argumentos, dict) else json.loads(argumentos)

    dispatch = {
        "ver_tela":        lambda: vision.descrever_tela(
                               args.get("pergunta",
                                        "O que está na tela? Descreva em detalhes em português.")),
        "clicar":          lambda: hands.clicar(args["x"], args["y"]),
        "clicar_duplo":    lambda: hands.clicar_duplo(args["x"], args["y"]),
        "digitar":         lambda: hands.digitar(args["texto"]),
        "pressionar_tecla": lambda: hands.pressionar_tecla(args["tecla"]),
        "atalho":          lambda: hands.atalho(args["teclas"]),
        "scroll":          lambda: hands.scroll(args["quantidade"]),
        "abrir_site":      lambda: hands.abrir_site(args["url"]),
        "salvar_cliente":  lambda: memory.salvar_cliente(
                               args["nome"],
                               args.get("contato", ""),
                               args.get("projeto", ""),
                               args.get("notas", "")),
        "listar_clientes": lambda: memory.listar_clientes(),
        "salvar_tarefa":   lambda: memory.salvar_tarefa(
                               args["titulo"],
                               args.get("cliente", ""),
                               args.get("descricao", ""),
                               args.get("status", "pendente"),
                               args.get("prioridade", "media")),
        "listar_tarefas":  lambda: memory.listar_tarefas(args.get("status")),
        # ── Arquivo e sistema ─────────────────────────────
        "listar_arquivos": lambda: _listar_arquivos(args["caminho"]),
        "ler_arquivo":     lambda: _ler_arquivo(args["caminho"]),
        "escrever_arquivo": lambda: _escrever_arquivo(args["caminho"], args["conteudo"]),
        "deletar_arquivo": lambda: _deletar_arquivo(args["caminho"]),
        "abrir_arquivo":   lambda: _abrir_arquivo(args["caminho"]),
        "executar_comando": lambda: _executar_comando(args["comando"]),
    }

    fn = dispatch.get(nome)
    if fn:
        return fn()
    return f"Ferramenta '{nome}' não encontrada."


# ── Implementações de arquivo / sistema ───────────────────

import os as _os
import subprocess as _subprocess

def _listar_arquivos(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        itens = _os.listdir(path)
        linhas = []
        for item in sorted(itens):
            full = _os.path.join(path, item)
            tipo = "[pasta]" if _os.path.isdir(full) else "[arquivo]"
            linhas.append(f"{tipo} {item}")
        return "\n".join(linhas) if linhas else "Pasta vazia."
    except Exception as e:
        return f"Erro ao listar: {e}"

def _ler_arquivo(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            conteudo = f.read(8000)
        return conteudo if conteudo else "(arquivo vazio)"
    except Exception as e:
        return f"Erro ao ler arquivo: {e}"

def _escrever_arquivo(caminho: str, conteudo: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return f"Arquivo salvo: {path}"
    except Exception as e:
        return f"Erro ao escrever arquivo: {e}"

def _deletar_arquivo(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        if _os.path.isdir(path):
            _os.rmdir(path)
        else:
            _os.remove(path)
        return f"Deletado: {path}"
    except Exception as e:
        return f"Erro ao deletar: {e}"

def _abrir_arquivo(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        _os.startfile(path)
        return f"Abrindo: {path}"
    except Exception as e:
        return f"Erro ao abrir: {e}"

def _executar_comando(comando: str) -> str:
    try:
        result = _subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        saida = (result.stdout or "") + (result.stderr or "")
        return saida[:2000] if saida.strip() else "(sem saída)"
    except Exception as e:
        return f"Erro ao executar: {e}"
