import json
from datetime import datetime
import os
import re
import unicodedata
import requests
import config
import memory
import tools

SYSTEM_PROMPT = f"""Você é {config.AGENT_NAME}, um assistente de IA pessoal do {config.USER_NAME}.

Você é inteligente, direta, prestativa e conversacional — como o ChatGPT, mas focada em trabalhar ao lado do usuário no computador.

CAPACIDADES:
- Ver a tela em tempo real
- Controlar mouse e teclado
- Abrir sites e programas
- Salvar clientes, tarefas e projetos na memória
- Responder qualquer pergunta com conhecimento amplo
- Executar automações no computador

COMO RESPONDER:
- Responda de forma natural, clara e direta — sem ser robótica
- Use linguagem informal e amigável em português brasileiro
- Para perguntas simples: resposta curta e objetiva
- Para perguntas complexas: explique bem, com exemplos se necessário
- Nunca termine com "Como posso ajudar?" ou frases genéricas repetitivas
- Varie o estilo das respostas — não repita a mesma estrutura toda vez
- Se não souber algo, diga claramente em vez de inventar

AÇÕES NO COMPUTADOR:
- Use ver_tela quando precisar ver o que está na tela
- Confirme ações irreversíveis antes de executar (envios, pagamentos, exclusões)
- Explique o que vai fazer antes de fazer

Fale sempre em português brasileiro."""

_TOOL_NAMES = {
    t.get("function", {}).get("name")
    for t in getattr(tools, "TOOL_DEFINITIONS", [])
    if t.get("function", {}).get("name")
}

_GREETING_PHRASES = {
    "oi",
    "ola",
    "opa",
    "e ai",
    "eae",
    "hey",
    "hello",
    "bom dia",
    "boa tarde",
    "boa noite",
}

_SMALL_TALK_RESPONSES = {
    "tudo": "Perfeito. Estou aqui e pronta para te ajudar no que voce precisar.",
    "tudo bem": "Tudo certo por aqui. Quer que eu veja sua tela ou execute alguma tarefa?",
    "de boa": "Boa. Se quiser, posso te ajudar com a proxima tarefa agora.",
    "ok": "Certo. Me diga o proximo passo.",
    "blz": "Fechado. O que fazemos agora?",
    "beleza": "Beleza. Pode mandar a proxima acao.",
    "sim": "Perfeito. Me diga o que voce quer que eu faca.",
    "nao": "Ok, sem problema. Me avisa quando quiser continuar.",
    "obrigado": "De nada! Fico a disposicao.",
    "obrigada": "De nada! Fico a disposicao.",
    "valeu": "Disponha! Precisar e so falar.",
    "legal": "Otimo! Pode continuar.",
    "certo": "Perfeito. Pode prosseguir.",
    "entendi": "Certo. Me diga o que quer fazer agora.",
    "com que eu falo": "Voce esta falando com Evelyn, sua assistente de IA. Posso ver sua tela, clicar, digitar, abrir sites e responder perguntas.",
    "com quem falo": "Voce fala com Evelyn, uma IA assistente. Como posso te ajudar?",
    "com quem eu falo": "Voce fala com Evelyn, sua assistente de IA. Posso ver sua tela, clicar, digitar, abrir sites e responder perguntas.",
    "quem e voce": "Sou a Evelyn, sua assistente de IA. Posso ajudar com tarefas na tela, automacao e conversas.",
    "quem e vc": "Sou a Evelyn, sua assistente de IA. Posso ajudar com tarefas na tela, automacao e conversas.",
    "quem es voce": "Sou a Evelyn, sua assistente de IA. Posso ajudar com tarefas na tela, automacao e conversas.",
    "o que e isso": "Sou a Evelyn, uma assistente de IA integrada ao seu computador.",
    "ola tudo bem": "Tudo otimo! Em que posso te ajudar hoje?",
    "oi tudo bem": "Oi! Tudo certo por aqui. O que voce precisa?",
    "ta bom": "Fechado, Alceu. Pode mandar o proximo passo.",
    "ouvir": "Estou te ouvindo, Alceu. Pode falar que eu sigo com voce.",
    "ta me ouvindo": "Estou te ouvindo sim, Alceu. Pode falar que eu te acompanho.",
    "voce ta me ouvindo": "Sim, Alceu. Estou te ouvindo e pronta para ajudar.",
}

_FAST_CHAT_MARKERS = (
    "oi",
    "ola",
    "tudo bem",
    "como voce",
    "como vc",
    "bom dia",
    "boa tarde",
    "boa noite",
    "blz",
    "beleza",
    "com que eu falo",
    "com quem falo",
    "com quem eu falo",
    "quem e voce",
    "quem es voce",
    "obrigado",
    "obrigada",
    "valeu",
    "ta me ouvindo",
    "voce ta me ouvindo",
)

_USER_NAME = str(getattr(config, "USER_NAME", "") or "").strip()
_GREETING_CURSOR = 0
_READY_CURSOR = 0

_GREETING_VARIANTS = [
    "Oi, {name}! Boa te ver por aqui. Como posso te ajudar agora?",
    "Ola, {name}! Tudo certo por ai? Me diz no que eu te ajudo.",
    "Ei, {name}! Estou com voce. Qual e a proxima tarefa?",
    "Boa! {name}, pode mandar que eu te ajudo agora.",
]

_READY_VARIANTS = [
    "Perfeito, {name}. Quer conversar, ver a tela ou executar uma tarefa?",
    "Estou pronta, {name}. Me fala se quer chat, visao da tela ou automacao.",
    "Fechou, {name}. Posso te ouvir, analisar a tela ou executar uma acao.",
    "Tudo certo, {name}. Diz o que voce quer que eu faca agora.",
]

_PROGRESS_CALLBACK = None


def set_progress_callback(callback):
    """Registra callback de progresso para UI acompanhar execução ao vivo."""
    global _PROGRESS_CALLBACK
    _PROGRESS_CALLBACK = callback


def _emit_progress(event: str, **data):
    cb = _PROGRESS_CALLBACK
    if not cb:
        return
    try:
        cb(event, data)
    except Exception:
        pass


def _tool_label(nome: str) -> str:
    labels = {
        "ver_tela": "analisar tela",
        "clicar": "clicar",
        "clicar_duplo": "duplo clique",
        "digitar": "digitar",
        "pressionar_tecla": "pressionar tecla",
        "atalho": "usar atalho",
        "scroll": "rolar tela",
        "scroll_continuo": "rolagem contínua",
        "parar_scroll": "parar rolagem",
        "pesquisar_web": "pesquisar web",
        "pesquisar_tendencias": "pesquisar tendências",
        "montar_video": "montar vídeo",
        "abrir_editor_video": "abrir aplicativo",
        "preenchimento_generativo": "preenchimento generativo",
        "firefly_gerar_imagem": "gerar imagem",
        "firefly_preenchimento": "preenchimento Firefly",
        "firefly_texto_para_video": "gerar vídeo",
        "abrir_site": "abrir site",
        "salvar_cliente": "salvar cliente",
        "listar_clientes": "listar clientes",
        "salvar_tarefa": "salvar tarefa",
        "listar_tarefas": "listar tarefas",
        "listar_arquivos": "listar arquivos",
        "ler_arquivo": "ler arquivo",
        "escrever_arquivo": "escrever arquivo",
        "deletar_arquivo": "deletar arquivo",
        "abrir_arquivo": "abrir arquivo",
        "executar_comando": "executar comando",
    }
    return labels.get(nome, nome)


