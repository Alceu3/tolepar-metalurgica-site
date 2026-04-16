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

# Provedor de IA:
# "ollama"     -> 100% local (sem custo mensal)
# "openrouter" -> nuvem (tem modelos gratis e pagos)
# "groq"       -> nuvem rapida e gratuita (recomendado)
PROVIDER = "groq"

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

AGENT_NAME = "ARIA"
USER_NAME = "Alceu"
LANGUAGE = "pt-BR"

VOICE_ENABLED = True   # False = sem fala (modo silencioso)
MIC_ENABLED = True     # False = só digitar (sem microfone)
INTERACTION_MODE = "hibrido"  # texto | voz | hibrido
MIC_AUTO_START = False  # True = liga microfone automaticamente ao abrir o widget

VOICE_RATE = 165       # Velocidade da fala (palavras/min)
MAX_HISTORY = 8       # Mensagens máximas no contexto

# Microfone: deixe None para usar o padrão do sistema.
# Se necessário, defina um índice específico (ex.: 1, 2, 3).
MIC_DEVICE_INDEX = None  # Auto-detect the best device
MIC_NAME_CONTAINS = ""

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

# Integração WhatsApp (Twilio)
WHATSAPP_ENABLED = (_os.environ.get("WHATSAPP_ENABLED", "true").strip().lower() == "true")
WHATSAPP_WEBHOOK_KEY = _os.environ.get("WHATSAPP_WEBHOOK_KEY", "")
TWILIO_ACCOUNT_SID = _os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = _os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = _os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
OWNER_WHATSAPP = _os.environ.get("OWNER_WHATSAPP", "whatsapp:+5545999363213")
OWNER_EMAIL = _os.environ.get("OWNER_EMAIL", "alceucordeiro29@gmail.com")

# Telegram Bot
TELEGRAM_BOT_TOKEN = _os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = _os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")
