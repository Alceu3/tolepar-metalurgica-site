"""
Bot do Telegram para conversar com a Evelyn remotamente.
Inicia em thread separada, não bloqueia o widget.

Configuração:
1. Crie um bot em @BotFather no Telegram -> copie o token
2. Adicione no .env:  TELEGRAM_BOT_TOKEN=seu_token_aqui
3. Opcional - restringir a um único usuário:
   TELEGRAM_ALLOWED_ID=123456789   (seu chat_id — mande /start e veja no log)
"""
import asyncio
import logging
import threading
import os
import time
import ctypes

import config

logger = logging.getLogger("telegram_bot")

# ── estado do loop ──────────────────────────────────────────────────────
_started: bool = False
_BOT_MUTEX = None
_LOCAL_MESSAGE_HOOK = None


def set_local_message_hook(callback):
    """Registra callback para espelhar mensagens do Telegram na UI local."""
    global _LOCAL_MESSAGE_HOOK
    _LOCAL_MESSAGE_HOOK = callback


def _emit_local(event_type: str, **payload):
    cb = _LOCAL_MESSAGE_HOOK
    if not cb:
        return
    try:
        cb(event_type, payload)
    except Exception as exc:
        logger.debug(f"Falha ao emitir evento local do Telegram: {exc}")


def _acquire_single_instance() -> bool:
    """Garante apenas 1 poller do Telegram por máquina/sessão."""
    global _BOT_MUTEX
    try:
        _BOT_MUTEX = ctypes.windll.kernel32.CreateMutexW(
            None,
            True,
            "Global\\EVELYN_TELEGRAM_BOT_SINGLE_INSTANCE",
        )
        err = ctypes.windll.kernel32.GetLastError()
        if err == 183:  # ERROR_ALREADY_EXISTS
            return False
        return True
    except Exception:
        # Se não conseguir usar mutex, segue para não bloquear funcionalidade.
        return True


def start():
    """Chamado pelo widget.py em thread daemon. Não bloqueia."""
    global _started
    if _started:
        return
    if not _acquire_single_instance():
        logger.info("Instância do bot Telegram já ativa em outro processo.")
        return
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN não configurado — bot desativado.")
        return
    _started = True
    t = threading.Thread(target=_run_bot, args=(token,), daemon=True, name="TelegramBot")
    t.start()
    logger.info("Thread do bot Telegram iniciada.")


def _run_bot(token: str):
    # Mantém o bot vivo mesmo com erros transitórios de rede/API.
    while True:
        try:
            asyncio.run(_main(token))
            logger.warning("Loop do Telegram encerrou inesperadamente. Reiniciando...")
        except Exception as exc:
            logger.error(f"Bot Telegram caiu: {exc}. Tentando reconectar em 5s...")
        time.sleep(5)


async def _main(token: str):
    from telegram import Update
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        filters, ContextTypes,
    )

    allowed_id = str(getattr(config, "TELEGRAM_ALLOWED_ID", "") or "").strip()
    _env_file  = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    def _salvar_owner(uid: str):
        """Persiste TELEGRAM_ALLOWED_ID no .env e no config em memória."""
        try:
            if os.path.exists(_env_file):
                txt = open(_env_file, encoding="utf-8").read()
                if "TELEGRAM_ALLOWED_ID" in txt:
                    import re as _re
                    txt = _re.sub(r"TELEGRAM_ALLOWED_ID=.*", f"TELEGRAM_ALLOWED_ID={uid}", txt)
                else:
                    txt = txt.rstrip() + f"\nTELEGRAM_ALLOWED_ID={uid}\n"
                open(_env_file, "w", encoding="utf-8").write(txt)
            config.TELEGRAM_ALLOWED_ID = uid  # atualiza em memória
            logger.info(f"TELEGRAM_ALLOWED_ID salvo: {uid}")
        except Exception as exc:
            logger.warning(f"Não foi possível salvar TELEGRAM_ALLOWED_ID: {exc}")

    async def _start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = str(update.effective_chat.id)
        logger.info(f"Telegram /start — chat_id={uid}")
        # salva automaticamente o primeiro dono que mandar /start
        current = str(getattr(config, "TELEGRAM_ALLOWED_ID", "") or "").strip()
        if not current:
            _salvar_owner(uid)
        nome = getattr(config, "AGENT_NAME", "Evelyn")
        await update.message.reply_text(
            f"Olá! Sou a {nome}. Pode mandar sua mensagem 🤖\n"
            f"(seu chat\\_id é `{uid}`)",
            parse_mode="Markdown",
        )

    async def _msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = str(update.effective_chat.id)
        current_allowed = str(getattr(config, "TELEGRAM_ALLOWED_ID", "") or "").strip()
        if current_allowed and uid != current_allowed:
            logger.warning(f"Acesso negado para chat_id={uid}")
            await update.message.reply_text("⛔ Acesso não autorizado.")
            return

        texto = (update.message.text or "").strip()
        if not texto:
            return

        logger.info(f"Telegram [{uid}]: {texto}")
        _emit_local("incoming", chat_id=uid, text=texto)
        await update.message.chat.send_action("typing")

        loop = asyncio.get_event_loop()
        try:
            import brain
            resposta = await loop.run_in_executor(None, brain.processar, texto)
        except Exception as exc:
            resposta = f"Erro interno: {exc}"

        _emit_local("outgoing", chat_id=uid, text=resposta)
        for chunk in _split(resposta, 4000):
            await update.message.reply_text(chunk)

    def _split(text: str, size: int):
        return [text[i:i+size] for i in range(0, max(len(text), 1), size)]

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _msg))

    logger.info("Bot Telegram online. Aguardando mensagens...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # mantém rodando indefinidamente
    while True:
        await asyncio.sleep(3600)