def _is_error_result(resultado) -> bool:
    txt = str(resultado or "").strip().lower()
    if not txt:
        return False
    if txt.startswith("erro") or txt.startswith("error"):
        return True
    markers = (" erro ", "invalid", "falha", "exception", "traceback")
    return any(m in f" {txt} " for m in markers)


def _is_retryable_error(resultado) -> bool:
    txt = str(resultado or "").strip().lower()
    retry_markers = (
        "timeout",
        "timed out",
        "429",
        "rate limit",
        "limite",
        "tempor",
        "connection",
        "conexao",
        "network",
        "indispon",
    )
    return any(m in txt for m in retry_markers)

_CAPABILITY_MARKERS = (
    "o que consegue fazer",
    "o que voce consegue fazer",
    "o que vc consegue fazer",
    "o que sabe fazer",
    "como pode ajudar",
)

_ACTION_MARKERS = (
    # navegação
    "abre ", "abrir ", "abre o ", "abrir o ",
    "clica ", "clicar ", "clica em", "clicar em",
    "vai para", "va para", "vamos para",
    "navega para", "navegue para",
    "acessa ", "acessar ",
    "entra no", "entre no", "entrar no",
    "seleciona ", "selecionar ",
    "arrasta", "arrastar",
    "clique em", "clique no", "clique na",
    # fechar / minimizar / maximizar
    "fecha ", "fechar ", "fecha o ", "fechar o ",
    "fecha a ", "fechar a ",
    "minimiza", "minimizar",
    "maximiza", "maximizar",
    "tela cheia",
    # digitar / escrever no computador
    "digita ", "digitar ",
    "escreve ", "escrever ",
    "rola ", "rolar ", "scroll",
    # ações genéricas no computador
    "executa", "executar",
    "pressiona", "pressionar",
    "atalho",
)
_NAVIGATION_MARKERS = _ACTION_MARKERS  # alias de compatibilidade

_SCREEN_REQUEST_MARKERS = (
    "ver minha tela",
    "ve minha tela",
    "vendo minha tela",
    "consegue ver minha tela",
    "o que esta na tela",
    "o que está na tela",
    "descreve a tela",
    "descreva a tela",
)


