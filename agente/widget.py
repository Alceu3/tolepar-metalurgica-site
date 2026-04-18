"""
ARIA Widget - Barra compacta transparente fixada acima da taskbar do Windows.
Clique na barra para expandir/recolher o painel de chat.
"""
import sys, os, threading, time
import ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from PIL import Image, ImageTk

import brain, config, hearing, voice, memory, task_overlay, telegram_bot


_SINGLE_INSTANCE_MUTEX = None


def _garantir_instancia_unica():
    """Garante instância única; se outra já existe, simplesmente continua."""
    global _SINGLE_INSTANCE_MUTEX
    try:
        _SINGLE_INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\EVELYN_WIDGET_SINGLE_INSTANCE")
        err = ctypes.windll.kernel32.GetLastError()
        if err == 183:  # ERROR_ALREADY_EXISTS
            # Outro processo com widget já está vivo — não abre segundo
            return False
    except Exception:
        return True
    return True

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
BAR_H   = 68    # altura da barra compacta (dois andares)
PANEL_H = 520   # altura do painel expandido
TASKBAR = 48    # altura estimada da taskbar do Windows
FLOAT_GAP = 70  # distância extra acima da taskbar
ALPHA   = 0.80  # transparência global

# Limites de redimensionamento
MIN_W   = 220
MAX_W   = 900
MIN_PANEL_H = 150
MAX_PANEL_H = 900


class ARIAWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Evelyn")
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

        self._bar_w   = BAR_W
        self._panel_h = PANEL_H
        self.root.geometry(f"{self._bar_w}x{BAR_H}+{self._x}+{self._y}")
        self._fixar_na_barra()
        self.root.after(180, self._trazer_para_frente)

        self._build_bar()
        self._build_panel()
        self._init_avatar_video()

        self.root.after(120, self._focus_input)
        task_overlay.init(self.root)
        telegram_bot.set_local_message_hook(self._on_telegram_event)
        telegram_bot.start()
        if bool(getattr(config, "PANEL_START_EXPANDED", True)):
            self.root.after(450, self._expandir)
        nome = str(getattr(config, "USER_NAME", "") or "").strip()
        saudacao = f"Ola, {nome}! Estou pronta. Pode falar ou digitar." if nome else "Ola! Estou pronta. Pode falar ou digitar."
        self.root.after(300, lambda: self._carregar_historico(saudacao))
        # Liga o microfone automaticamente se estiver habilitado
        if config.MIC_ENABLED and hearing.MIC_AVAILABLE and getattr(config, "MIC_AUTO_START", False):
            self.root.after(600, self._toggle_mic)
        elif config.MIC_ENABLED and (not hearing.MIC_AVAILABLE):
            self.root.after(700, lambda: self._add("SISTEMA", "Microfone indisponivel no ambiente atual. Vou funcionar em modo texto."))

    # ------------------------------------------------------------------ UI

    def _build_bar(self):
        """Barra compacta: duas linhas — título em cima, entrada em baixo."""
        self.bar = tk.Frame(self.root, bg=SURFACE)
        self.bar.pack(fill="x", side="top")

        # ── Linha 1: logo + botões ──────────────────────────────
        row1 = tk.Frame(self.bar, bg=SURFACE)
        row1.pack(fill="x")

        self.lbl_logo = tk.Label(
            row1, text=" ◈ Evelyn", bg=SURFACE, fg=BLUE,
            font=("Segoe UI", 10, "bold"), cursor="hand2", padx=4,
        )
        self.lbl_logo.pack(side="left", padx=(4, 0))
        self.lbl_logo.bind("<ButtonPress-1>", self._logo_press)
        self.lbl_logo.bind("<B1-Motion>", self._on_drag)
        self.lbl_logo.bind("<ButtonRelease-1>", self._logo_release)

        # Botão fechar
        btn_fechar = tk.Button(
            row1, text="✕", bg=SURFACE, fg=MUTED,
            font=("Segoe UI", 9), bd=0, padx=6, cursor="hand2",
            activebackground=RED, activeforeground=TEXT,
            command=self.root.destroy,
        )
        btn_fechar.pack(side="right", fill="y")

        # Botão mic
        self.mic_btn = tk.Button(
            row1, text="🎤", bg=SURFACE, fg=MUTED,
            font=("Segoe UI", 9), bd=0, padx=6, cursor="hand2",
            activebackground="#21262d",
            command=self._toggle_mic,
        )
        self.mic_btn.pack(side="right", fill="y")

        # Arrastar pela linha 1
        row1.bind("<ButtonPress-1>", self._logo_press)
        row1.bind("<B1-Motion>", self._on_drag)
        row1.bind("<ButtonRelease-1>", self._logo_release)

        # ── Linha 2: campo de texto ─────────────────────────────
        row2 = tk.Frame(self.bar, bg=SURFACE)
        row2.pack(fill="x", padx=4, pady=(0, 4))

        self.entrada = tk.Entry(
            row2, bg=BG2, fg=TEXT, insertbackground=TEXT,
            font=("Segoe UI", 9), bd=0, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=BLUE,
        )
        self.entrada.pack(fill="x", ipady=4, padx=2)
        self.entrada.bind("<Return>", lambda e: self._enviar())
        self.entrada.bind("<Button-1>", lambda e: self._focus_input())

    def _build_panel(self):
        """Painel expansível com Text widget scrollável — seleção e cópia com mouse."""
        self.panel = tk.Frame(self.root, bg=BG, bd=0)

        # Mensagens armazenadas internamente
        self._chat_lines = []
        self._status_text = ""
        self._avatar_font = None

        # Label de status na parte inferior (separado do chat)
        self.lbl_status = tk.Label(
            self.panel, text="", bg=BG, fg=MUTED,
            font=("Segoe UI", 9, "italic"), anchor="w", padx=8,
        )
        self.lbl_status.pack(side="bottom", fill="x")

        # Linha do tempo da tarefa (acompanhamento ao vivo)
        self._task_steps = []
        self.lbl_timeline = tk.Label(
            self.panel,
            text="",
            bg="#111722",
            fg="#9ecbff",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            padx=8,
            pady=5,
        )
        self.lbl_timeline.pack(side="top", fill="x")

        # Text widget scrollável
        txt_frame = tk.Frame(self.panel, bg=BG)
        txt_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(txt_frame, bg=SURFACE, troughcolor=BG,
                                 activebackground=BORDER, bd=0, highlightthickness=0)
        scrollbar.pack(side="right", fill="y")

        self.chat_text = tk.Text(
            txt_frame,
            bg="#0b0f14", fg=TEXT,
            font=("Segoe UI", 10),
            bd=0, relief="flat",
            wrap="word",
            state="normal",
            cursor="xterm",
            selectbackground=BLUE,
            selectforeground="#0d1117",
            highlightthickness=0,
            yscrollcommand=scrollbar.set,
            padx=8, pady=6,
        )
        self.chat_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.chat_text.yview)

        # Bloqueia digitação acidental mas permite seleção, cópia e Delete
        def _bloquear_digitacao(e):
            if e.state & 0x4:  # Ctrl pressionado
                return
            if e.keysym in ("Delete", "BackSpace"):
                return
            if e.keysym in ("Up", "Down", "Left", "Right", "Home", "End",
                            "Prior", "Next"):
                return
            return "break"

        self.chat_text.bind("<Key>", _bloquear_digitacao)

        # Tags de cor por remetente
        self.chat_text.tag_config("you",  foreground="#64c8ff")
        self.chat_text.tag_config("aria", foreground="#82ff9e")
        self.chat_text.tag_config("sys",  foreground="#ffdc50")
        self.chat_text.tag_config("voz",  foreground="#c8b4ff")

        # Menu de contexto com botão direito
        self._ctx_menu = tk.Menu(self.panel, tearoff=0, bg=SURFACE, fg=TEXT,
                                  activebackground=BLUE, activeforeground="#0d1117",
                                  bd=0)
        self._ctx_menu.add_command(label="Copiar seleção",  command=self._copiar_selecao)
        self._ctx_menu.add_command(label="Copiar tudo",     command=self._copiar_tudo)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Excluir seleção", command=self._excluir_selecao)
        self._ctx_menu.add_command(label="Limpar tudo",     command=self._limpar_chat)
        self.chat_text.bind("<Button-3>", self._show_ctx_menu)

        # Campo de voz para compatibilidade interna (não exibido)
        self.entrada_voz = tk.Entry(self.panel, bg=BG2, fg=GREEN)

        # avatar_label mantido para compatibilidade (oculto)
        self.avatar_label = tk.Label(self.panel, bg="#0b0f14", bd=0)

        # Handle de redimensionamento (canto inferior direito)
        self._resize_grip = tk.Label(
            self.panel, text="⠿", bg=SURFACE, fg=MUTED,
            font=("Segoe UI", 8), cursor="size_nw_se", padx=2, pady=1,
        )
        self._resize_grip.place(relx=1.0, rely=1.0, x=-4, y=-4, anchor="se")
        self._resize_grip.bind("<ButtonPress-1>",   self._resize_start)
        self._resize_grip.bind("<B1-Motion>",       self._resize_drag)
        self._resize_grip.bind("<ButtonRelease-1>", self._resize_end)
        self._resize_grip.lift()

    def _init_avatar_video(self):
        self._avatar_cap = None
        self._avatar_job = None
        self._avatar_photo = None
        self._avatar_cv2 = None
        self._avatar_path = str(getattr(config, "AVATAR_VIDEO_PATH", "") or "").strip()
        self._avatar_enabled = bool(getattr(config, "AVATAR_ENABLED", True))
        self._avatar_fps = max(8, int(getattr(config, "AVATAR_FPS", 18) or 18))

        if not self._avatar_enabled:
            # Sem vídeo: mantém um loop leve para desenhar mensagens na interface.
            self._avatar_tick()
            return
        if not self._avatar_path or (not os.path.exists(self._avatar_path)):
            self._avatar_tick()
            return

        try:
            import cv2
            self._avatar_cv2 = cv2
            cap = cv2.VideoCapture(self._avatar_path)
            if not cap or (not cap.isOpened()):
                self._avatar_tick()
                return
            self._avatar_cap = cap
            self._avatar_tick()
        except Exception:
            self._avatar_tick()

    def _render_static_overlay(self):
        """Sem vídeo — o Text widget já mostra o chat. Apenas garante resize grip visível."""
        self._resize_grip.lift()

    def _render_avatar_placeholder(self, msg):
        pass  # substituído pelo Text widget

    def _fit_avatar_frame(self, frame_rgb):
        h, w = frame_rgb.shape[:2]
        pw = self.panel.winfo_width()
        ph = self.panel.winfo_height()
        target_w = max(280, pw if pw > 1 else self._bar_w)
        target_h = max(150, ph if ph > 1 else int(getattr(config, "AVATAR_HEIGHT", 180) or 180))

        # Crop central para manter enquadramento natural do avatar.
        src_ratio = w / max(1, h)
        dst_ratio = target_w / max(1, target_h)
        if src_ratio > dst_ratio:
            new_w = int(h * dst_ratio)
            x0 = max(0, (w - new_w) // 2)
            frame_rgb = frame_rgb[:, x0:x0 + new_w]
        else:
            new_h = int(w / max(0.001, dst_ratio))
            y0 = max(0, (h - new_h) // 2)
            frame_rgb = frame_rgb[y0:y0 + new_h, :]

        img = Image.fromarray(frame_rgb)
        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def _draw_chat_on_frame(self, img_pil):
        """Renderiza mensagens do chat e status diretamente sobre o frame do vídeo."""
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img_pil)
        W, H = img_pil.size

        # Carrega fonte na primeira chamada
        if self._avatar_font is None:
            for font_path in (
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "C:/Windows/Fonts/arial.ttf",
            ):
                try:
                    self._avatar_font = ImageFont.truetype(font_path, 14)
                    break
                except Exception:
                    pass
            if self._avatar_font is None:
                self._avatar_font = ImageFont.load_default()
        font = self._avatar_font

        tag_colors = {
            "you":  (100, 200, 255),   # azul claro — usuário
            "aria": (130, 255, 160),   # verde claro — Evelyn
            "sys":  (255, 220, 80),    # amarelo — sistema
            "voz":  (200, 180, 255),   # lilás — voz
        }
        margin_x = 10
        line_h = 22
        max_line_w = W - margin_x * 2

        def text_w(t):
            try:
                return font.getbbox(t)[2]
            except Exception:
                return len(t) * 8

        # Quebra de linha das mensagens armazenadas
        display_lines = []
        for (tag, quem, texto) in self._chat_lines:
            full = f"{quem}: {texto}"
            words = full.split(" ")
            current = ""
            for word in words:
                test = (current + " " + word).strip() if current else word
                if text_w(test) <= max_line_w:
                    current = test
                else:
                    if current:
                        display_lines.append((tag, current))
                    current = word
            if current:
                display_lines.append((tag, current))

        status_h = line_h if self._status_text else 0
        available_h = H - status_h - 15
        max_lines = max(1, available_h // line_h)
        visible = display_lines[-max_lines:]

        y_start = max(10, H - status_h - 10 - len(visible) * line_h)

        for i, (tag, line) in enumerate(visible):
            y = y_start + i * line_h
            color = tag_colors.get(tag, (255, 255, 255))
            draw.text((margin_x, y), line, font=font, fill=color)

        # Status na parte inferior
        if self._status_text:
            sy = H - status_h - 2
            draw.text((margin_x, sy), self._status_text, font=font, fill=(255, 255, 255))

        # Indicador de estado (ponto colorido no canto superior direito)
        dot_r = 5
        dx, dy = W - dot_r - 8, dot_r + 8
        if voice.is_speaking:
            draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=(63, 185, 80))
        elif self.mic_ativo:
            draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=(88, 166, 255))

        return img_pil

    def _avatar_tick(self):
        if not self._avatar_cap or not self._avatar_cv2:
            self._render_static_overlay()
            self._avatar_job = self.root.after(120, self._avatar_tick)
            return

        ok, frame = self._avatar_cap.read()
        if not ok:
            self._avatar_cap.set(self._avatar_cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._avatar_cap.read()
            if not ok:
                self._render_avatar_placeholder("Falha ao reproduzir avatar")
                return

        rgb = self._avatar_cv2.cvtColor(frame, self._avatar_cv2.COLOR_BGR2RGB)
        fitted = self._fit_avatar_frame(rgb)
        fitted = self._draw_chat_on_frame(fitted)
        self._avatar_photo = ImageTk.PhotoImage(fitted)
        self.avatar_label.configure(image=self._avatar_photo, text="", compound="center")

        self._resize_grip.lift()

        if voice.is_speaking:
            delay = max(25, int(1000 / (self._avatar_fps + 8)))
        elif self.mic_ativo:
            delay = max(35, int(1000 / self._avatar_fps))
        else:
            delay = max(45, int(1000 / (self._avatar_fps - 2)))

        self._avatar_job = self.root.after(delay, self._avatar_tick)

    # ------------------------------------------------------------------ lógica de layout

    def _expandir(self):
        if not self._expanded:
            self._toggle_panel()

    def _toggle_panel(self):
        if self._expanded:
            # Restaura à posição exata que tinha antes de abrir
            self._y = self._bar_y_before_expand
            self.panel.pack_forget()
            self.root.geometry(f"{self._bar_w}x{BAR_H}+{self._x}+{self._y}")
            self.root.update_idletasks()
            self._expanded = False
            self.lbl_logo.configure(text=" ◈ Evelyn")
        else:
            total_h = BAR_H + self._panel_h
            self._bar_y_before_expand = self._y  # salva posição atual da barra
            # Expande para cima; se não couber, expande para baixo
            new_y = self._y - self._panel_h
            if new_y < 0:
                new_y = self._y + BAR_H
            new_y = max(0, min(new_y, self._sh - total_h))
            self._y = new_y
            self.root.geometry(f"{self._bar_w}x{total_h}+{self._x}+{self._y}")
            self.panel.pack(fill="both", expand=True)
            self._expanded = True
            self.lbl_logo.configure(text=" ▾ Evelyn")
            self._focus_input()

    def _fixar_na_barra(self):
        """Recolhe (se preciso) e fixa no centro acima da barra de tarefas."""
        if self._expanded:
            self.panel.pack_forget()
            self._expanded = False
            self.lbl_logo.configure(text=" ◈ Evelyn")
        self._x = (self._sw - self._bar_w) // 2
        self._y = self._sh - BAR_H - TASKBAR - FLOAT_GAP
        self.root.geometry(f"{self._bar_w}x{BAR_H}+{self._x}+{self._y}")

    def _trazer_para_frente(self):
        """Garante que a janela fique visível e no topo ao abrir."""
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()

    # ------------------------------------------------------------------ resize
    def _resize_start(self, event):
        self._rx0 = event.x_root
        self._ry0 = event.y_root
        self._rw0 = self._bar_w
        self._rh0 = self._panel_h

    def _resize_drag(self, event):
        dw = event.x_root - self._rx0
        dh = event.y_root - self._ry0
        new_w = max(MIN_W, min(MAX_W, self._rw0 + dw))
        new_h = max(MIN_PANEL_H, min(MAX_PANEL_H, self._rh0 + dh))
        self._bar_w   = new_w
        self._panel_h = new_h
        total_h = BAR_H + new_h if self._expanded else BAR_H
        self.root.geometry(f"{new_w}x{total_h}+{self._x}+{self._y}")
        # força atualização visual do avatar ao redimensionar
        if self._avatar_cap and (self._avatar_job is None):
            self._avatar_tick()

    def _resize_end(self, event):
        # salva dimensões nos atributos (já atualizados no drag)
        pass

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
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        self._bar_w = w
        self.root.geometry(f"{w}x{h}+{self._x}+{self._y}")

    # ------------------------------------------------------------------ chat

    def _add(self, quem, texto):
        tag = {"Evelyn": "aria", "SISTEMA": "sys", "VOZ": "voz"}.get(quem, "you")
        self._chat_lines.append((tag, quem, texto))
        if len(self._chat_lines) > 200:
            self._chat_lines = self._chat_lines[-200:]
        # Insere no Text widget
        linha = f"{quem}: {texto}\n"
        self.chat_text.insert("end", linha, tag)
        self.chat_text.see("end")

    def _carregar_historico(self, saudacao):
        """Carrega as últimas mensagens salvas e exibe no chat antes da saudação."""
        try:
            hist = memory.get_history(max_messages=20)
            if hist:
                self._add("SISTEMA", "--- histórico anterior ---")
                for msg in hist:
                    quem = "Evelyn" if msg["role"] == "assistant" else (
                        str(getattr(config, "USER_NAME", "Você") or "Você"))
                    self._add(quem, msg["content"])
                self._add("SISTEMA", "--- nova sessão ---")
        except Exception:
            pass
        self._add("Evelyn", saudacao)

    def _set_status(self, msg):
        self._status_text = str(msg)
        self.lbl_status.config(text=str(msg))

    def _on_telegram_event(self, event_type, payload):
        """Espelha mensagens do Telegram no chat local e opcionalmente fala a resposta."""
        if not bool(getattr(config, "TELEGRAM_MIRROR_TO_LOCAL", True)):
            return

        payload = payload or {}
        chat_id = str(payload.get("chat_id", "") or "")
        text = str(payload.get("text", "") or "").strip()
        if not text:
            return

        if event_type == "incoming":
            self.root.after(0, lambda: self._add("Voce", f"[Telegram {chat_id}] {text}"))
            return

        if event_type == "outgoing":
            self.root.after(0, lambda: self._add("Evelyn", f"[Telegram] {text}"))
            if bool(getattr(config, "TELEGRAM_SPEAK_ON_LOCAL", True)) and bool(getattr(config, "VOICE_ENABLED", True)):
                threading.Thread(target=voice.falar, args=(text,), daemon=True).start()
            return

    def _resumo_resultado(self, txt, max_len=140):
        s = str(txt or "").replace("\n", " ").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 3] + "..."

    def _timeline_render(self):
        if not self._task_steps:
            self.lbl_timeline.config(text="")
            return
        ultimas = self._task_steps[-6:]
        linhas = [f"{i + 1}. {linha}" for i, linha in enumerate(ultimas)]
        self.lbl_timeline.config(text="\n".join(linhas))

    def _timeline_reset(self):
        self._task_steps = []
        self._timeline_render()

    def _timeline_add(self, texto):
        self._task_steps.append(str(texto))
        self._timeline_render()

    def _timeline_mark_last(self, prefix_from, prefix_to):
        for i in range(len(self._task_steps) - 1, -1, -1):
            line = self._task_steps[i]
            if line.startswith(prefix_from):
                self._task_steps[i] = prefix_to + line[len(prefix_from):]
                break
        self._timeline_render()

    def _on_brain_progress(self, event, data):
        data = data or {}
        label = str(data.get("label") or data.get("tool") or "etapa")
        resultado = self._resumo_resultado(data.get("result", ""))

        if event == "phase":
            msg = str(data.get("message") or "Planejando execução...")
            self.root.after(0, self._timeline_reset)
            self.root.after(0, lambda: self._timeline_add("🧠 Planejando execução"))
            self.root.after(0, lambda: self._set_status("🧠 " + msg))
            self.root.after(0, lambda: self._add("SISTEMA", "🧠 " + msg))
            return

        if event == "tool_start":
            self.root.after(0, lambda: self._timeline_add(f"⏳ {label}"))
            self.root.after(0, lambda: self._set_status(f"⏳ executando: {label}"))
            self.root.after(0, lambda: self._add("SISTEMA", f"▶ Executando: {label}"))
            return

        if event == "tool_success":
            texto = f"✅ {label} concluído"
            if resultado:
                texto += f" | {resultado}"
            self.root.after(0, lambda: self._timeline_mark_last("⏳ ", "✅ "))
            self.root.after(0, lambda: self._set_status(f"✅ {label} ok"))
            self.root.after(0, lambda: self._add("SISTEMA", texto))
            return

        if event == "tool_retry":
            texto = f"🔄 {label}: tentando corrigir e executar novamente"
            self.root.after(0, lambda: self._timeline_mark_last("⏳ ", "⚠ "))
            self.root.after(0, lambda: self._timeline_add(f"🔄 {label} (nova tentativa)"))
            self.root.after(0, lambda: self._set_status(f"🔄 corrigindo: {label}"))
            self.root.after(0, lambda: self._add("SISTEMA", texto))
            return

        if event == "tool_error":
            texto = f"❌ {label} falhou"
            if resultado:
                texto += f" | {resultado}"
            self.root.after(0, lambda: self._timeline_mark_last("⏳ ", "❌ "))
            self.root.after(0, lambda: self._set_status(f"❌ erro em: {label}"))
            self.root.after(0, lambda: self._add("SISTEMA", texto))
            return

        if event == "finished":
            ok = bool(data.get("success", False))
            final_msg = str(data.get("message") or ("Concluído." if ok else "Concluído com falhas."))
            if ok:
                self.root.after(0, lambda: self._timeline_add("🏁 Finalizado com sucesso"))
            else:
                self.root.after(0, lambda: self._timeline_add("🏁 Finalizado com pendências"))
            self.root.after(0, lambda: self._set_status(("✅ " if ok else "⚠ ") + final_msg))
            self.root.after(0, lambda: self._add("SISTEMA", ("✅ " if ok else "⚠ ") + final_msg))
            return

    def _limpar_chat(self):
        """Limpa todas as mensagens do chat."""
        self._chat_lines.clear()
        self._status_text = ""
        self.chat_text.delete("1.0", "end")

    def _copiar_selecao(self):
        try:
            texto = self.chat_text.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
        except Exception:
            pass

    def _copiar_tudo(self):
        texto = self.chat_text.get("1.0", "end")
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)

    def _excluir_selecao(self):
        try:
            self.chat_text.delete("sel.first", "sel.last")
        except Exception:
            pass

    def _show_ctx_menu(self, event):
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

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
        # Comando para parar a fala imediatamente
        _msg_norm = msg.lower().strip()
        _stop_words = ("para", "pare", "cala boca", "calar", "silencio", "shhh",
                       "chega", "pode parar", "para de falar", "para de fala",
                       "fica quieta", "fica quieto", "cala a boca", "stop")
        _voice_on_words = (
            "resposta em fala", "resposta em voz", "responder em fala", "responder em voz",
            "fala on", "audio on", "som on", "liga voz", "ligar voz", "ativa voz", "ativar voz",
            "liga a voz", "ativar a voz",
        )
        _voice_off_words = (
            "resposta em texto", "so texto", "só texto",
            "fala off", "audio off", "som off", "desliga voz", "desativar voz",
            "desliga a voz", "desativar a voz",
        )
        if any(_msg_norm == w or _msg_norm.startswith(w) for w in _stop_words):
            voice.parar()
            self.root.after(0, lambda: self._add("Evelyn", "Ok, parei."))
            self._set_status("")
            return
        if any(_msg_norm == w or _msg_norm.startswith(w) for w in _voice_on_words):
            config.VOICE_ENABLED = True
            self.root.after(0, lambda: self._add("Evelyn", "Voz ativada. Vou responder falando."))
            threading.Thread(target=voice.falar, args=("Voz ativada.",), daemon=True).start()
            self._set_status("")
            return
        if any(_msg_norm == w or _msg_norm.startswith(w) for w in _voice_off_words):
            config.VOICE_ENABLED = False
            voice.parar()
            self.root.after(0, lambda: self._add("Evelyn", "Voz desativada. Vou responder em texto."))
            self._set_status("")
            return

        self._set_status("pensando...")
        brain.set_progress_callback(task_overlay.get_callback())
        try:
            resp = brain.processar(msg)
        except Exception as ex:
            resp = f"[Erro: {ex}]"
        finally:
            brain.set_progress_callback(None)
            self._set_status("")

        # Comandos especiais de microfone — ligar/desligar sem exibir resposta bruta
        if resp == "__TOGGLE_MIC_ON__":
            self.root.after(0, lambda: self._add("Evelyn", "Microfone ativado! Pode falar."))
            self.root.after(0, lambda: (not self.mic_ativo) and self._toggle_mic())
            return
        if resp == "__TOGGLE_MIC_OFF__":
            self.root.after(0, lambda: self._add("Evelyn", "Microfone desativado."))
            self.root.after(0, lambda: self.mic_ativo and self._toggle_mic())
            return
        if resp == "__TOGGLE_VOICE_ON__":
            config.VOICE_ENABLED = True
            self.root.after(0, lambda: self._add("Evelyn", "Voz ativada. Vou responder falando."))
            threading.Thread(target=voice.falar, args=("Voz ativada.",), daemon=True).start()
            return
        if resp == "__TOGGLE_VOICE_OFF__":
            config.VOICE_ENABLED = False
            voice.parar()
            self.root.after(0, lambda: self._add("Evelyn", "Voz desativada. Vou responder em texto."))
            return

        self.root.after(0, lambda: self._add("Evelyn", resp))
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
        import time
        self._set_status("🎤 inicializando microfone...")
        # Sempre força nova detecção — evita usar índice obsoleto em cache
        hearing._cached_mic_idx[0] = None
        try:
            mic_idx = hearing._best_mic_index()
        except Exception:
            mic_idx = None
        if mic_idx is None:
            self.root.after(0, lambda: self._add("SISTEMA", "Microfone não encontrado."))
            self._set_status("")
            self.mic_ativo = False
            self.root.after(0, lambda: self.mic_btn.configure(fg=MUTED))
            return

        erros_seguidos = 0
        sem_audio_seguidos = 0
        while self.mic_ativo:
            try:
                self._set_status("🎤 fale agora...")

                if voice.is_speaking:
                    time.sleep(0.2)
                    continue

                result = hearing._capturar_audio(mic_idx, max_secs=10)

                if not self.mic_ativo:
                    break

                if result is None:
                    sem_audio_seguidos += 1
                    if sem_audio_seguidos == 8:
                        self._set_status(f"🎤 sem audio no device {mic_idx} (ajuste manual)")
                    erros_seguidos = 0
                    continue
                sem_audio_seguidos = 0

                self._set_status("📝 transcrevendo...")
                try:
                    pcm_bytes, sample_rate = result
                    texto = hearing._transcrever_whisper(pcm_bytes, sample_rate)
                except Exception as e:
                    print(f"[widget] Erro ao transcrever: {e}")
                    texto = None

                erros_seguidos = 0
                if texto:
                    def _tratar_voz(t=texto):
                        txt = (t or "").strip()
                        if not txt:
                            return

                        auto_send = bool(getattr(config, "MIC_AUTO_SEND", False))
                        require_wake = bool(getattr(config, "MIC_REQUIRE_WAKE_WORD", True))
                        wake_word = str(getattr(config, "MIC_WAKE_WORD", "evelyn") or "").strip().lower()

                        normalized = txt.lower().strip()
                        woke = (not require_wake) or (wake_word and normalized.startswith(wake_word))

                        # Proteção anti-voz fantasma: ignora qualquer ditado sem wake word.
                        if require_wake and (not woke):
                            self._set_status("🎤 áudio ignorado (diga 'Evelyn ...')")
                            return

                        # Remove palavra de ativação do começo antes de enviar/preencher
                        if wake_word and normalized.startswith(wake_word):
                            cleaned = txt[len(wake_word):].lstrip(" ,:;-.")
                        else:
                            cleaned = txt

                        if not cleaned.strip():
                            self._set_status("🎤 ouvi a ativação, diga o comando")
                            return

                        if auto_send and woke and cleaned.strip():
                            self._set_input_text(cleaned)
                            self._enviar()
                        else:
                            self._set_input_text(cleaned)
                            self._set_status("🎤 ditado capturado (pressione Enter para enviar)")

                    self.root.after(0, _tratar_voz)

            except Exception as e:
                erros_seguidos += 1
                print(f"[widget] Erro mic (#{erros_seguidos}): {e}")
                if erros_seguidos >= 5:
                    # Muitos erros seguidos — pausa de 3s e tenta de novo
                    self._set_status("⚠️ mic com falha, aguardando...")
                    time.sleep(3)
                    erros_seguidos = 0
                else:
                    time.sleep(0.5)

        self._set_status("")
        self.root.after(0, lambda: self.mic_btn.configure(fg=MUTED))

    def run(self):
        self._iniciar_tray()
        self.root.mainloop()
        try:
            self._tray_icon.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------ tray icon

    def _iniciar_tray(self):
        """Cria ícone na bandeja do sistema em thread separada."""
        try:
            import pystray
            from PIL import Image as PILImage, ImageDraw as PILDraw

            # Cria ícone 64x64 com círculo azul + letra E
            size = 64
            img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
            d = PILDraw.Draw(img)
            d.ellipse([4, 4, size - 4, size - 4], fill=(33, 38, 45, 220))
            d.ellipse([8, 8, size - 8, size - 8], fill=(13, 17, 23, 255))
            d.text((18, 14), "E", fill=(88, 166, 255, 255))

            def _mostrar(icon, item):
                self.root.after(0, self._trazer_para_frente)

            def _sair(icon, item):
                icon.stop()
                self.root.after(0, self.root.destroy)

            menu = pystray.Menu(
                pystray.MenuItem("Mostrar Evelyn", _mostrar, default=True),
                pystray.MenuItem("Sair", _sair),
            )
            self._tray_icon = pystray.Icon("evelyn", img, "Evelyn — Agente IA", menu)
            t = threading.Thread(target=self._tray_icon.run, daemon=True)
            t.start()
        except Exception as e:
            print(f"[tray] Aviso: {e}")



if __name__ == "__main__":
    if _garantir_instancia_unica():
        ARIAWidget().run()
