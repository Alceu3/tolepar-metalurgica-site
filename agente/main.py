#!/usr/bin/env python3
"""
ARIA — Agente de IA Autônomo Local
  👁️  Visão   → vê a tela em tempo real
  🖐️  Mãos    → controla mouse e teclado
  👂  Ouvido  → reconhece sua voz (requer pyaudio)
  🔊  Fala    → responde em voz (pyttsx3)
  🧠  Cérebro → OpenRouter (modelo configurável)

Como rodar:
  cd agente
  python main.py          → modo texto + microfone opcional
  python main.py --voz    → modo voz contínuo
"""

import os
import sys

# Garante imports do próprio diretório
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import brain
import voice
import hearing
import memory
import hands


BANNER = f"""
╔══════════════════════════════════════════╗
║   {config.AGENT_NAME} — Agente IA Autônomo Local          ║
║   Provedor: {str(getattr(config, 'PROVIDER', 'openrouter')).upper():<29}║
║   Modelo: {((config.OLLAMA_MODEL if str(getattr(config, 'PROVIDER', 'openrouter')).lower() == 'ollama' else config.MODEL)[:38]):<38}
║   Voz: {'✅' if config.VOICE_ENABLED else '❌'}  |  Mic: {'✅' if config.MIC_ENABLED else '❌'}              ║
╠══════════════════════════════════════════╣
║  Comandos especiais:                     ║
║    'limpar'  → apaga histórico           ║
║    'tarefas' → lista tarefas             ║
║    'clientes'→ lista clientes            ║
║    'autoteste'→ verifica ambiente         ║
║    'modo texto|voz|hibrido'              ║
║    'audio on|off'                        ║
║    'CONFIRMO: ...' para ação crítica     ║
║    'sair'    → encerra                   ║
╚══════════════════════════════════════════╝
"""

COMANDOS_ESPECIAIS = {
    "limpar":   lambda: memory.clear_history(),
    "tarefas":  lambda: memory.listar_tarefas(),
    "clientes": lambda: memory.listar_clientes(),
}


def _normalizar_modo(modo: str) -> str:
    m = (modo or "").strip().lower()
    if m in ("texto", "voz", "hibrido", "híbrido"):
        return "hibrido" if m == "híbrido" else m
    return "hibrido"


def _autoteste() -> str:
    linhas = []
    try:
        linhas.append(hands.tamanho_tela())
        linhas.append("Mouse e teclado: OK")
    except Exception as e:
        linhas.append(f"Hands: falha ({e})")

    try:
        import vision
        _ = vision.capturar_base64()
        linhas.append("Visao (captura de tela): OK")
    except Exception as e:
        linhas.append(f"Visao: falha ({e})")

    return "\n".join(linhas)


def _obter_entrada(modo: str) -> str | None:
    """Obtém entrada por texto ou microfone."""
    if modo == "texto":
        return input("Você (texto): ").strip() or None

    if modo == "voz":
        if not config.MIC_ENABLED:
            print("Microfone desativado. Troque para 'modo texto' ou ative MIC_ENABLED.")
            return None
        return hearing.ouvir(timeout=20)

    # Modo híbrido: digita ou usa Enter para falar.
    if config.MIC_ENABLED:
        linha = input("Você (Enter = microfone): ").strip()
        if not linha:
            return hearing.ouvir()
        return linha

    return input("Você: ").strip() or None


def modo_texto():
    modo_entrada = _normalizar_modo(getattr(config, "INTERACTION_MODE", "hibrido"))
    audio_ligado = bool(config.VOICE_ENABLED)

    print(BANNER)
    voice.falar(
        f"Olá! Sou o {config.AGENT_NAME}. Modo atual: {modo_entrada}. Como posso ajudar?",
        silent=not audio_ligado,
    )

    while True:
        try:
            entrada = _obter_entrada(modo_entrada)
            if not entrada:
                continue

            cmd = entrada.lower().strip()

            if cmd in ("modo texto", "modo voz", "modo hibrido", "modo híbrido"):
                alvo = cmd.replace("modo", "").strip()
                modo_entrada = _normalizar_modo(alvo)
                voice.falar(f"Modo alterado para {modo_entrada}.", silent=not audio_ligado)
                continue

            if cmd in ("audio on", "audio ligar", "som on"):
                audio_ligado = True
                voice.falar("Resposta em áudio ativada.", silent=False)
                continue

            if cmd in ("audio off", "audio desligar", "som off"):
                audio_ligado = False
                print("Resposta em áudio desativada.")
                continue

            if cmd in ("sair", "exit", "quit", "encerrar"):
                voice.falar("Até logo! Foi um prazer trabalhar com você.",
                            silent=not audio_ligado)
                break

            if cmd in COMANDOS_ESPECIAIS:
                resultado = COMANDOS_ESPECIAIS[cmd]()
                print(resultado)
                continue

            if cmd == "autoteste":
                print(_autoteste())
                continue

            print("⏳ Processando...", end="\r", flush=True)
            resposta = brain.processar(entrada)
            print(" " * 30, end="\r")  # limpa linha
            voice.falar(resposta, silent=not audio_ligado)

        except KeyboardInterrupt:
            print("\n")
            voice.falar("Interrompido. Até logo!", silent=not audio_ligado)
            break
        except Exception as e:
            print(f"\n[ERRO] {e}")
            import traceback; traceback.print_exc()


def modo_voz():
    """Loop totalmente por voz."""
    voice.falar("Modo de voz ativado. Pode falar!")

    while True:
        try:
            entrada = hearing.ouvir(timeout=20)
            if not entrada:
                continue

            if any(p in entrada.lower() for p in ("encerrar", "desligar", "pare", "sair")):
                voice.falar("Encerrando. Até logo!")
                break

            resposta = brain.processar(entrada)
            voice.falar(resposta)

        except KeyboardInterrupt:
            voice.falar("Até logo!")
            break


if __name__ == "__main__":
    if "--voz" in sys.argv:
        modo_voz()
    else:
        modo_texto()
