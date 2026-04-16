import json
from datetime import datetime
import os
import re
import unicodedata
import requests
import config
import memory
import tools

SYSTEM_PROMPT = f"""Você é {config.AGENT_NAME}, um agente de IA autônomo que trabalha AO LADO do usuário como parceiro de trabalho.

CAPACIDADES:
👁️  Ver a tela — você enxerga o computador em tempo real
🖐️  Controlar — mouse, teclado, abrir sites e navegar
💬  Conversar — voz e texto em português
📋  Memória — guarda clientes, tarefas e projetos
🧠  Raciocínio — planeja e executa tarefas complexas

COMO AGIR:
• Use ver_tela somente quando a tarefa depender da tela atual ou antes de automatizar cliques
• Para preencher formulários: veja a tela → identifique os campos → preencha um a um
• Para cadastros em plataformas: abra o site, veja a tela, execute passo a passo
• Salve dados importantes de clientes e tarefas na memória
• Sempre confirme ações irreversíveis (envios, compras, pagamentos) ANTES de executar
• Quando for realizar múltiplas ações, explique o plano brevemente antes
• Se encontrar erro em algum passo, analise a tela e tente uma abordagem alternativa
• Se a solicitação for apenas conversa, explicação ou planejamento textual, não use ferramentas

PERFIL:
Você ajuda com: cadastros em plataformas, atendimento a clientes, responder dúvidas,
gerenciar projetos, automatizar tarefas repetitivas e resolver problemas junto com o usuário.

Fale SEMPRE em português brasileiro, de forma profissional e amigável."""

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
    "com que eu falo": "Voce esta falando com ARIA, sua assistente de IA. Posso ver sua tela, clicar, digitar, abrir sites e responder perguntas.",
    "com quem falo": "Voce fala com ARIA, uma IA assistente. Como posso te ajudar?",
    "com quem eu falo": "Voce fala com ARIA, sua assistente de IA. Posso ver sua tela, clicar, digitar, abrir sites e responder perguntas.",
    "quem e voce": "Sou a ARIA, sua assistente de IA. Posso ajudar com tarefas na tela, automacao e conversas.",
    "quem es voce": "Sou a ARIA, sua assistente de IA. Posso ajudar com tarefas na tela, automacao e conversas.",
    "o que e isso": "Sou a ARIA, uma assistente de IA integrada ao seu computador.",
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

_CAPABILITY_MARKERS = (
    "o que consegue fazer",
    "o que voce consegue fazer",
    "o que vc consegue fazer",
    "o que sabe fazer",
    "como pode ajudar",
)

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
    pediu_ouvir = norm in {"ouvir", "me ouvir", "me ouve"}

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
    if norm in _MIC_LIGAR:
        return "__TOGGLE_MIC_ON__"
    if norm in _MIC_DESLIGAR:
        return "__TOGGLE_MIC_OFF__"

    if pediu_ouvir:
        nome = _fmt_name()
        if nome:
            return f"Estou te ouvindo, {nome}. Pode falar."
        return "Estou te ouvindo. Pode falar."

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


def _small_talk_response(texto: str) -> str | None:
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

    acao_local = _direct_local_action(mensagem_usuario)
    if acao_local:
        _log_event("assistant_message", {"content": acao_local})
        memory.add_to_history("user", mensagem_usuario)
        memory.add_to_history("assistant", acao_local)
        return acao_local

    # Caminho rápido para perguntas de tela: evita duas rodadas no LLM (tool + resumo)
    # e reduz a latência percebida no widget.
    if _is_direct_screen_request(mensagem_usuario):
        pergunta = "Descreva objetivamente o que aparece na tela em portugues, em ate 6 linhas."

        resposta = "Nao consegui analisar a tela agora."
        try:
            resultado = tools.executar("ver_tela", {"pergunta": pergunta})
            resposta = str(resultado) if resultado else resposta
        except Exception:
            resposta = "Nao consegui analisar a tela agora."

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
        return resposta

    confirmado = mensagem_usuario.strip().upper().startswith(f"{config.CONFIRM_TOKEN}:")

    historico = memory.get_history(config.MAX_HISTORY)
    mensagens = [{"role": "system", "content": SYSTEM_PROMPT}]
    mensagens.extend(historico)
    mensagens.append({"role": "user", "content": mensagem_usuario})
    _log_event("user_message", {"content": mensagem_usuario[: config.LOG_MAX_CHARS]})

    fallback_count = 0
    for iteracao in range(4):  # máx. 4 iterações para tool-calling
        # Na última iteração, remove ferramentas para forçar resposta de texto
        usar_tools = iteracao < 3
        try:
            message, err = _chat_with_provider(mensagens, tools=usar_tools)
        except requests.exceptions.Timeout:
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
        return resposta

    return "Atingi o limite de passos. Pode reformular o pedido?"
