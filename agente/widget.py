"""
ARIA Widget - Barra compacta transparente fixada acima da taskbar do Windows.
Clique na barra para expandir/recolher o painel de chat.
"""
import sys, os, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import scrolledtext

import brain, config, hearing, voice

# Cores (tema escuro semi-transparente)
BG      = "#0d1117"
BG2     = "#161b22"
SURFACE = "#21262d"
BORDER  = "#30363d"
TEXT    = "#e6edf3"
BLUE    = "#58a6ff"
GREEN   = "#3fb950"
RED     = "#f85149"
YELLOW  = "#d29922"
MUTED   = "#8b949e"

# Dimensões
BAR_W   = 320   # largura da barra sempre visível
BAR_H   = 44    # altura da barra compacta
PANEL_H = 520   # altura do painel expandido
TASKBAR = 48    # altura estimada da taskbar do Windows
FLOAT_GAP = 70  # distância extra acima da taskbar
ALPHA   = 0.68  # transparência global


class ARIAWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ARIA")
        self.root.configure(bg=BG)
        self.root.wm_attributes("-topmost", True)
        self.root.overrideredirect(True)          # sem borda do SO
        self.root.attributes("-alpha", ALPHA)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self._sw = sw
        self._sh = sh

        # Posição inicial fixa: centro acima da taskbar
        self._x = (sw - BAR_W) // 2
        self._y = sh - BAR_H - TASKBAR - FLOAT_GAP
        self._expanded = False
        self._bar_y_before_expand = self._y
        self.mic_ativo = False
        self._dx = 0
        self._dy = 0

        self.root.geometry(f"{BAR_W}x{BAR_H}+{self._x}+{self._y}")
        self._fixar_na_barra()

        self._build_bar()
        self._build_panel()

        self.root.after(120, self._focus_input)
        nome = str(getattr(config, "USER_NAME", "") or "").strip()
        saudacao = f"Ola, {nome}! Estou pronta. Pode falar ou digitar." if nome else "Ola! Estou pronta. Pode falar ou digitar."
        self.root.after(300, lambda: self._add("ARIA", saudacao))
        # Liga o microfone automaticamente se estiver habilitado
        if config.MIC_ENABLED and hearing.MIC_AVAILABLE and getattr(config, "MIC_AUTO_START", False):
            self.root.after(600, self._toggle_mic)
        elif config.MIC_ENABLED and (not hearing.MIC_AVAILABLE):
            self.root.after(700, lambda: self._add("SISTEMA", "Microfone indisponivel no ambiente atual. Vou funcionar em modo texto."))

    # ------------------------------------------------------------------ UI

    def _build_bar(self):
        """Barra compacta: ARIA + campo de texto + mic."""
        self.bar = tk.Frame(self.root, bg=SURFACE, height=BAR_H)
        self.bar.pack(fill="x", side="top")
        self.bar.pack_propagate(False)

        # Logo / toggle + drag
        self.lbl_logo = tk.Label(
            self.bar, text=" ◈ ARIA", bg=SURFACE, fg=BLUE,
            font=("Segoe UI", 10, "bold"), cursor="hand2", padx=4,
        )
        self.lbl_logo.pack(side="left", padx=(4, 0))
        # Usa press+release para distinguir clique de arraste
        self.lbl_logo.bind("<ButtonPress-1>", self._logo_press)
        self.lbl_logo.bind("<B1-Motion>", self._on_drag)
        self.lbl_logo.bind("<ButtonRelease-1>", self._logo_release)

        # Botão mic
        self.mic_btn = tk.Button(
            self.bar, text="🎤", bg=SURFACE, fg=MUTED,
            font=("Segoe UI", 10), bd=0, padx=6, cursor="hand2",
            activebackground="#21262d",
            command=self._toggle_mic,
        )
        self.mic_btn.pack(side="right", fill="y")

        # Campo de texto no cabeçalho
        entry_wrap = tk.Frame(self.bar, bg=BG, padx=2, pady=2)
        entry_wrap.pack(side="left", fill="both", expand=True, padx=(6, 4), pady=4)

        self.entrada = tk.Entry(
            entry_wrap, bg=BG2, fg=TEXT, insertbackground=TEXT,
            font=("Segoe UI", 9), bd=0, relief="flat",
            highlightthickness=0,
        )
        self.entrada.pack(fill="both", expand=True, ipady=4, padx=4)
        self.entrada.bind("<Return>", lambda e: self._enviar())
        self.entrada.bind("<Button-1>", lambda e: self._focus_input())

        # Arrastar apenas com drag na parte vazia da barra (logo)
        # (bindings já definidos no lbl_logo acima)

    def _build_panel(self):
        """Painel expansível com histórico, status e caixa de texto."""
        self.panel = tk.Frame(self.root, bg=BG, bd=0)
        # não empacotado ainda (recolhido por padrão)

        self.chat = scrolledtext.ScrolledText(
            self.panel, bg=BG2, fg=TEXT, font=("Consolas", 8),
            wrap=tk.WORD, bd=0, relief="flat",
            insertbackground=TEXT, state="disabled",
            selectbackground=SURFACE,
        )
        self.chat.pack(fill="both", expand=True, padx=6, pady=(6, 4))
        self.chat.tag_config("you",  foreground=BLUE)
        self.chat.tag_config("aria", foreground=GREEN)
        self.chat.tag_config("sys",  foreground=YELLOW)
        self.chat.tag_config("voz",  foreground=RED)

        self.lbl_status = tk.Label(
            self.panel,
            text="",
            bg=BG,
            fg=YELLOW,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.lbl_status.pack(fill="x", padx=8, pady=(0, 4))

        # Campo de voz apenas para compatibilidade interna (não exibido)
        self.entrada_voz = tk.Entry(self.panel, bg=BG2, fg=GREEN)

    # ------------------------------------------------------------------ lógica de layout

    def _expandir(self):
        if not self._expanded:
            self._toggle_panel()

    def _toggle_panel(self):
        if self._expanded:
            # Restaura à posição exata que tinha antes de abrir
            self._y = self._bar_y_before_expand
            self.panel.pack_forget()
            self.root.geometry(f"{BAR_W}x{BAR_H}+{self._x}+{self._y}")
            self.root.update_idletasks()
            self._expanded = False
            self.lbl_logo.configure(text=" ◈ ARIA")
        else:
            total_h = BAR_H + PANEL_H
            self._bar_y_before_expand = self._y  # salva posição atual da barra
            # Expande para cima; se não couber, expande para baixo
            new_y = self._y - PANEL_H
            if new_y < 0:
                new_y = self._y + BAR_H
            new_y = max(0, min(new_y, self._sh - total_h))
            self._y = new_y
            self.root.geometry(f"{BAR_W}x{total_h}+{self._x}+{self._y}")
            self.panel.pack(fill="both", expand=True)
            self._expanded = True
            self.lbl_logo.configure(text=" ▾ ARIA")
            self.chat.see("end")
            self._focus_input()

    def _fixar_na_barra(self):
        """Recolhe (se preciso) e fixa no centro acima da barra de tarefas."""
        if self._expanded:
            self.panel.pack_forget()
            self._expanded = False
            self.lbl_logo.configure(text=" ◈ ARIA")
        self._x = (self._sw - BAR_W) // 2
        self._y = self._sh - BAR_H - TASKBAR - FLOAT_GAP
        self.root.geometry(f"{BAR_W}x{BAR_H}+{self._x}+{self._y}")

    # ------------------------------------------------------------------ drag
    def _logo_press(self, event):
        self._drag_moved = False
        self._start_drag(event)

    def _logo_release(self, event):
        if not self._drag_moved:
            self._toggle_panel()

    def _start_drag(self, event):
        self._dx = event.x_root - self._x
        self._dy = event.y_root - self._y

    def _on_drag(self, event):
        self._drag_moved = True
        self._x = max(0, event.x_root - self._dx)
        self._y = max(0, event.y_root - self._dy)
        largura = self.root.winfo_width()
        altura = self.root.winfo_height()
        self.root.geometry(f"{largura}x{altura}+{self._x}+{self._y}")

    # ------------------------------------------------------------------ chat

    def _add(self, quem, texto):
        self.chat.configure(state="normal")
        tag = {"ARIA": "aria", "SISTEMA": "sys", "VOZ": "voz"}.get(quem, "you")
        self.chat.insert("end", f"{quem}: ", tag)
        self.chat.insert("end", f"{texto}\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _set_status(self, msg):
        self.root.after(0, lambda: self.lbl_status.configure(text=msg))

    def _focus_input(self):
        self.root.focus_force()
        self.entrada.focus_force()
        self.entrada.icursor(tk.END)

    def _focus_dictation(self):
        self.root.focus_force()
        self.entrada.focus_force()
        self.entrada.icursor(tk.END)

    def _set_input_text(self, texto):
        self.entrada.delete(0, tk.END)
        self.entrada.insert(0, texto)

    def _set_dictation_text(self, texto):
        self.entrada.delete(0, tk.END)
        self.entrada.insert(0, texto)

    def _usar_ditado(self):
        ditado = self.entrada_voz.get().strip()
        if not ditado or ditado.lower().startswith("ditado do microfone"):
            return
        self._set_input_text(ditado)
        self._focus_input()

    def _ditado_na_entrada(self, texto):
        novo = texto.strip()
        if not novo:
            return
        self._set_input_text(novo)
        self._set_status("🎤 ditado capturado — pressione Enter para enviar")
        self._focus_input()

    def _enviar(self):
        msg = self.entrada.get().strip()
        if not msg:
            ditado = self.entrada_voz.get().strip()
            if ditado and not ditado.lower().startswith("ditado do microfone"):
                msg = ditado
        if not msg:
            return
        self.entrada.delete(0, tk.END)
        self._add("Voce", msg)
        threading.Thread(target=self._processar, args=(msg,), daemon=True).start()

    def _processar(self, msg):
        self._set_status("pensando...")
        try:
            resp = brain.processar(msg)
        except Exception as ex:
            resp = f"[Erro: {ex}]"
        self._set_status("")
        self.root.after(0, lambda: self._add("ARIA", resp))
        if config.VOICE_ENABLED:
            threading.Thread(target=voice.falar, args=(resp,), daemon=True).start()

    # ------------------------------------------------------------------ mic

    def _toggle_mic(self):
        if self.mic_ativo:
            self.mic_ativo = False
            self.mic_btn.configure(fg=MUTED)
            self._set_status("")
        else:
            self.mic_ativo = True
            self.mic_btn.configure(fg=RED)
            threading.Thread(target=self._ouvir_loop, daemon=True).start()

    def _ouvir_loop(self):
        try:
            while self.mic_ativo:
                self._set_status("🎤 ouvindo (5s)...")
                try:
                    texto = hearing.ouvir(timeout=2, phrase_time_limit=8)
                except Exception as e:
                    print(f"[widget] Erro ao ouvir: {e}")
                    self._set_status(f"❌ Erro mic: {e}")
                    texto = None
                
                if not self.mic_ativo:
                    break
                if texto:
                    def _enviar_voz(t=texto):
                        self._set_input_text(t)
                        self._enviar()
                    self.root.after(0, _enviar_voz)
                else:
                    self._set_status("🎤 ouvindo (5s)... fale ALTO")
        except Exception as e:
            print(f"[widget] Erro na thread mic: {e}")
        finally:
            self._set_status("")
            self.root.after(0, lambda: self.mic_btn.configure(fg=MUTED))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ARIAWidget().run()
