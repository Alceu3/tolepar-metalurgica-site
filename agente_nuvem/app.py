"""
ARIA — Interface Web (Gradio)
Abre no navegador com:
  • Caixa de texto para digitar
  • Botão de microfone para falar
  • Toggle para ouvir resposta em áudio
  • Histórico visual da conversa
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
import brain
import voice
import config

# ── TTS para resposta em áudio ────────────────────────────
try:
    import pyttsx3
    _tts = pyttsx3.init()
    _tts.setProperty("rate", config.VOICE_RATE)
    for v in _tts.getProperty("voices"):
        if any(k in v.id.lower() for k in ("brazil", "pt_br", "portuguese")):
            _tts.setProperty("voice", v.id)
            break
    TTS_OK = True
except Exception:
    TTS_OK = False


def _resposta_audio(texto: str):
    """Gera arquivo de áudio temporário com a resposta."""
    if not TTS_OK:
        return None
    import wave, array
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        _tts.save_to_file(texto, tmp.name)
        _tts.runAndWait()
        if os.path.getsize(tmp.name) > 100:
            return tmp.name
    except Exception:
        pass
    return None


# ── Processamento de mensagem ─────────────────────────────

def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def processar_texto(mensagem: str, historico: list, audio_on: bool):
    if not mensagem or not mensagem.strip():
        return historico, None, ""

    resposta = brain.processar(mensagem.strip())
    historico = historico + [_msg("user", mensagem.strip()), _msg("assistant", resposta)]
    audio_path = _resposta_audio(resposta) if audio_on else None
    return historico, audio_path, ""


def processar_audio_mic(audio_file, historico: list, audio_on: bool):
    """Transcreve áudio do microfone e processa."""
    if audio_file is None:
        return historico, None

    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(audio_file) as source:
            audio = r.record(source)
        texto = r.recognize_google(audio, language="pt-BR")
    except Exception as e:
        texto = f"[Não consegui transcrever: {e}]"

    resposta = brain.processar(texto)
    historico = historico + [_msg("user", f"🎤 {texto}"), _msg("assistant", resposta)]
    audio_path = _resposta_audio(resposta) if audio_on else None
    return historico, audio_path


# ── Interface ─────────────────────────────────────────────

with gr.Blocks(title="ARIA — Agente IA Local") as app:

    gr.Markdown("# ARIA — Agente IA Autônomo Local")
    gr.Markdown(
        f"**Provedor:** `{getattr(config, 'PROVIDER', 'ollama').upper()}` &nbsp;|&nbsp; "
        f"**Modelo:** `{config.OLLAMA_MODEL}`"
    )

    chatbot = gr.Chatbot(elem_id="chatbox", label="Conversa", height=480)

    with gr.Row():
        audio_toggle = gr.Checkbox(
            label="🔊 Resposta em áudio",
            value=config.VOICE_ENABLED,
        )

    # ── Entrada de texto ──────────────────────────────────
    with gr.Row():
        txt_input = gr.Textbox(
            placeholder="Digite sua mensagem...",
            show_label=False,
            scale=8,
            container=False,
        )
        send_btn = gr.Button("Enviar", elem_id="send_btn", scale=1)

    audio_out = gr.Audio(label="Resposta em áudio", autoplay=True, visible=True)

    # ── Entrada de voz (microfone) ────────────────────────
    gr.Markdown("### 🎤 Ou fale com a ARIA")
    mic_input = gr.Audio(
        sources=["microphone"],
        type="filepath",
        label="Clique no microfone e fale",
    )
    mic_btn = gr.Button("Enviar áudio")

    # ── Eventos texto ─────────────────────────────────────
    send_btn.click(
        processar_texto,
        inputs=[txt_input, chatbot, audio_toggle],
        outputs=[chatbot, audio_out, txt_input],
    )
    txt_input.submit(
        processar_texto,
        inputs=[txt_input, chatbot, audio_toggle],
        outputs=[chatbot, audio_out, txt_input],
    )

    # ── Eventos voz ───────────────────────────────────────
    mic_btn.click(
        processar_audio_mic,
        inputs=[mic_input, chatbot, audio_toggle],
        outputs=[chatbot, audio_out],
    )


if __name__ == "__main__":
    print("Abrindo ARIA no navegador...")
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=True,
        share=False,
        theme=gr.themes.Soft(),
        css="#chatbox{height:480px;overflow-y:auto} footer{display:none!important}",
    )