def _normalize_text(texto: str) -> str:
    txt = (texto or "").strip().lower()
    txt = "".join(
        ch for ch in unicodedata.normalize("NFD", txt)
        if unicodedata.category(ch) != "Mn"
    )
    txt = re.sub(r"[^a-z0-9\s]", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _is_simple_greeting(texto: str) -> bool:
    norm = _normalize_text(texto)
    if not norm or len(norm) > 30:
        return False
    return norm in _GREETING_PHRASES


def _fmt_name() -> str:
    return _USER_NAME or ""


def _next_variant(options: list[str], cursor_name: str) -> str:
    global _GREETING_CURSOR, _READY_CURSOR
    if not options:
        return ""
    if cursor_name == "greeting":
        idx = _GREETING_CURSOR % len(options)
        _GREETING_CURSOR += 1
    else:
        idx = _READY_CURSOR % len(options)
        _READY_CURSOR += 1
    return options[idx]


def _greeting_response() -> str:
    nome = _fmt_name() or ""
    template = _next_variant(_GREETING_VARIANTS, "greeting")
    return template.format(name=nome).replace("  ", " ").strip()


def _ready_response() -> str:
    nome = _fmt_name() or ""
    template = _next_variant(_READY_VARIANTS, "ready")
    return template.format(name=nome).replace("  ", " ").strip()


def _direct_local_action(texto: str) -> str | None:
    """Executa comandos locais simples sem depender de API externa."""
    norm = _normalize_text(texto)
    if not norm:
        return None

    compact = norm.replace(" ", "")
    pediu_abrir = any(v in norm for v in ("abre", "abra", "abrir", "abre a", "abra a"))
    pediu_pasta_trabalho = ("pasta de trabalho" in norm) or ("pastadetrabalho" in compact)
    pediu_pasta_generica = ("pasta" in norm)

    # Comandos de microfone — ligar/desligar sem API
    _MIC_LIGAR = {
        "ativa o microfone", "ativar microfone", "ativa microfone",
        "liga o microfone", "ligar microfone", "liga microfone",
        "ativa o mic", "liga o mic", "liga mic", "ativa mic",
        "ligar o mic", "ativar o mic",
        "microfone on", "mic on", "ligar voz", "ativar voz",
        "começa a ouvir", "comeca a ouvir", "comecar a ouvir",
    }
    _MIC_DESLIGAR = {
        "desativa o microfone", "desativar microfone", "desativa microfone",
        "desliga o microfone", "desligar microfone", "desliga microfone",
        "desativa o mic", "desliga o mic", "desliga mic", "desativa mic",
        "microfone off", "mic off", "desligar voz", "desativar voz",
        "para de ouvir", "para ouvir",
    }
    _VOICE_LIGAR = {
        "resposta em fala", "falar", "responder em voz", "responder em fala",
        "ativa a voz", "ativar a voz", "ativa voz", "ativar voz",
        "liga a voz", "ligar a voz", "liga voz", "ligar voz",
        "audio on", "som on",
    }
    _VOICE_DESLIGAR = {
        "resposta em texto", "somente texto", "só texto", "so texto",
        "desativa a voz", "desativar a voz", "desativa voz", "desativar voz",
        "desliga a voz", "desligar a voz", "desliga voz", "desligar voz",
        "audio off", "som off",
    }
    if norm in _MIC_LIGAR:
        return "__TOGGLE_MIC_ON__"
    if norm in _MIC_DESLIGAR:
        return "__TOGGLE_MIC_OFF__"
    if norm in _VOICE_LIGAR:
        return "__TOGGLE_VOICE_ON__"
    if norm in _VOICE_DESLIGAR:
        return "__TOGGLE_VOICE_OFF__"

    if pediu_abrir and (pediu_pasta_trabalho or pediu_pasta_generica):
        pasta_trabalho = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            resultado = tools.executar("abrir_arquivo", {"caminho": pasta_trabalho})
            resultado_txt = str(resultado)
            if resultado_txt.lower().startswith("erro"):
                return "Tentei abrir sua pasta de trabalho, mas deu erro. Vou tentar de novo se voce pedir."
            nome = _fmt_name()
            if nome:
                return f"Pronto, {nome}. Abri sua pasta de trabalho."
            return "Pronto. Abri sua pasta de trabalho."
        except Exception:
            return "Tentei abrir sua pasta de trabalho, mas deu erro. Vou tentar de novo se voce pedir."

    return None


def _direct_task_action(texto: str) -> str | None:
    """Cria tarefa localmente a partir de comandos diretos do usuario."""
    if not isinstance(texto, str):
        return None

    raw = texto.strip()
    norm = _normalize_text(raw)
    if not norm:
        return None

    gatilhos = (
        "cria tarefa",
        "criar tarefa",
        "crie tarefa",
        "adiciona tarefa",
        "adicionar tarefa",
        "nova tarefa",
        "salva tarefa",
        "salvar tarefa",
        "anota tarefa",
        "anotar tarefa",
    )
    if not any(g in norm for g in gatilhos):
        return None

    # Extrai o titulo removendo o prefixo de comando mais comum.
    titulo = re.sub(
        r"(?i)^\s*(cria(?:r)?|crie|adiciona(?:r)?|salva(?:r)?|anota(?:r)?|nova)\s+(?:uma\s+)?tarefa\s*[:\-]?\s*",
        "",
        raw,
    ).strip()

    # Campos opcionais em formato simples: "prioridade: alta, status: pendente, cliente: nome"
    prioridade = "media"
    status = "pendente"
    cliente = ""
    descricao = ""

    m_prio = re.search(r"(?i)\bprioridade\s*[:=]\s*(baixa|media|alta|urgente)\b", raw)
    if m_prio:
        prioridade = _normalize_text(m_prio.group(1)).replace(" ", "_")

    m_status = re.search(
        r"(?i)\bstatus\s*[:=]\s*(pendente|em\s+andamento|concluido|concluida|cancelado|cancelada)\b",
        raw,
    )
    if m_status:
        st = _normalize_text(m_status.group(1)).replace(" ", "_")
        status = {
            "concluida": "concluido",
            "cancelada": "cancelado",
        }.get(st, st)

    m_cliente = re.search(r"(?i)\bcliente\s*[:=]\s*([^,;]+)", raw)
    if m_cliente:
        cliente = m_cliente.group(1).strip()

    m_desc = re.search(r"(?i)\bdescricao\s*[:=]\s*(.+)$", raw)
    if m_desc:
        descricao = m_desc.group(1).strip()

    if not titulo:
        return "Me passe o titulo da tarefa. Exemplo: cria tarefa fechar contrato do cliente"

    try:
        resultado = memory.salvar_tarefa(
            titulo=titulo,
            cliente=cliente,
            descricao=descricao,
            status=status,
            prioridade=prioridade,
        )
        return str(resultado)
    except Exception:
        return "Tentei salvar a tarefa, mas houve um erro. Tente novamente."


def _is_direct_screen_request(texto: str) -> bool:
    norm = _normalize_text(texto)
    if not norm:
        return False
    return any(marker in norm for marker in _SCREEN_REQUEST_MARKERS)


def _capability_response(texto: str) -> str | None:
    norm = _normalize_text(texto)
    if not norm:
        return None
    if any(marker in norm for marker in _CAPABILITY_MARKERS):
        return (
            "Eu posso: ver sua tela, clicar e digitar, abrir sites, "
            "usar atalhos, salvar clientes e tarefas, ler/escrever arquivos, "
            "e conversar por voz ou texto."
        )
    return None


def _direct_telegram_action(texto: str) -> str | None:
    """Envia mensagem proativa no Telegram em comandos diretos do usuario."""
    if not isinstance(texto, str):
        return None

    raw = texto.strip()
    norm = _normalize_text(raw)
    if not norm:
        return None

    gatilhos = (
        "me chama no telegram",
        "me chama no telegran",
        "me chama no tg",
        "manda mensagem no telegram",
        "me manda no telegram",
        "envia no telegram",
        "chama no telegram",
        "chama no telegran",
    )
    if not any(g in norm for g in gatilhos):
        return None

    nome = _fmt_name() or ""
    msg = f"Oi{(', ' + nome) if nome else ''}! Te chamei no Telegram agora."

    try:
        resultado = str(tools.executar("enviar_telegram", {"mensagem": msg}))
    except Exception:
        return "Nao consegui enviar no Telegram agora. Tenta de novo em instantes."

    rnorm = _normalize_text(resultado)
    if "mensagem enviada" in rnorm:
        return "Pronto. Te chamei no Telegram."
    if "chat_id" in rnorm and "nao registrado" in rnorm:
        return "Ainda nao achei seu chat no Telegram. Manda /start no bot e me pede de novo."
    if "403" in rnorm or "forbidden" in rnorm:
        return "Nao consegui enviar no Telegram por bloqueio de permissao. Manda /start no bot e tente novamente."
    if "token" in rnorm and "nao configurado" in rnorm:
        return "O token do Telegram nao esta configurado no sistema."

    return f"Tentei enviar no Telegram, mas deu isso: {resultado}"


def _direct_video_download_action(texto: str) -> str | None:
    """Baixa video por link quando o usuario pede download explicitamente."""
    if not isinstance(texto, str):
        return None

    raw = texto.strip()
    norm = _normalize_text(raw)
    if not norm:
        return None

    gatilhos = (
        "baixar video",
        "baixa video",
        "abaixar video",
        "download de video",
        "baixar o video",
        "baixa o video",
        "download do video",
    )
    if not any(g in norm for g in gatilhos):
        return None

    m = re.search(r"(https?://[^\s]+)", raw, flags=re.IGNORECASE)
    if not m:
        return "Me envie o link completo do video (http/https) para eu baixar agora."

    url = m.group(1).strip().rstrip(").,;!?\"'")
    qualidade = ""
    apenas_audio = False

    m_q = re.search(r"\b(2160|1440|1080|720|480|360)\s*p?\b", norm)
    if m_q:
        qualidade = m_q.group(1)

    if any(x in norm for x in (
        "so audio", "somente audio", "apenas audio", "so musica", "somente musica", "mp3", "audio apenas"
    )):
        apenas_audio = True

    try:
        return str(tools.executar("baixar_video_link", {
            "url": url,
            "qualidade": qualidade,
            "apenas_audio": apenas_audio,
        }))
    except Exception as e:
        return f"Nao consegui baixar o video agora ({e}). Tente novamente em instantes."


def _direct_youtube_ops_action(texto: str) -> str | None:
    """Planeja operacao de canal no YouTube: pesquisa, modelagem e agenda."""
    if not isinstance(texto, str):
        return None

    raw = texto.strip()
    norm = _normalize_text(raw)
    if not norm:
        return None

    if "youtube" not in norm and "canal" not in norm:
        return None

    gatilhos = (
        "monetizado",
        "monetiza",
        "modela",
        "semelhante",
        "agenda",
        "postando",
        "postar",
        "cria os video",
        "criar os video",
        "cria video",
        "criar video",
    )
    if not any(g in norm for g in gatilhos):
        return None

    nicho = "geral"
    m_nicho = re.search(
        r"(?i)\b(?:de|sobre|nicho)\s+([a-z0-9\s]{3,60})$",
        raw,
    )
    if m_nicho and m_nicho.group(1).strip():
        nicho = m_nicho.group(1).strip(" .,!?:;\"'")

    videos_semana = 4
    m_freq = re.search(r"\b([1-7])\s*(?:videos|video)\s*(?:por\s+semana|semana)\b", norm)
    if m_freq:
        videos_semana = int(m_freq.group(1))

    referencia = ""
    m_ref = re.search(r"(?i)\bsemelhante\s+a\s+(.+)$", raw)
    if m_ref and m_ref.group(1).strip():
        referencia = m_ref.group(1).strip(" .,!?:;\"'")

    # Pedido explicito de automacao total com acompanhamento em planilha.
    pediu_automatico_total = any(x in norm for x in (
        "automatico",
        "automatica",
        "100",
        "planilha",
        "acompanha",
        "acompanhar",
        "agenda",
    ))

    if pediu_automatico_total:
        try:
            return str(tools.executar("youtube_inicializar_automacao_total", {
                "nicho": nicho,
                "videos_semana": videos_semana,
            }))
        except Exception as e:
            return f"Nao consegui iniciar a automacao total do YouTube agora ({e}). Tente novamente em instantes."

    try:
        return str(tools.executar("planejar_operacao_youtube", {
            "nicho": nicho,
            "referencia": referencia,
            "videos_semana": videos_semana,
        }))
    except Exception as e:
        return f"Nao consegui montar o plano do YouTube agora ({e}). Tente novamente em instantes."


def _direct_web_search_action(texto: str) -> str | None:
    """Executa busca web direta para pedidos simples de pesquisa."""
    if not isinstance(texto, str):
        return None

    raw = texto.strip()
    norm = _normalize_text(raw)
    if not norm:
        return None

    gatilhos = (
        "pesquisa",
        "pesquisar",
        "procura",
        "procurar",
        "busca",
        "buscar",
    )
    pedido_natural_video = ("quero ver" in norm) and ("video" in norm)
    pediu_youtube = ("youtube" in norm) or ("you tube" in norm)
    pedido_video = ("video" in norm) or ("videos" in norm)
    if not any(g in norm for g in gatilhos) and not pedido_natural_video:
        return None

    # Frases de reclamacao/instrucao sem tema claro: nao transforme isso em termo de busca.
    if (
        ("nao quero" in norm or "não quero" in texto.lower() or "nao apareceu" in norm or "nao abriu" in norm)
        and ("mensagem" in norm or "tela" in norm)
        and ("video" not in norm and "site" not in norm and "youtube" not in norm)
    ):
        return "Entendi. Eu nao vou responder com lista no chat. Me diga so o tema curto (ex: 'video de carro') que eu digito no navegador agora."

    query = ""
    padroes_query = (
        r"(?i).*\b(?:pesquisa(?:r)?|procura(?:r)?|busca(?:r)?)\b(?:\s+para\s+mim)?(?:\s+no\s+campo\s+de\s+pesquisa\s+do\s+google|\s+no\s+campo\s+do\s+google|\s+no\s+google|\s+na\s+internet|\s+na\s+web)?\s*[:\-]?\s*(.+)$",
        r"(?i).*\b(?:digita(?:r)?|escreve(?:r)?)\b(?:\s+no\s+campo\s+de\s+pesquisa\s+do\s+google|\s+no\s+google)?\s*[:\-]?\s*(.+)$",
        r"(?i).*\b(?:abre(?:ir)?\s+o\s+google\s+e\s+)?(?:pesquisa(?:r)?|procura(?:r)?|busca(?:r)?)\b\s*[:\-]?\s*(.+)$",
    )
    for p in padroes_query:
        m = re.match(p, raw)
        if m and m.group(1).strip():
            query = m.group(1).strip(" .,!?:;\"'")
            break

    if pedido_natural_video and not query:
        m_video = re.search(r"(?i)\bquero\s+ver\s+(?:um\s+|uma\s+)?(.+)$", raw)
        if m_video and m_video.group(1).strip():
            query = m_video.group(1).strip(" .,!?:;\"'")

    # Extracao adicional para frases longas com pedido de video.
    if (pediu_youtube or pedido_video) and not query:
        m_video_de = re.search(r"(?i)\b(?:video|videos|vídeo|vídeos)\s+(?:de|sobre)\s+(.+)$", raw)
        if m_video_de and m_video_de.group(1).strip():
            query = m_video_de.group(1).strip(" .,!?:;\"'")

    if not query:
        query = raw

    # Limpa verbos e frases de comando que as vezes entram junto no começo.
    query = re.sub(
        r"(?i)^\s*(agora\s+)?(pra\s+mim\s+|para\s+mim\s+)?(pesquisa(?:r)?|procura(?:r)?|busca(?:r)?|digita(?:r)?|escreve(?:r)?)\s+",
        "",
        query,
    ).strip(" .,!?:;\"'")
    query = re.sub(r"(?i)^\s*quero\s+ver\s+(?:um\s+|uma\s+)?", "", query).strip(" .,!?:;\"'")
    query = re.sub(r"(?i)^\s*(do|da|no|na)\s+google\s+", "", query).strip(" .,!?:;\"'")
    query = re.sub(r"(?i)\b(aqui\s+no\s+youtube|no\s+youtube|do\s+youtube|aqui\s+no\s+google|no\s+google|do\s+google)\b", " ", query)
    query = re.split(
        r"(?i)\b(preciso\s+que|quero\s+que|abre\s+para\s+mim|abrir\s+para\s+mim|pra\s+mim|para\s+mim|agora)\b",
        query,
        maxsplit=1,
    )[0].strip(" .,!?:;\"'")
    query = re.sub(r"(?i)\s+", " ", query).strip()

    if not query:
        return "Me diga o tema da pesquisa e eu busco para voce agora."

    # Tema final para pedidos de video/YouTube: remove palavras de interface.
    if pediu_youtube or pedido_video:
        query = re.sub(r"(?i)^\s*(video|videos|vídeo|vídeos)\s+(de|sobre)\s+", "", query).strip(" .,!?:;\"'")
        query = re.sub(r"(?i)^\s*(youtube|you\s*tube)\s+", "", query).strip(" .,!?:;\"'")

    # Sempre usa o navegador quando o usuário menciona google/navegador/campo/digita
    quer_navegador = any(g in norm for g in (
        "no google", "no navegador", "no chrome", "no firefox", "no edge",
        "pelo navegador", "abre o google", "abre o navegador", "abrir o google",
        "campo", "campo de pesquisa", "campo do google",
        "digita", "digitar", "escreve", "escrever",
    ))
    if pedido_natural_video or ("na tela" in norm) or ("notebook" in norm):
        quer_navegador = True

    # Pedido de video no YouTube: sempre abrir direto no YouTube.
    if pediu_youtube or (pedido_video and pedido_natural_video):
        try:
            resultado_yt = str(tools.executar("pesquisar_no_youtube", {"query": query}))
            return resultado_yt
        except Exception as e:
            return f"Nao consegui abrir o YouTube com '{query}' agora ({e}). Tente de novo em instantes."

    qnorm = _normalize_text(query)

    # Evita pesquisar frase de comando em vez do tema.
    cmd_hits = sum(1 for x in ("google", "campo", "digita", "escreve", "pesquisa", "pesquisar") if x in qnorm)
    if (len(query.split()) > 14 and any(x in norm for x in ("google", "campo", "digita", "escreve"))) or (
        cmd_hits >= 2 and len(query.split()) <= 12
    ):
        return "Me diga so o tema curto da pesquisa (ex: 'video de carro') que eu digito no Google agora."

    if not quer_navegador:
        # Tenta busca silenciosa pela API primeiro (resposta rápida via chat)
        try:
            resultado = str(tools.executar("pesquisar_web", {"query": query}))
        except Exception:
            resultado = ""

        rnorm = _normalize_text(resultado)
        api_ok = (
            resultado.strip()
            and "erro" not in rnorm
            and "failed" not in rnorm
            and "nao consegui" not in rnorm
            and len(resultado.strip()) > 80  # resultado muito curto = provavelmente inútil
        )
        if api_ok:
            saida = resultado.strip()
            if len(saida) > 1400:
                saida = saida[:1400].rstrip() + "..."
            return saida

    # Usuário quer o navegador, ou a API falhou — abre o Google e digita
    try:
        resultado_nav = str(tools.executar("pesquisar_no_navegador", {"query": query}))
        return resultado_nav
    except Exception as e:
        return f"Nao consegui pesquisar '{query}' agora ({e}). Tente de novo em instantes."


def _direct_file_find_action(texto: str) -> str | None:
    """Busca arquivo/pasta no log quando usuário pergunta onde está algo que foi criado."""
    if not isinstance(texto, str):
        return None
    raw = texto.strip()
    norm = _normalize_text(raw)
    if not norm:
        return None

    # Padrões de intenção de busca de arquivo/pasta
    gatilhos_busca = (
        "onde esta", "onde fica", "onde foi", "onde salvo", "onde salvou",
        "cade o arquivo", "cade a pasta", "cade o",
        "acha o arquivo", "acha a pasta", "encontra o arquivo", "encontra a pasta",
        "nao acho", "nao encontro", "nao esta mais",
        "qual o caminho", "qual e o caminho",
        "listar arquivos", "quais arquivos", "arquivos criados", "pastas criadas",
    )
    # Comandos de abrir algo que foi criado antes (sem caminho explícito)
    gatilhos_abrir = ("abre o arquivo", "abre a pasta", "abrir o arquivo", "abrir a pasta")

    eh_listagem = any(g in norm for g in (
        "listar arquivos", "quais arquivos", "arquivos criados", "pastas criadas",
        "quais pastas", "mostrar arquivos",
    ))
    if eh_listagem:
        resultado = memory.listar_arquivos_criados()
        return resultado

    eh_busca = any(g in norm for g in gatilhos_busca + gatilhos_abrir)
    if not eh_busca:
        return None

    # Extrai o nome do arquivo/pasta (palavras após o gatilho)
    trecho = re.sub(
        r"(?i)^\s*(onde esta|onde fica|onde foi|onde salvo|onde salvou|cade o arquivo|cade a pasta|"
        r"cade o|acha o arquivo|acha a pasta|encontra o arquivo|encontra a pasta|nao acho|"
        r"nao encontro|abre o arquivo|abre a pasta|abrir o arquivo|abrir a pasta|"
        r"qual o caminho|qual e o caminho)\s*[:\-]?\s*",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    if not trecho or len(trecho) < 2:
        # Sem nome específico — lista tudo
        return memory.listar_arquivos_criados()

    resultados = memory.buscar_arquivo(trecho)
    if not resultados:
        return None  # deixa LLM tentar com ver_tela / criatividade

    if len(resultados) == 1:
        e = resultados[0]
        caminho = e["caminho"]
        tipo = e.get("tipo", "arquivo")
        # Se pediu para abrir, abre direto
        if any(g in norm for g in ("abre", "abrir", "abra")):
            try:
                tools.executar("abrir_arquivo", {"caminho": caminho})
                return f"Pronto, abrindo {tipo} '{e['nome']}' em {caminho}."
            except Exception:
                return f"Encontrei o {tipo} em {caminho}, mas nao consegui abrir. Tente manualmente."
        return f"O {tipo} '{e['nome']}' está em: {caminho}"

    linhas = [f"Encontrei {len(resultados)} resultados para '{trecho}':"]
    for e in resultados:
        linhas.append(f"  [{e['tipo']}] {e['nome']} → {e['caminho']}")
    return "\n".join(linhas)



    norm = _normalize_text(texto)
    if not norm:
        return None
    direct = _SMALL_TALK_RESPONSES.get(norm)
    if direct:
        return direct

    # Respostas locais para variações comuns (ex.: "oi tudo bem")
    if any(marker in norm for marker in _FAST_CHAT_MARKERS):
        if "tudo bem" in norm or "como voce" in norm or "como vc" in norm:
            return "Tudo certo por aqui. Como posso te ajudar agora?"
        if "ouvindo" in norm:
            nome = _fmt_name() or ""
            if nome:
                return f"Estou te ouvindo sim, {nome}. Pode falar."
            return "Estou te ouvindo sim. Pode falar."
        return _ready_response()

    return None


def _is_invalid_vision_text(texto: str) -> bool:
    t = (texto or "").strip()
    if not t:
        return True
    if t in {"!", "!!", "!!!", ".", "..", "...", "?", "??", "???"}:
        return True
    if len(t) <= 3 and all(ch in "!?.," for ch in t):
        return True
    return False


def _parse_args(args_raw):
    if isinstance(args_raw, dict):
        return args_raw
    if isinstance(args_raw, str):
        s = args_raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {"valor": parsed}
        except json.JSONDecodeError:
            return {}
    return {}


def _sanitize_tool_args(nome: str, args: dict) -> dict:
    """Normaliza argumentos malformados vindos do modelo."""
    if not isinstance(args, dict):
        return {}

    if nome == "ver_tela":
        pergunta = args.get("pergunta")
        if not pergunta or not isinstance(pergunta, str):
            args["pergunta"] = "Descreva o que está na tela em português."
        else:
            raw = pergunta.strip()
            if raw.startswith("{") and raw.endswith("}"):
                # Modelo enviou schema JSON em vez da pergunta real — usa pergunta padrão.
                args["pergunta"] = "Descreva o que está na tela em português."
            elif len(raw) < 3:
                args["pergunta"] = "Descreva o que está na tela em português."

    return args


def _try_json_tool_payload(txt: str):
    """Tenta ler um payload JSON de tool-call e retorna dict normalizado."""
    try:
        payload = json.loads(txt)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    name = payload.get("name") or payload.get("tool") or payload.get("function")
    if isinstance(name, dict):
        name = name.get("name")
    if not isinstance(name, str) or name not in _TOOL_NAMES:
        return None

    args = payload.get("arguments")
    if args is None:
        args = payload.get("parameters")
    if args is None:
        args = {}

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"pergunta": args}

    if not isinstance(args, dict):
        args = {"valor": args}

    args = _sanitize_tool_args(name, args)

    return {
        "id": "call_content_1",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


def _extract_tool_call_from_content(content):
    """Fallback: alguns modelos retornam tool call como texto JSON em `content`."""
    if not isinstance(content, str):
        return None

    txt = content.strip()
    if not txt:
        return None

    # Remove cercas markdown caso venha como ```json ... ```.
    txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s*```$", "", txt).strip()

    # Caso comum: payload puro.
    parsed = _try_json_tool_payload(txt)
    if parsed:
        return parsed

    # Fallback: tenta achar um objeto JSON dentro do texto.
    match = re.search(r"\{[\s\S]*\}", txt)
    if not match:
        return None

    return _try_json_tool_payload(match.group(0))


def _log_event(event_type: str, payload: dict):
    if not config.LOG_TO_FILE:
        return
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    log_path = os.path.join(data_dir, "agent.log.jsonl")
    record = {
        "ts": datetime.now().isoformat(),
        "event": event_type,
        "payload": payload,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _chat_groq(mensagens, usar_tools=True):
    import time
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.GROQ_MODEL,
        "messages": mensagens,
        "temperature": 0.5,
        "max_tokens": 512,
    }
    if usar_tools:
        payload["tools"] = tools.TOOL_DEFINITIONS
        payload["tool_choice"] = "auto"
    
    for tentativa in range(5):  # Aumentado de 3 para 5 tentativas
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
        except Exception as e:
            if tentativa < 4:
                time.sleep(2 ** tentativa)  # 1, 2, 4, 8 segundos de backoff
                continue
            return None, f"Erro de conexão: {e}"
        
        if resp.status_code == 429:
            try:
                # Tenta extrair o tempo de espera da mensagem
                msg = resp.json().get("error", {}).get("message", "")
                if "try again in" in msg:
                    retry_after = float(msg.split("try again in ")[1].split("s")[0]) + 0.5
                else:
                    retry_after = 2 ** (tentativa + 1)  # 2, 4, 8, 16 segundos
            except Exception:
                retry_after = 2 ** (tentativa + 1)
            
            retry_after = min(retry_after, 20.0)  # Máximo 20 segundos
            print(f"[brain] Rate limit. Aguardando {retry_after:.1f}s...")
            time.sleep(retry_after)
            continue
        
        if resp.status_code != 200:
            return None, f"Erro no Groq ({resp.status_code}): {resp.text[:300]}"
        
        data = resp.json()
        return data["choices"][0]["message"], None
    
    return None, "Limite de uso momentâneo atingido. Aguarde 30s antes de tentar novamente."


def _chat_openrouter(mensagens, usar_tools=True):
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.MODEL,
        "messages": mensagens,
        "temperature": 0.7,
    }
    if usar_tools:
        payload["tools"] = tools.TOOL_DEFINITIONS
        payload["tool_choice"] = "auto"
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=90,
    )
    if resp.status_code != 200:
        return None, f"Erro na API ({resp.status_code}): {resp.text[:300]}"
    data = resp.json()
    return data["choices"][0]["message"], None


def _chat_openai(mensagens, usar_tools=True):
    """Chama a API oficial da OpenAI (ChatGPT)."""
    if not config.OPENAI_API_KEY:
        return None, "Chave OpenAI não configurada. Adicione OPENAI_API_KEY no arquivo .env"
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": getattr(config, "OPENAI_MODEL", "gpt-4o-mini"),
        "messages": mensagens,
        "temperature": 0.9,
        "top_p": 0.95,
        "max_tokens": 1024,
    }
    if usar_tools:
        payload["tools"] = tools.TOOL_DEFINITIONS
        payload["tool_choice"] = "auto"
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
    except Exception as e:
        return None, f"Erro de conexão OpenAI: {e}"
    if resp.status_code == 401:
        return None, "Chave OpenAI inválida. Verifique OPENAI_API_KEY no arquivo .env"
    if resp.status_code == 429:
        return None, "Limite de uso OpenAI atingido. Tente novamente em instantes."
    if resp.status_code != 200:
        return None, f"Erro OpenAI ({resp.status_code}): {resp.text[:300]}"
    try:
        data = resp.json()
    except Exception:
        return None, f"Resposta inválida da OpenAI (corpo vazio ou malformado): {resp.text[:200]}"
    try:
        return data["choices"][0]["message"], None
    except (KeyError, IndexError) as e:
        return None, f"Resposta inesperada da OpenAI: {e} — {str(data)[:200]}"


def _chat_ollama(mensagens, usar_tools=True):
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": mensagens,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.5,
            "num_predict": 220,
        },
    }
    if usar_tools:
        payload["tools"] = tools.TOOL_DEFINITIONS
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=45,
    )
    if resp.status_code != 200:
        return None, f"Erro no Ollama ({resp.status_code}): {resp.text[:300]}"
    data = resp.json()
    return data.get("message", {}), None


def _is_rate_limit_error(err: str | None) -> bool:
    if not err:
        return False
    norm = _normalize_text(err)
    return (
        "limite de uso" in norm
        or "rate limit" in norm
        or "429" in norm
        or "too many requests" in norm
    )


def _chat_with_provider(mensagens, tools=True):
    provider = str(getattr(config, "PROVIDER", "groq")).lower().strip()
    if provider == "openai":
        message, err = _chat_openai(mensagens, usar_tools=tools)
        if message:
            return message, None
        # Fallback opcional para Groq quando OpenAI falhar
        if bool(getattr(config, "OPENAI_FALLBACK_GROQ", False)):
            print(f"[brain] OpenAI falhou ({err}), tentando Groq...")
            msg2, err2 = _chat_groq(mensagens, usar_tools=tools)
            if msg2:
                return msg2, None
            return None, err or err2 or "Falha ao obter resposta."
        return None, err or "Falha ao obter resposta da OpenAI."
    if provider == "groq":
        message, err = _chat_groq(mensagens, usar_tools=tools)
        if message:
            return message, None

        # Fallback automático para manter continuidade em sessões longas.
        # Se Groq limitar/falhar, tenta Ollama local.
        msg2, err2 = _chat_ollama(mensagens, usar_tools=tools)
        if msg2:
            return msg2, None

        # Último fallback: OpenRouter (se configurado).
        msg3, err3 = _chat_openrouter(mensagens, usar_tools=tools)
        if msg3:
            return msg3, None

        if _is_rate_limit_error(err):
            return None, (
                "Estou com alto uso na nuvem agora e o fallback local também falhou. "
                "Tente novamente em alguns segundos."
            )
        return None, err or err2 or err3 or "Falha ao obter resposta do provedor."
    if provider == "ollama":
        return _chat_ollama(mensagens, usar_tools=tools)
    return _chat_openrouter(mensagens, usar_tools=tools)


def _extract_tool_calls(message):
    tool_calls = message.get("tool_calls") or []
    normalized = []
    for idx, tc in enumerate(tool_calls):
        fn = tc.get("function", {})
        name = fn.get("name")
        args = fn.get("arguments", "{}")
        call_id = tc.get("id") or f"call_{idx+1}"

        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)

        if not name or name not in _TOOL_NAMES:
            continue

        normalized.append({
            "id": call_id,
            "function": {"name": name, "arguments": args},
        })

    if not normalized:
        fallback = _extract_tool_call_from_content(message.get("content"))
        if fallback:
            normalized.append(fallback)

    return normalized


def processar(mensagem_usuario: str) -> str:
    """Processa uma mensagem do usuário e retorna a resposta final."""

    _emit_progress("phase", message="Entendi seu pedido. Vou planejar e executar em etapas.")

    provider = str(getattr(config, "PROVIDER", "groq")).lower().strip()
    modo_openai = provider == "openai"

    # No modo OpenAI: só intercepta comandos de controle (voz/mic), tudo mais vai para o GPT.
    # No modo Groq/Ollama: usa atalhos locais para respostas rápidas e económicas.
    if not modo_openai:
        if _is_simple_greeting(mensagem_usuario):
            resposta = _greeting_response()
            _log_event("assistant_message", {"content": resposta})
            memory.add_to_history("user", mensagem_usuario)
            memory.add_to_history("assistant", resposta)
            return resposta

        resposta_capacidade = _capability_response(mensagem_usuario)
        if resposta_capacidade:
            _log_event("assistant_message", {"content": resposta_capacidade})
            memory.add_to_history("user", mensagem_usuario)
            memory.add_to_history("assistant", resposta_capacidade)
            return resposta_capacidade

        resposta_curta = _small_talk_response(mensagem_usuario)
        if resposta_curta:
            _log_event("assistant_message", {"content": resposta_curta})
            memory.add_to_history("user", mensagem_usuario)
            memory.add_to_history("assistant", resposta_curta)
            return resposta_curta

    # Comandos de controle (voz/mic) — sempre interceptados independente do provedor
    tarefa_local = _direct_task_action(mensagem_usuario)
    if tarefa_local:
        _log_event("assistant_message", {"content": tarefa_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", tarefa_local)
        return tarefa_local

    telegram_local = _direct_telegram_action(mensagem_usuario)
    if telegram_local:
        _log_event("assistant_message", {"content": telegram_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", telegram_local)
        return telegram_local

    yt_ops_local = _direct_youtube_ops_action(mensagem_usuario)
    if yt_ops_local:
        _log_event("assistant_message", {"content": yt_ops_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", yt_ops_local)
        return yt_ops_local

    download_local = _direct_video_download_action(mensagem_usuario)
    if download_local:
        _log_event("assistant_message", {"content": download_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", download_local)
        return download_local

    busca_local = _direct_web_search_action(mensagem_usuario)
    if busca_local:
        _log_event("assistant_message", {"content": busca_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", busca_local)
        return busca_local

    arquivo_local = _direct_file_find_action(mensagem_usuario)
    if arquivo_local:
        _log_event("assistant_message", {"content": arquivo_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", arquivo_local)
        return arquivo_local

    acao_local = _direct_local_action(mensagem_usuario)
    if acao_local:
        _log_event("assistant_message", {"content": acao_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", acao_local)
        return acao_local

    # Caminho rápido para perguntas de tela: evita duas rodadas no LLM (tool + resumo)
    # e reduz a latência percebida no widget.
    if _is_direct_screen_request(mensagem_usuario):
        _emit_progress("tool_start", tool="ver_tela", label=_tool_label("ver_tela"), args={"pergunta": "resumo da tela"})
        pergunta = "Descreva objetivamente o que aparece na tela em portugues, em ate 6 linhas."

        resposta = "Nao consegui analisar a tela agora."
        try:
            resultado = tools.executar("ver_tela", {"pergunta": pergunta})
            resposta = str(resultado) if resultado else resposta
            if _is_error_result(resposta):
                _emit_progress("tool_error", tool="ver_tela", label=_tool_label("ver_tela"), result=resposta)
            else:
                _emit_progress("tool_success", tool="ver_tela", label=_tool_label("ver_tela"), result=resposta)
        except Exception:
            resposta = "Nao consegui analisar a tela agora."
            _emit_progress("tool_error", tool="ver_tela", label=_tool_label("ver_tela"), result=resposta)

        # Retry automático com prompt mais simples quando o modelo retorna vazio/falha.
        resposta_norm = _normalize_text(resposta)
        if (
            _is_invalid_vision_text(resposta)
            or "nao consegui analisar a tela" in resposta_norm
            or "limite de uso" in resposta_norm
            or "erro groq 429" in resposta_norm
            or "rate limit" in resposta_norm
        ):
            try:
                resultado2 = tools.executar(
                    "ver_tela",
                    {"pergunta": "Liste os principais elementos visiveis na tela em 3 linhas."},
                )
                if resultado2 and (not _is_invalid_vision_text(str(resultado2))):
                    resposta = str(resultado2)
                else:
                    resposta = "Nao consegui analisar a tela agora. Tente novamente em alguns segundos."
            except Exception:
                resposta = "Nao consegui analisar a tela agora. Tente novamente em alguns segundos."

        _log_event("assistant_message", {"content": resposta[: config.LOG_MAX_CHARS]})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", resposta)
        _emit_progress("finished", success=not _is_error_result(resposta), message="Concluído.")
        return resposta

    confirmado = mensagem_usuario.strip().upper().startswith(f"{config.CONFIRM_TOKEN}:")

    historico = memory.get_history(config.MAX_HISTORY)
    mensagens = [{"role": "system", "content": SYSTEM_PROMPT}]
    mensagens.extend(historico)
    mensagens.append({"role": "user", "content": mensagem_usuario})
    _log_event("user_message", {"content": mensagem_usuario[: config.LOG_MAX_CHARS]})

    # REGRA SEMPRE ATIVA: antes de qualquer tarefa, olha a tela primeiro.
    # Assim como um humano olha o que está na frente antes de agir,
    # a Evelyn sempre captura o estado atual da tela antes de executar qualquer coisa.
    # Exceção: mensagens puramente conversacionais curtas (menos de 8 palavras e sem verbos de ação).
    norm_user = _normalize_text(mensagem_usuario)
    _palavras = norm_user.split()
    _eh_conversa_pura = (
        len(_palavras) < 8
        and not any(m.strip() in norm_user for m in _ACTION_MARKERS)
        and not any(x in norm_user for x in (
            "pesquisa", "pesquisar", "procura", "procurar", "busca", "buscar",
            "cria", "criar", "faz", "fazer", "abre", "abrir", "fecha", "fechar",
            "escreve", "digita", "salva", "envia", "manda", "executa", "roda",
            "instala", "desinstala", "copia", "move", "apaga", "deleta",
        ))
    )
    if not _eh_conversa_pura:
        try:
            _emit_progress("tool_start", tool="ver_tela", label=_tool_label("ver_tela"), args={})
            ctx_tela = tools.executar(
                "ver_tela",
                {
                    "pergunta": (
                        "Descreva o estado atual da tela em detalhes: "
                        "quais janelas estão abertas, qual está em foco/ativa, "
                        "o que está visível (títulos, conteúdo, abas abertas). "
                        "Seja específico — isso será usado para decidir qual ação executar."
                    )
                },
            )
            if ctx_tela and not _is_error_result(str(ctx_tela)):
                _emit_progress("tool_success", tool="ver_tela", label=_tool_label("ver_tela"), result=str(ctx_tela))
                mensagens.insert(1, {
                    "role": "system",
                    "content": (
                        f"[ESTADO ATUAL DA TELA — LEIA ANTES DE AGIR]:\n{ctx_tela}\n\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "1. Sempre analise o estado da tela acima antes de executar qualquer ação.\n"
                        "2. NÃO feche, minimize ou altere janelas que o usuário não pediu.\n"
                        "3. Se o navegador já estiver aberto, use-o. Não abra uma nova janela.\n"
                        "4. Se não tiver certeza do que está na tela, use ver_tela novamente.\n"
                        "5. Aja somente na janela/programa correto para a tarefa pedida."
                    ),
                })
        except Exception:
            pass

    fallback_count = 0
    for iteracao in range(4):  # máx. 4 iterações para tool-calling
        # Na última iteração, remove ferramentas para forçar resposta de texto
        usar_tools = iteracao < 3
        try:
            message, err = _chat_with_provider(mensagens, tools=usar_tools)
        except requests.exceptions.Timeout:
            if not preferir_modelo:
                resposta_curta_timeout = _small_talk_response(mensagem_usuario)
                if resposta_curta_timeout:
                    _log_event("assistant_message", {"content": resposta_curta_timeout})
                    memory.add_to_history("user", mensagem_usuario)
                    memory.add_to_history("assistant", resposta_curta_timeout)
                    return resposta_curta_timeout

            provider = str(getattr(config, "PROVIDER", "groq")).lower().strip()
            if provider == "ollama":
                return "Timeout: o Ollama demorou demais. Verifique se o modelo está carregado (ollama run llama3.2:3b)."
            return "Timeout na API. Tente novamente em instantes."
        except requests.exceptions.ConnectionError:
            provider = str(getattr(config, "PROVIDER", "groq")).lower().strip()
            if provider == "ollama":
                return "Ollama não está rodando. Abra um terminal e execute: ollama serve"
            return "Sem conexão com a internet. Verifique sua rede."

        if err:
            return err

        # ── Executa ferramentas se necessário ─────────────
        tool_calls = _extract_tool_calls(message)
        if tool_calls:
            mensagens.append(message)
            for tc in tool_calls:
                nome      = tc["function"]["name"]
                args_raw  = tc["function"]["arguments"]
                args      = _parse_args(args_raw)
                args      = _sanitize_tool_args(nome, args)

                _emit_progress("tool_start", tool=nome, label=_tool_label(nome), args=args)

                if config.SAFE_MODE and (not confirmado) and tools.is_dangerous_tool(nome, args):
                    bloqueio = (
                        "Modo seguro ativo: detectei uma ação potencialmente irreversível. "
                        f"Repita o pedido iniciando com '{config.CONFIRM_TOKEN}:' para executar."
                    )
                    _log_event("tool_blocked", {"tool": nome, "args": args})
                    memory.add_to_history("user", mensagem_usuario)
                    memory.add_to_history("assistant", bloqueio)
                    _emit_progress("tool_error", tool=nome, label=_tool_label(nome), result=bloqueio)
                    _emit_progress("finished", success=False, message="Execução bloqueada por segurança.")
                    return bloqueio

                print(f"  [TOOL] [{nome}] {json.dumps(args, ensure_ascii=False)}")
                try:
                    resultado = tools.executar(nome, args)
                except Exception as ex:
                    resultado = f"Erro ao executar ferramenta '{nome}': {ex}"
                print(f"  [OK] {str(resultado)[:250]}")
                _log_event("tool_result", {
                    "tool": nome,
                    "args": args,
                    "result": str(resultado)[: config.LOG_MAX_CHARS],
                })

                if _is_error_result(resultado):
                    _emit_progress("tool_error", tool=nome, label=_tool_label(nome), result=str(resultado))
                    if _is_retryable_error(resultado):
                        _emit_progress("tool_retry", tool=nome, label=_tool_label(nome), result="Falhou, vou tentar corrigir e executar de novo.")
                        try:
                            resultado_retry = tools.executar(nome, args)
                            resultado = resultado_retry
                            if _is_error_result(resultado_retry):
                                _emit_progress("tool_error", tool=nome, label=_tool_label(nome), result=str(resultado_retry))
                            else:
                                _emit_progress("tool_success", tool=nome, label=_tool_label(nome), result=str(resultado_retry))
                        except Exception as ex_retry:
                            resultado = f"Erro na nova tentativa da ferramenta '{nome}': {ex_retry}"
                            _emit_progress("tool_error", tool=nome, label=_tool_label(nome), result=str(resultado))
                else:
                    _emit_progress("tool_success", tool=nome, label=_tool_label(nome), result=str(resultado))

                mensagens.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      str(resultado),
                })
            continue  # próxima iteração com resultados das tools

        # ── Resposta final de texto ────────────────────────
        resposta = message.get("content") or ""

        # Failsafe: se o modelo devolver tool-call em texto no conteúdo final,
        # reprocessa como chamada de ferramenta em vez de mostrar JSON ao usuário.
        fallback_call = _extract_tool_call_from_content(resposta)
        if fallback_call:
            fallback_count += 1
            if fallback_count > 2:
                # Modelo fica em loop devolvendo JSON — interrompe e responde ao usuário.
                resposta = "Não consegui concluir a ação automaticamente. Pode me descrever melhor o que precisa?"
                _log_event("assistant_message", {"content": resposta})
                memory.add_to_history("user", mensagem_usuario)
                memory.add_to_history("assistant", resposta)
                _emit_progress("finished", success=False, message="Não consegui concluir automaticamente.")
                return resposta

            mensagens.append(message)
            nome = fallback_call["function"]["name"]
            args = _parse_args(fallback_call["function"]["arguments"])
            args = _sanitize_tool_args(nome, args)

            if config.SAFE_MODE and (not confirmado) and tools.is_dangerous_tool(nome, args):
                bloqueio = (
                    "Modo seguro ativo: detectei uma ação potencialmente irreversível. "
                    f"Repita o pedido iniciando com '{config.CONFIRM_TOKEN}:' para executar."
                )
                _log_event("tool_blocked", {"tool": nome, "args": args})
                memory.add_to_history("user", mensagem_usuario)
                memory.add_to_history("assistant", bloqueio)
                return bloqueio

            print(f"  [TOOL] [{nome}] {json.dumps(args, ensure_ascii=False)}")
            resultado = tools.executar(nome, args)
            print(f"  [OK] {str(resultado)[:250]}")
            _log_event("tool_result", {
                "tool": nome,
                "args": args,
                "result": str(resultado)[: config.LOG_MAX_CHARS],
            })
            mensagens.append({
                "role": "tool",
                "tool_call_id": fallback_call["id"],
                "content": str(resultado),
            })
            continue

        if not isinstance(resposta, str):
            resposta = str(resposta)

        # Guarda final: nunca exibir JSON de tool-call cru ao usuário.
        if resposta.strip().startswith("{"):
            try:
                possible = json.loads(resposta.strip())
                if isinstance(possible, dict) and (
                    possible.get("name") in _TOOL_NAMES
                    or possible.get("tool") in _TOOL_NAMES
                ):
                    resposta = "Não consegui completar a ação. Pode reformular o pedido?"
            except (json.JSONDecodeError, Exception):
                pass

        _log_event("assistant_message", {"content": resposta[: config.LOG_MAX_CHARS]})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", resposta)
        _emit_progress("finished", success=True, message="Tarefa concluída.")
        return resposta

    _emit_progress("finished", success=False, message="Limite de passos atingido.")
    return "Atingi o limite de passos. Pode reformular o pedido?"
