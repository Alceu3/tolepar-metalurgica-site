"""
Painel de tarefas permanente — mesmo estilo visual da Evelyn.
Transparente, sem borda do SO, arrastável, redimensionável.
Aba "Ao vivo": progresso da tarefa atual.
Aba "Histórico": todas as execuções salvas em disco (data/task_history.json).
"""
import tkinter as tk
import json
import os
from datetime import datetime

# ── Paleta ──────────────────────────────────────────────────────────────
_BG      = "#0d1117"
_BG2     = "#161b22"
_SURFACE = "#21262d"
_BORDER  = "#30363d"
_TEXT    = "#e6edf3"
_BLUE    = "#58a6ff"
_GREEN   = "#3fb950"
_RED     = "#f85149"
_YELLOW  = "#d29922"
_MUTED   = "#8b949e"
_ALPHA   = 0.88

_ICON_COLORS = {
    "\U0001f9e0": _BLUE,
    "\u23f3": _YELLOW,
    "\u2705": _GREEN,
    "\u274c": _RED,
    "\U0001f504": _YELLOW,
    "\u26a0":  _YELLOW,
    "\U0001f3c1": _GREEN,
}

_DEFAULT_W = 320
_DEFAULT_H = 300
_MIN_W     = 220
_MIN_H     = 140
_MAX_W     = 800
_MAX_H     = 700

_HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "task_history.json"
)


