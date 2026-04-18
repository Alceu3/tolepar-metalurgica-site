# ============================================================
#  ARIA - Configurações do Agente
# ============================================================

import os as _os, pathlib as _pl
def _load_env():
    env_file = _pl.Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                _os.environ.setdefault(k.strip(), v.strip())
_load_env()
OPENROUTER_API_KEY = _os.environ.get("OPENROUTER_API_KEY", "")  # https://openrouter.ai/keys
GROQ_API_KEY = _os.environ.get("GROQ_API_KEY", "")  # https://console.groq.com/keys
OPENAI_API_KEY = _os.environ.get("OPENAI_API_KEY", "")  # https://platform.openai.com/api-keys

# Adobe Firefly (Creative Cloud) — https://developer.adobe.com/firefly-services/docs/
# Crie um projeto em https://developer.adobe.com/console e copie as credenciais:
ADOBE_CLIENT_ID     = _os.environ.get("ADOBE_CLIENT_ID", "")
ADOBE_CLIENT_SECRET = _os.environ.get("ADOBE_CLIENT_SECRET", "")

# Telegram Bot — https://t.me/BotFather
# 1. Abra @BotFather no Telegram, envie /newbot e copie o token
# 2. Adicione no arquivo .env (pasta pai):  TELEGRAM_BOT_TOKEN=seu_token_aqui
# 3. Opcional: TELEGRAM_ALLOWED_ID=seu_chat_id  (mande /start ao bot e veja o log)
TELEGRAM_BOT_TOKEN  = _os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_ID = _os.environ.get("TELEGRAM_ALLOWED_ID", "")
TELEGRAM_MIRROR_TO_LOCAL = (_os.environ.get("TELEGRAM_MIRROR_TO_LOCAL", "true").strip().lower() == "true")
TELEGRAM_SPEAK_ON_LOCAL = (_os.environ.get("TELEGRAM_SPEAK_ON_LOCAL", "true").strip().lower() == "true")

# YouTube Data API (publicacao e agendamento 100% automaticos)
# Configure no .env:
# YOUTUBE_CLIENT_ID=...
# YOUTUBE_CLIENT_SECRET=...
# YOUTUBE_REFRESH_TOKEN=...
# Opcional:
# YOUTUBE_DEFAULT_CATEGORY_ID=2   (Autos & Vehicles)
# YOUTUBE_TRACKER_CSV=C:\\caminho\\youtube_tracker.csv
# YOUTUBE_CHANNEL_METRICS_CSV=C:\\caminho\\youtube_channel_metrics.csv
YOUTUBE_CLIENT_ID = _os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = _os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = _os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_DEFAULT_CATEGORY_ID = _os.environ.get("YOUTUBE_DEFAULT_CATEGORY_ID", "2")
YOUTUBE_TRACKER_CSV = _os.environ.get("YOUTUBE_TRACKER_CSV", "")
YOUTUBE_CHANNEL_METRICS_CSV = _os.environ.get("YOUTUBE_CHANNEL_METRICS_CSV", "")

# Provedor de IA:
# "ollama"     -> 100% local (sem custo mensal)
# "openrouter" -> nuvem (tem modelos gratis e pagos)
# "groq"       -> nuvem rapida e gratuita (recomendado)
# "openai"     -> ChatGPT oficial (requer chave paga)
PROVIDER = "openai"

# Groq
GROQ_MODEL = "llama-3.3-70b-versatile"  # 70b, rapido e gratuito

# Ollama local
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_MODEL_VISION = "moondream:latest"

# Modelos disponíveis (escolha um):
# "google/gemini-2.0-flash-exp:free"       → grátis, suporta visão + tools
# "meta-llama/llama-3.3-70b-instruct:free" → grátis, só tools
# "openai/gpt-4o-mini"                     → pago, muito confiável
# "anthropic/claude-3.5-sonnet"            → pago, mais inteligente
MODEL = "google/gemini-2.0-flash-exp:free"
MODEL_VISION = "google/gemini-2.0-flash-exp:free"

# OpenAI (ChatGPT oficial)
# "gpt-4o"       → mais inteligente (pago)
# "gpt-4o-mini"  → mais barato e rápido (recomendado)
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_FALLBACK_GROQ = False  # True = usa Groq se OpenAI falhar

AGENT_NAME = "Evelyn"
USER_NAME = "Alceu"
LANGUAGE = "pt-BR"

VOICE_ENABLED = True   # False = sem fala (modo silencioso)
MIC_ENABLED = True     # False = só digitar (sem microfone)
INTERACTION_MODE = "hibrido"  # texto | voz | hibrido
MIC_AUTO_START = False  # False = nao prende o microfone ao abrir; usa padrao do notebook
MIC_AUTO_SEND = False   # False = evita envio automatico com ruido/voz fantasma
MIC_REQUIRE_WAKE_WORD = True  # True = so processa quando comecar com "Evelyn"
MIC_WAKE_WORD = "evelyn"  # Ex.: "evelyn"
MIC_AUTO_SWITCH_DEVICE = False  # False = nao troca device automaticamente (modo manual)

# Avatar visual da Evelyn (fundo animado no painel)
AVATAR_ENABLED = False
AVATAR_VIDEO_PATH = r"C:\Users\ACER\Downloads\share_video.mp4"
AVATAR_HEIGHT = 180
AVATAR_FPS = 18
PANEL_START_EXPANDED = True

VOICE_RATE = 175       # Velocidade da fala (palavras/min)
MAX_HISTORY = 8       # Mensagens máximas no contexto

# Microfone: detecta automaticamente pelo nome do fone conectado.
# Não fixar MIC_DEVICE_INDEX para evitar quebrar quando o índice muda.
MIC_DEVICE_INDEX = None
MIC_NAME_CONTAINS = "realtek"

# Segurança: exige confirmação para ações potencialmente irreversíveis.
SAFE_MODE = True
CONFIRM_TOKEN = "CONFIRMO"

# Logging de execução para auditoria e replay de problemas.
LOG_TO_FILE = True
LOG_MAX_CHARS = 300

# Fallback para cliques quando o modelo gerar coordenadas de outra resolução.
REFERENCE_SCREEN_WIDTH = 1920
REFERENCE_SCREEN_HEIGHT = 1080

# Integração ARIA nuvem <-> ARIA local
CLOUD_API_URL = _os.environ.get("CLOUD_API_URL", "")
CLOUD_API_TOKEN = _os.environ.get("CLOUD_API_TOKEN", "")
LOCAL_PROJECTS_DIR = str((_pl.Path(__file__).parent / "projetos").resolve())
