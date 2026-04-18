import time
import threading
import webbrowser

import pyautogui
import pyperclip
import config

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.35

# Controle de scroll contínuo
_scroll_continuo_flag = threading.Event()


def _safe_coords(x: int, y: int):
    """Normaliza coordenadas para a tela atual com fallback proporcional."""
    sw, sh = pyautogui.size()
    ix, iy = int(x), int(y)

    if ix < 0 or iy < 0 or ix >= sw or iy >= sh:
        rw = max(1, int(getattr(config, "REFERENCE_SCREEN_WIDTH", sw)))
        rh = max(1, int(getattr(config, "REFERENCE_SCREEN_HEIGHT", sh)))
        ix = int((max(0, min(ix, rw - 1)) / rw) * sw)
        iy = int((max(0, min(iy, rh - 1)) / rh) * sh)

    ix = max(0, min(ix, sw - 1))
    iy = max(0, min(iy, sh - 1))
    return ix, iy


# ── Visão espacial ────────────────────────────────────────

def tamanho_tela():
    w, h = pyautogui.size()
    return f"Resolução da tela: {w}x{h}"


def posicao_mouse():
    x, y = pyautogui.position()
    return f"Posição atual do mouse: ({x}, {y})"


# ── Mouse ─────────────────────────────────────────────────

def mover_mouse(x: int, y: int):
    sx, sy = _safe_coords(x, y)
    pyautogui.moveTo(sx, sy, duration=0.4)
    return f"Mouse movido para ({sx}, {sy})"


def clicar(x: int, y: int):
    sx, sy = _safe_coords(x, y)
    pyautogui.click(sx, sy)
    return f"Clique em ({sx}, {sy})"


def clicar_duplo(x: int, y: int):
    sx, sy = _safe_coords(x, y)
    pyautogui.doubleClick(sx, sy)
    return f"Duplo clique em ({sx}, {sy})"


def clicar_direito(x: int, y: int):
    sx, sy = _safe_coords(x, y)
    pyautogui.rightClick(sx, sy)
    return f"Clique direito em ({sx}, {sy})"


def scroll(quantidade: int):
    """Scroll único forte — rola bastante de uma vez."""
    sw, sh = pyautogui.size()
    pyautogui.moveTo(sw // 2, sh // 2, duration=0.1)
    pyautogui.click()
    time.sleep(0.2)
    ticks = int(quantidade) * 200
    pyautogui.scroll(ticks)
    direcao = "cima" if quantidade > 0 else "baixo"
    return f"Scroll para {direcao} ({abs(quantidade)})"


def scroll_continuo(direcao: str):
    """Inicia scroll contínuo até parar_scroll() ser chamado."""
    _scroll_continuo_flag.clear()
    sw, sh = pyautogui.size()
    pyautogui.moveTo(sw // 2, sh // 2, duration=0.1)
    pyautogui.click()
    ticks = -5 if direcao.lower() in ("baixo", "down") else 5

    def _loop():
        while not _scroll_continuo_flag.is_set():
            pyautogui.scroll(ticks)
            time.sleep(0.08)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return f"Rolando para {direcao} continuamente. Diga 'para' para parar."


def parar_scroll():
    """Para o scroll contínuo."""
    _scroll_continuo_flag.set()
    return "Scroll parado."


# ── Teclado ───────────────────────────────────────────────

def digitar(texto: str):
    """Cola o texto via clipboard — funciona com acentos e caracteres especiais."""
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")
    return f"Texto digitado: '{texto}'"


def pressionar_tecla(tecla: str):
    pyautogui.press(tecla)
    return f"Tecla pressionada: {tecla}"


def atalho(teclas: str):
    """Ex: 'ctrl+c', 'ctrl+v', 'alt+tab', 'ctrl+shift+t'"""
    keys = [k.strip() for k in teclas.lower().split("+")]
    pyautogui.hotkey(*keys)
    return f"Atalho executado: {teclas}"


# ── Navegador / Sistema ───────────────────────────────────

def abrir_site(url: str):
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    time.sleep(2.5)
    return f"Site aberto: {url}"