def _load_history():
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(runs):
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(runs[-200:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _make_scrollable(parent, bg=None):
    if bg is None:
        bg = "#0d1117"
    outer = tk.Frame(parent, bg=bg)
    sb = tk.Scrollbar(outer, bg="#21262d", troughcolor=bg,
                      activebackground="#30363d", bd=0, highlightthickness=0, width=8)
    sb.pack(side="right", fill="y")
    canvas = tk.Canvas(outer, bg=bg, bd=0, highlightthickness=0,
                       yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.config(command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg)
    cwin  = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_frame(e):
        canvas.configure(scrollregion=canvas.bbox("all"))
    def _on_canvas(e):
        canvas.itemconfig(cwin, width=e.width)
    def _on_wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    inner.bind("<Configure>", _on_frame)
    canvas.bind("<Configure>", _on_canvas)
    canvas.bind("<MouseWheel>", _on_wheel)
    inner.bind("<MouseWheel>", _on_wheel)
    return outer, inner, canvas


class TaskOverlay:
    def __init__(self, root_tk):
        self._root = root_tk
        self._wx   = None
        self._wy   = None
        self._ww   = _DEFAULT_W
        self._wh   = _DEFAULT_H
        self._dx   = self._dy = 0
        self._rx0  = self._ry0 = 0
        self._rw0  = _DEFAULT_W
        self._rh0  = _DEFAULT_H
        self._live_steps  = []
        self._live_labels = []
        self._live_canvas = None
        self._live_frame  = None
        self._hist_canvas = None
        self._hist_frame  = None
        self._tab = "live"
        self._current_run = None
        self._collapsed   = False
        self._drag_moved  = False
        self._tab_bar_ref = None
        self._build()

    def _build(self):
        sw = self._root.winfo_screenwidth()
        if self._wx is None:
            self._wx = sw - _DEFAULT_W - 16
            self._wy = 40
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", _ALPHA)
        win.configure(bg=_BG)
        win.geometry(f"{self._ww}x{self._wh}+{self._wx}+{self._wy}")
        win.protocol("WM_DELETE_WINDOW", lambda: None)
        self._win = win

        hdr = tk.Frame(win, bg=_SURFACE, height=30)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        lbl_title = tk.Label(
            hdr, text="  \u25c8 Evelyn  \u2014  tarefas",
            bg=_SURFACE, fg=_BLUE,
            font=("Segoe UI", 9, "bold"), anchor="w", cursor="fleur",
        )
        lbl_title.pack(side="left", fill="both", expand=True)
        for w in (hdr, lbl_title):
            w.bind("<ButtonPress-1>",   self._drag_start)
            w.bind("<B1-Motion>",       self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        tab_bar = tk.Frame(win, bg=_BG2, height=26)
        tab_bar.pack(fill="x")
        self._tab_bar_ref = tab_bar
        tab_bar.pack_propagate(False)
        self._btn_live = tk.Button(
            tab_bar, text="\u25cf Ao vivo", bd=0,
            bg=_SURFACE, fg=_BLUE,
            font=("Segoe UI", 8, "bold"), cursor="hand2",
            activebackground=_BG, activeforeground=_TEXT,
            command=lambda: self._switch_tab("live"),
        )
        self._btn_live.pack(side="left", fill="y", ipadx=8)
        self._btn_hist = tk.Button(
            tab_bar, text="\U0001f4cb Hist\u00f3rico", bd=0,
            bg=_BG2, fg=_MUTED,
            font=("Segoe UI", 8), cursor="hand2",
            activebackground=_BG, activeforeground=_TEXT,
            command=lambda: self._switch_tab("hist"),
        )
        self._btn_hist.pack(side="left", fill="y", ipadx=8)

        self._content = tk.Frame(win, bg=_BG)
        self._content.pack(fill="both", expand=True)

        self._build_live_panel()
        self._build_hist_panel()
        self._switch_tab("live")

        grip = tk.Label(
            win, text="\u28ff", bg=_SURFACE, fg=_MUTED,
            font=("Segoe UI", 8), cursor="size_nw_se", padx=2, pady=1,
        )
        grip.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor="se")
        grip.bind("<ButtonPress-1>", self._resize_start)
        grip.bind("<B1-Motion>",     self._resize_drag)
        grip.lift()

    def _build_live_panel(self):
        self._live_panel, inner, canvas = _make_scrollable(self._content)
        self._live_frame  = inner
        self._live_canvas = canvas
        tk.Label(
            inner, text="Nenhuma tarefa em andamento.",
            bg=_BG, fg=_MUTED, font=("Segoe UI", 9),
            padx=8, pady=6, anchor="w",
        ).pack(fill="x")

    def _build_hist_panel(self):
        self._hist_panel, inner, canvas = _make_scrollable(self._content)
        self._hist_frame  = inner
        self._hist_canvas = canvas

    def _switch_tab(self, tab):
        self._tab = tab
        if tab == "live":
            self._hist_panel.pack_forget()
            self._live_panel.pack(fill="both", expand=True)
            self._btn_live.config(bg=_SURFACE, fg=_BLUE, font=("Segoe UI", 8, "bold"))
            self._btn_hist.config(bg=_BG2,     fg=_MUTED, font=("Segoe UI", 8))
        else:
            self._live_panel.pack_forget()
            self._hist_panel.pack(fill="both", expand=True)
            self._btn_hist.config(bg=_SURFACE, fg=_BLUE, font=("Segoe UI", 8, "bold"))
            self._btn_live.config(bg=_BG2,     fg=_MUTED, font=("Segoe UI", 8))
            self._refresh_hist()

    def _drag_start(self, e):
        self._dx = e.x_root - self._wx
        self._dy = e.y_root - self._wy
        self._drag_moved = False

    def _drag_move(self, e):
        self._drag_moved = True
        self._wx = e.x_root - self._dx
        self._wy = e.y_root - self._dy
        if self._win.winfo_exists():
            h = 30 if self._collapsed else self._wh
            self._win.geometry(f"{self._ww}x{h}+{self._wx}+{self._wy}")

    def _drag_end(self, e):
        if not self._drag_moved:
            self._toggle_collapse()

    def _toggle_collapse(self):
        if not self._win or not self._win.winfo_exists():
            return
        self._collapsed = not self._collapsed
        if self._collapsed:
            # esconde abas e conteúdo
            if self._tab_bar_ref:
                self._tab_bar_ref.pack_forget()
            self._content.pack_forget()
            self._win.geometry(f"{self._ww}x30+{self._wx}+{self._wy}")
        else:
            # reexibe abas e conteúdo
            if self._tab_bar_ref:
                self._tab_bar_ref.pack(fill="x")
            self._content.pack(fill="both", expand=True)
            self._win.geometry(f"{self._ww}x{self._wh}+{self._wx}+{self._wy}")

    def _resize_start(self, e):
        self._rx0 = e.x_root
        self._ry0 = e.y_root
        self._rw0 = self._ww
        self._rh0 = self._wh

    def _resize_drag(self, e):
        self._ww = max(_MIN_W, min(_MAX_W, self._rw0 + e.x_root - self._rx0))
        self._wh = max(_MIN_H, min(_MAX_H, self._rh0 + e.y_root - self._ry0))
        if self._win.winfo_exists():
            self._win.geometry(f"{self._ww}x{self._wh}+{self._wx}+{self._wy}")

    def on_progress(self, event, data):
        data   = data or {}
        label  = str(data.get("label") or data.get("tool") or "")
        result = str(data.get("result") or "")[:100].replace("\n", " ")
        ok     = bool(data.get("success", False))
        if event == "phase":
            self._root.after(0, self._start_run)
        elif event == "tool_start":
            self._root.after(0, lambda: self._live_add(f"\u23f3 {label}"))
        elif event == "tool_success":
            extra = f"  \u2192  {result}" if result else ""
            self._root.after(0, lambda: self._live_mark("\u23f3", f"\u2705 {label}{extra}"))
        elif event == "tool_retry":
            self._root.after(0, lambda: self._live_mark("\u23f3", f"\U0001f504 {label}  (corrigindo...)"))
        elif event == "tool_error":
            extra = f"  \u2192  {result}" if result else ""
            self._root.after(0, lambda: self._live_mark("\u23f3", f"\u274c {label}{extra}"))
        elif event == "finished":
            msg = f"\U0001f3c1 {'Conclu\u00eddo!' if ok else 'Finalizado com pend\u00eancias.'}"
            self._root.after(0, lambda: self._finish_run(msg, ok))

    def _start_run(self):
        self._live_steps  = []
        self._live_labels = []
        if self._live_frame:
            for w in self._live_frame.winfo_children():
                w.destroy()
        self._current_run = {
            "ts":    datetime.now().strftime("%d/%m/%Y %H:%M"),
            "steps": [],
            "ok":    False,
        }
        if self._tab != "live":
            self._switch_tab("live")
        self._live_add("\U0001f9e0 Planejando execu\u00e7\u00e3o")

    def _live_add(self, texto):
        if not self._live_frame:
            return
        idx = len(self._live_steps)
        self._live_steps.append(texto)
        if self._current_run:
            self._current_run["steps"].append(texto)
        cor = _TEXT
        for icon, c in _ICON_COLORS.items():
            if texto.startswith(icon):
                cor = c
                break
        lbl = tk.Label(
            self._live_frame,
            text=f"{idx + 1}. {texto}",
            bg=_BG, fg=cor,
            font=("Segoe UI", 9),
            anchor="w", justify="left",
            wraplength=self._ww - 30,
            padx=8, pady=2,
        )
        lbl.pack(fill="x")
        self._live_labels.append(lbl)
        if self._live_canvas:
            self._live_canvas.after(40, lambda: self._live_canvas.yview_moveto(1.0))

    def _live_mark(self, starts, novo):
        for i in range(len(self._live_steps) - 1, -1, -1):
            if self._live_steps[i].startswith(starts):
                self._live_steps[i] = novo
                if self._current_run:
                    try:
                        self._current_run["steps"][i] = novo
                    except IndexError:
                        pass
                if i < len(self._live_labels):
                    cor = _TEXT
                    for icon, c in _ICON_COLORS.items():
                        if novo.startswith(icon):
                            cor = c
                            break
                    self._live_labels[i].config(text=f"{i + 1}. {novo}", fg=cor)
                return
        self._live_add(novo)

    def _finish_run(self, msg, ok):
        self._live_add(msg)
        if self._current_run:
            self._current_run["ok"]    = ok
            self._current_run["steps"] = list(self._live_steps)
            runs = _load_history()
            runs.append(self._current_run)
            _save_history(runs)
            self._current_run = None

    def _refresh_hist(self):
        if not self._hist_frame:
            return
        for w in self._hist_frame.winfo_children():
            w.destroy()
        runs = _load_history()
        if not runs:
            tk.Label(
                self._hist_frame,
                text="Nenhuma tarefa registrada ainda.",
                bg=_BG, fg=_MUTED, font=("Segoe UI", 9),
                padx=8, pady=8, anchor="w",
            ).pack(fill="x")
            return
        for run in reversed(runs):
            ts    = run.get("ts", "")
            ok    = run.get("ok", False)
            ico   = "\u2705" if ok else "\u26a0"
            cor   = _GREEN if ok else _YELLOW
            steps = run.get("steps", [])
            card  = tk.Frame(self._hist_frame, bg=_SURFACE, pady=4)
            card.pack(fill="x", padx=6, pady=3)
            hdr = tk.Frame(card, bg=_SURFACE)
            hdr.pack(fill="x", padx=6)
            lbl_ts = tk.Label(
                hdr, text=f"{ico}  {ts}",
                bg=_SURFACE, fg=cor,
                font=("Segoe UI", 9, "bold"), anchor="w", cursor="hand2",
            )
            lbl_ts.pack(side="left")
            lbl_count = tk.Label(
                hdr, text=f"{len(steps)} passos",
                bg=_SURFACE, fg=_MUTED,
                font=("Segoe UI", 8), anchor="e",
            )
            lbl_count.pack(side="right")
            detail  = tk.Frame(card, bg=_BG2)
            expanded = [False]
            def _toggle(d=detail, e=expanded):
                if e[0]:
                    d.pack_forget()
                    e[0] = False
                else:
                    d.pack(fill="x", padx=6, pady=2)
                    e[0] = True
            for w in (hdr, lbl_ts, lbl_count):
                w.bind("<Button-1>", lambda _e, t=_toggle: t())
            for step in steps:
                cor_s = _TEXT
                for icon, c in _ICON_COLORS.items():
                    if step.startswith(icon):
                        cor_s = c
                        break
                tk.Label(
                    detail, text=f"  {step}",
                    bg=_BG2, fg=cor_s,
                    font=("Segoe UI", 8),
                    anchor="w", justify="left",
                    wraplength=self._ww - 40,
                    padx=4, pady=1,
                ).pack(fill="x")
        if self._hist_canvas:
            self._hist_canvas.after(40, lambda: self._hist_canvas.yview_moveto(0.0))


_overlay = None


def init(root_tk):
    global _overlay
    # destrói instância anterior se existir (evita duplicação)
    if _overlay is not None:
        try:
            _overlay._win.destroy()
        except Exception:
            pass
    _overlay = TaskOverlay(root_tk)


def get_callback():
    if _overlay:
        return _overlay.on_progress
    return None
