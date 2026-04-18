import json
import os
import re
import time as _time
from html import unescape
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import vision
import hands
import memory


def _pesquisar_web(query: str) -> str:
    """Pesquisa na internet e retorna resumo dos resultados.

    1) Tenta API duckduckgo_search (DDGS)
    2) Fallback para endpoint HTML do DuckDuckGo
    """
    query = (query or "").strip()
    if not query:
        return "Informe o tema da pesquisa."

    # 1) Caminho principal: pacote duckduckgo_search
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=4))
        if resultados:
            linhas = []
            for r in resultados[:4]:
                titulo = (r.get("title") or "").strip()
                corpo = (r.get("body") or "").strip()[:220]
                if titulo or corpo:
                    linhas.append(f"• {titulo}: {corpo}".strip())
            if linhas:
                return "\n".join(linhas)
    except Exception:
        pass

    # 2) Fallback resiliente: DuckDuckGo HTML
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        titulos = re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
        snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>', html, flags=re.I | re.S)

        linhas = []
        for i, t in enumerate(titulos[:4]):
            titulo = re.sub(r"<.*?>", "", unescape(t)).strip()
            sn = ""
            if i < len(snippets):
                a, b = snippets[i]
                sn = re.sub(r"<.*?>", "", unescape((a or b or ""))).strip()
            if titulo or sn:
                linhas.append(f"• {titulo}: {sn[:220]}".strip())

        if linhas:
            return "\n".join(linhas)
        return "Nenhum resultado encontrado."
    except Exception as e:
        return f"Erro ao pesquisar: {e}"


def _pesquisar_no_navegador(query: str) -> str:
    """Pesquisa no Google: verifica o que está aberto e age de forma adequada."""
    import pyautogui as _pag

    # Primeiro: olha a tela para saber se já há um navegador aberto.
    try:
        estado = vision.descrever_tela(
            "Quais janelas ou programas estão visíveis na tela agora? "
            "Existe algum navegador aberto (Chrome, Edge, Firefox)? "
            "Responda em uma linha curta em português."
        )
    except Exception:
        estado = ""

    estado_norm = estado.lower()
    navegador_aberto = any(x in estado_norm for x in ("chrome", "edge", "firefox", "navegador", "google", "youtube", "http"))

    if navegador_aberto:
        # Usa a barra de endereço do navegador já aberto
        _pag.hotkey("ctrl", "l")
        _time.sleep(0.25)
        _pag.hotkey("ctrl", "a")
        _time.sleep(0.10)
        hands.digitar(f"https://www.google.com/search?q={quote_plus(query)}")
        _time.sleep(0.20)
        hands.pressionar_tecla("enter")
        _time.sleep(2.0)
    else:
        # Nenhum navegador aberto: abre nova janela
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        hands.abrir_site(url)
        _time.sleep(2.0)

    return f"Pesquisa aberta no Google: '{query}'. Os resultados estão visíveis na tela."


def _pesquisar_no_youtube(query: str) -> str:
    """Abre pesquisa de video diretamente no YouTube, evitando passar pelo Google."""
    import pyautogui as _pag

    query = (query or "").strip()
    if not query:
        return "Me diga o tema do video para eu pesquisar no YouTube."

    try:
        estado = vision.descrever_tela(
            "Quais janelas estao visiveis? Existe navegador aberto (Chrome, Edge, Firefox)?"
        )
    except Exception:
        estado = ""

    estado_norm = (estado or "").lower()
    navegador_aberto = any(x in estado_norm for x in ("chrome", "edge", "firefox", "navegador", "google", "youtube", "http"))
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"

    if navegador_aberto:
        _pag.hotkey("ctrl", "l")
        _time.sleep(0.25)
        _pag.hotkey("ctrl", "a")
        _time.sleep(0.10)
        hands.digitar(url)
        _time.sleep(0.20)
        hands.pressionar_tecla("enter")
        _time.sleep(2.0)
    else:
        hands.abrir_site(url)
        _time.sleep(2.0)

    return f"Pesquisa aberta no YouTube: '{query}'. Os videos estao visiveis na tela."


def _baixar_video_link(url: str, pasta_saida: str = "", qualidade: str = "", apenas_audio: bool = False) -> str:
    """Baixa um video de um link direto para a pasta de downloads do agente."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Envie um link valido completo (http/https) para baixar o video."

    if pasta_saida:
        destino = os.path.abspath(pasta_saida)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        destino = os.path.join(base_dir, "data", "downloads")

    os.makedirs(destino, exist_ok=True)

    try:
        import yt_dlp
    except Exception:
        return (
            "Nao consegui baixar porque falta a dependencia yt-dlp. "
            "Instale com: pip install yt-dlp"
        )

    qualidade = (qualidade or "").strip().lower()
    if qualidade.endswith("p"):
        qualidade = qualidade[:-1]
    if qualidade not in {"", "360", "480", "720", "1080", "1440", "2160"}:
        qualidade = ""

    outtmpl = os.path.join(destino, "%(title).120B [%(id)s].%(ext)s")
    if apenas_audio:
        formato = "bestaudio/best"
    elif qualidade:
        formato = f"bestvideo[height<={qualidade}]+bestaudio/best[height<={qualidade}]/best"
    else:
        formato = "best[ext=mp4]/best"

    ydl_opts = {
        "format": formato,
        "outtmpl": outtmpl,
        "noplaylist": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
    }
    if apenas_audio:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            caminho = ydl.prepare_filename(info)

        # Em alguns sites/extensoes o arquivo final pode variar de extensao.
        if not os.path.exists(caminho):
            base, _ = os.path.splitext(caminho)
            candidatos = [
                base + ".mp4",
                base + ".mkv",
                base + ".webm",
                base + ".mp3",
                base + ".m4a",
            ]
            for c in candidatos:
                if os.path.exists(c):
                    caminho = c
                    break

        if os.path.exists(caminho):
            try:
                tipo = "audio" if apenas_audio else "video"
                memory.registrar_arquivo(caminho, tipo, f"download de link: {url}")
            except Exception:
                pass
            if apenas_audio:
                return f"Audio baixado com sucesso em: {caminho}"
            if qualidade:
                return f"Video ({qualidade}p) baixado com sucesso em: {caminho}"
            return f"Video baixado com sucesso em: {caminho}"

        return f"Download concluido, mas nao localizei o arquivo final. Verifique a pasta: {destino}"
    except Exception as e:
        return f"Erro ao baixar video: {e}"


def _pesquisar_canais_monetizados(nicho: str, limite: int = 8) -> str:
    """Pesquisa canais do nicho e aponta sinais publicos de monetizacao (estimativa)."""
    nicho = (nicho or "").strip()
    if not nicho:
        return "Informe o nicho para pesquisar canais (ex: carros, receitas, tecnologia)."

    limite = max(3, min(int(limite or 8), 20))

    try:
        from duckduckgo_search import DDGS
        query = f"site:youtube.com {nicho} canal youtube"
        resultados = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=limite * 2):
                url = (r.get("href") or r.get("url") or "").strip()
                titulo = (r.get("title") or "").strip()
                trecho = (r.get("body") or "").strip()
                if "youtube.com" not in url.lower():
                    continue
                if not titulo and not url:
                    continue
                resultados.append((titulo, url, trecho))
                if len(resultados) >= limite:
                    break
    except Exception:
        resultados = []

    if not resultados:
        return (
            f"Nao consegui listar canais agora para '{nicho}'. "
            "Tente novamente em instantes ou use um nicho mais especifico."
        )

    sinais = (
        "membro",
        "members",
        "super chat",
        "super thanks",
        "anuncio",
        "ads",
        "patrocin",
        "afiliad",
        "sponsor",
    )

    linhas = [
        f"Canais encontrados para '{nicho}' (monetizacao = estimativa por sinais publicos):"
    ]
    for i, (titulo, url, trecho) in enumerate(resultados, start=1):
        tnorm = (f"{titulo} {trecho}").lower()
        score = sum(1 for s in sinais if s in tnorm)
        status = "provavel monetizado" if score >= 1 else "sem sinal claro"
        nome = titulo or "Canal sem titulo"
        linhas.append(f"{i}. {nome} | {status} | {url}")

    linhas.append(
        "Observacao: o YouTube nao exibe publicamente um selo oficial de monetizacao para todos os canais; "
        "a classificacao acima e por sinais visiveis."
    )
    return "\n".join(linhas)


def _modelar_videos_semelhantes(nicho: str, referencia: str = "", quantidade: int = 10) -> str:
    """Gera ideias modeladas para videos semelhantes a um canal/tema de referencia."""
    nicho = (nicho or "").strip() or "geral"
    referencia = (referencia or "").strip()
    quantidade = max(3, min(int(quantidade or 10), 30))

    base_temas = [
        "top 5 erros comuns",
        "antes e depois",
        "quanto custa de verdade",
        "mitos e verdades",
        "guia rapido para iniciantes",
        "comparativo real",
        "reacao e analise",
        "segredos que ninguem conta",
        "passo a passo pratico",
        "desafio de 7 dias",
        "setup ideal",
        "resultado final",
        "o que eu faria hoje",
        "ferramentas essenciais",
        "erros que me atrasaram",
    ]

    linhas = [
        f"Modelagem de conteudo para nicho '{nicho}'" + (f" com referencia '{referencia}'" if referencia else "") + ":",
        "Formato sugerido por video: Hook (3s) -> Prova/Execucao -> CTA.",
    ]
    for i in range(quantidade):
        tema = base_temas[i % len(base_temas)]
        titulo = f"{nicho.title()}: {tema.title()}"
        hook = f"Hook: 'Se voce curte {nicho}, veja isso antes de perder dinheiro/tempo.'"
        cta = "CTA: 'Comenta a proxima ideia e segue para parte 2.'"
        linhas.append(f"{i + 1}. {titulo} | {hook} | {cta}")

    return "\n".join(linhas)


def _gerar_agenda_postagens_youtube(nicho: str, videos_semana: int = 4, semanas: int = 4, horario: str = "20:00") -> str:
    """Cria uma agenda de postagem e salva em arquivo JSON para execucao recorrente."""
    from datetime import datetime, timedelta

    nicho = (nicho or "").strip() or "geral"
    videos_semana = max(1, min(int(videos_semana or 4), 7))
    semanas = max(1, min(int(semanas or 4), 12))
    horario = (horario or "20:00").strip()
    if not re.match(r"^\d{2}:\d{2}$", horario):
        horario = "20:00"

    agora = datetime.now()
    total = videos_semana * semanas

    # Distribui posts ao longo dos dias da semana.
    dias_usados = [0, 1, 2, 3, 4, 5, 6][:videos_semana]
    agenda = []
    idx = 1
    data_cursor = agora
    while len(agenda) < total:
        for d in dias_usados:
            delta = (d - data_cursor.weekday()) % 7
            if delta == 0 and data_cursor.date() == agora.date():
                delta = 1
            dia = data_cursor + timedelta(days=delta)
            item = {
                "ordem": idx,
                "titulo": f"{nicho.title()} #{idx}",
                "data": dia.strftime("%Y-%m-%d"),
                "hora": horario,
                "status": "planejado",
            }
            agenda.append(item)
            idx += 1
            if len(agenda) >= total:
                break
        data_cursor = data_cursor + timedelta(days=7)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    pasta = os.path.join(base_dir, "data")
    os.makedirs(pasta, exist_ok=True)
    arquivo = os.path.join(pasta, "youtube_agenda.json")
    payload = {
        "nicho": nicho,
        "videos_semana": videos_semana,
        "semanas": semanas,
        "horario": horario,
        "itens": agenda,
    }
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    try:
        memory.registrar_arquivo(arquivo, "agenda", f"agenda youtube para {nicho}")
    except Exception:
        pass

    preview = [f"Agenda criada ({total} posts) em: {arquivo}"]
    for it in agenda[:8]:
        preview.append(f"- {it['data']} {it['hora']} | {it['titulo']}")
    if len(agenda) > 8:
        preview.append(f"... e mais {len(agenda) - 8} posts planejados.")
    return "\n".join(preview)


def _planejar_operacao_youtube(nicho: str, referencia: str = "", videos_semana: int = 4) -> str:
    """Planeja operacao completa: pesquisa, modelagem de videos e agenda de postagem."""
    nicho = (nicho or "").strip() or "geral"
    referencia = (referencia or "").strip()

    parte1 = _pesquisar_canais_monetizados(nicho, limite=6)
    parte2 = _modelar_videos_semelhantes(nicho, referencia, quantidade=12)
    parte3 = _gerar_agenda_postagens_youtube(nicho, videos_semana=videos_semana, semanas=4, horario="20:00")

    return (
        "PLANO YOUTUBE PRONTO\n\n"
        + parte1
        + "\n\n"
        + parte2
        + "\n\n"
        + parte3
        + "\n\n"
        + "Proximo passo: abra o YouTube Studio para subir os videos e agendar conforme a agenda."
    )


def _youtube_tracker_path() -> str:
    custom = (getattr(config, "YOUTUBE_TRACKER_CSV", "") or "").strip()
    if custom:
        return os.path.abspath(custom)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "data", "youtube_tracker.csv")


def _youtube_channel_metrics_path() -> str:
    custom = (getattr(config, "YOUTUBE_CHANNEL_METRICS_CSV", "") or "").strip()
    if custom:
        return os.path.abspath(custom)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "data", "youtube_channel_metrics.csv")


def _youtube_get_access_token() -> str:
    cid = (getattr(config, "YOUTUBE_CLIENT_ID", "") or "").strip()
    secret = (getattr(config, "YOUTUBE_CLIENT_SECRET", "") or "").strip()
    refresh = (getattr(config, "YOUTUBE_REFRESH_TOKEN", "") or "").strip()
    if not cid or not secret or not refresh:
        raise ValueError(
            "Credenciais YouTube ausentes no .env: YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET e YOUTUBE_REFRESH_TOKEN."
        )

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": cid,
            "client_secret": secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao renovar token do YouTube: {resp.status_code} {resp.text[:240]}")
    token = (resp.json() or {}).get("access_token", "")
    if not token:
        raise RuntimeError("Token de acesso do YouTube vazio.")
    return token


def _youtube_verificar_conta_conectada() -> str:
    """Verifica qual conta/canal do YouTube esta conectado pelas credenciais atuais."""
    try:
        token = _youtube_get_access_token()
    except Exception as e:
        return f"Nao consegui autenticar no YouTube: {e}"

    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics", "mine": "true"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        return f"Erro ao consultar conta YouTube: {resp.status_code} {resp.text[:250]}"

    items = (resp.json() or {}).get("items", [])
    if not items:
        return "Token valido, mas nenhum canal encontrado para esta conta Google."

    ch = items[0]
    sn = ch.get("snippet") or {}
    st = ch.get("statistics") or {}
    canal_id = (ch.get("id") or "").strip()
    canal_nome = (sn.get("title") or "").strip()
    inscritos = st.get("subscriberCount", "")
    videos = st.get("videoCount", "")
    views = st.get("viewCount", "")

    return (
        "Conta YouTube conectada com sucesso.\n"
        f"Canal: {canal_nome}\n"
        f"Canal ID: {canal_id}\n"
        f"Inscritos: {inscritos}\n"
        f"Videos: {videos}\n"
        f"Views totais: {views}"
    )


def _youtube_iso_utc(dt_txt: str) -> str:
    from datetime import datetime, timezone

    txt = (dt_txt or "").strip()
    if not txt:
        return ""

    # Aceita: YYYY-MM-DD HH:MM | YYYY-MM-DDTHH:MM | ISO com/sem timezone.
    txt = txt.replace(" ", "T")
    if len(txt) == 16:
        txt = txt + ":00"
    dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _youtube_append_tracker(row: dict) -> None:
    import csv

    path = _youtube_tracker_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exists = os.path.exists(path)
    cols = [
        "data_execucao",
        "video_id",
        "url",
        "titulo",
        "status",
        "agendado_para",
        "arquivo_video",
        "canal",
        "view_count",
        "like_count",
        "comment_count",
    ]
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if not exists:
            w.writeheader()
        payload = {c: row.get(c, "") for c in cols}
        w.writerow(payload)


def _youtube_publicar_e_agendar(
    caminho_video: str,
    titulo: str,
    descricao: str = "",
    tags=None,
    privacidade: str = "private",
    agendar_em: str = "",
    categoria_id: str = "",
) -> str:
    """Publica video no YouTube via API oficial e opcionalmente agenda publicacao."""
    from datetime import datetime

    caminho = os.path.abspath((caminho_video or "").strip())
    if not caminho or not os.path.exists(caminho):
        return f"Arquivo de video nao encontrado: {caminho_video}"
    if not titulo:
        return "Informe um titulo para publicar no YouTube."

    tags_list = []
    if isinstance(tags, list):
        tags_list = [str(t).strip() for t in tags if str(t).strip()]
    elif isinstance(tags, str) and tags.strip():
        tags_list = [p.strip() for p in tags.split(",") if p.strip()]

    privacy = (privacidade or "private").strip().lower()
    if privacy not in {"private", "public", "unlisted"}:
        privacy = "private"

    publish_at = ""
    if agendar_em:
        try:
            publish_at = _youtube_iso_utc(agendar_em)
            privacy = "private"  # regra da API para agendamento
        except Exception as e:
            return f"Formato de data/hora invalido para agendamento: {e}"

    cat_id = str(categoria_id or getattr(config, "YOUTUBE_DEFAULT_CATEGORY_ID", "2") or "2")

    try:
        token = _youtube_get_access_token()
    except Exception as e:
        return f"Nao consegui autenticar no YouTube: {e}"

    metadata = {
        "snippet": {
            "title": titulo[:100],
            "description": descricao[:5000],
            "categoryId": cat_id,
            "tags": tags_list[:40],
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if publish_at:
        metadata["status"]["publishAt"] = publish_at

    try:
        init_resp = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/*",
            },
            data=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            timeout=60,
        )
        if init_resp.status_code not in (200, 201):
            return f"Falha ao iniciar upload YouTube: {init_resp.status_code} {init_resp.text[:300]}"

        upload_url = init_resp.headers.get("Location", "").strip()
        if not upload_url:
            return "Falha ao iniciar upload: URL de upload nao retornada pela API."

        with open(caminho, "rb") as f:
            binario = f.read()

        put_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/*",
            },
            data=binario,
            timeout=1800,
        )
        if put_resp.status_code not in (200, 201):
            return f"Falha no upload final YouTube: {put_resp.status_code} {put_resp.text[:300]}"

        data = put_resp.json() or {}
        vid = str(data.get("id", "")).strip()
        if not vid:
            return "Upload concluido, mas a API nao retornou video_id."

        url = f"https://www.youtube.com/watch?v={vid}"
        canal = ((data.get("snippet") or {}).get("channelTitle") or "")

        _youtube_append_tracker({
            "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "video_id": vid,
            "url": url,
            "titulo": titulo,
            "status": "agendado" if publish_at else privacy,
            "agendado_para": publish_at,
            "arquivo_video": caminho,
            "canal": canal,
            "view_count": "",
            "like_count": "",
            "comment_count": "",
        })

        try:
            memory.registrar_arquivo(_youtube_tracker_path(), "planilha", "rastreamento youtube")
        except Exception:
            pass

        if publish_at:
            return f"Video enviado e agendado com sucesso para {publish_at}. Link: {url}"
        return f"Video publicado com sucesso. Link: {url}"
    except Exception as e:
        return f"Erro ao publicar video no YouTube: {e}"


def _youtube_sincronizar_planilha_metricas(limite: int = 20) -> str:
    """Atualiza planilha com metricas de canal e videos mais recentes do canal autenticado."""
    import csv
    from datetime import datetime

    limite = max(1, min(int(limite or 20), 50))
    try:
        token = _youtube_get_access_token()
    except Exception as e:
        return f"Nao consegui autenticar no YouTube: {e}"

    headers = {"Authorization": f"Bearer {token}"}

    ch_resp = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics,contentDetails", "mine": "true"},
        headers=headers,
        timeout=30,
    )
    if ch_resp.status_code != 200:
        return f"Erro ao ler dados do canal: {ch_resp.status_code} {ch_resp.text[:250]}"

    ch_items = (ch_resp.json() or {}).get("items", [])
    if not ch_items:
        return "Nenhum canal encontrado para o token atual."

    canal = ch_items[0]
    canal_id = ((canal.get("id") or "")).strip()
    canal_nome = ((canal.get("snippet") or {}).get("title") or "").strip()
    stats = canal.get("statistics") or {}
    uploads = (((canal.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or "").strip()

    # Salva metricas do canal
    channel_csv = _youtube_channel_metrics_path()
    os.makedirs(os.path.dirname(channel_csv), exist_ok=True)
    new_file = not os.path.exists(channel_csv)
    with open(channel_csv, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "data_execucao",
                "canal_id",
                "canal",
                "inscritos",
                "views_total",
                "videos_total",
            ],
        )
        if new_file:
            w.writeheader()
        w.writerow({
            "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "canal_id": canal_id,
            "canal": canal_nome,
            "inscritos": stats.get("subscriberCount", ""),
            "views_total": stats.get("viewCount", ""),
            "videos_total": stats.get("videoCount", ""),
        })

    if not uploads:
        return "Metricas do canal atualizadas, mas nao encontrei playlist de uploads."

    pl_resp = requests.get(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        params={"part": "contentDetails", "playlistId": uploads, "maxResults": min(limite, 50)},
        headers=headers,
        timeout=30,
    )
    if pl_resp.status_code != 200:
        return f"Canal atualizado, mas falhou leitura de videos: {pl_resp.status_code} {pl_resp.text[:250]}"

    v_ids = [
        (((it.get("contentDetails") or {}).get("videoId") or "").strip())
        for it in ((pl_resp.json() or {}).get("items") or [])
    ]
    v_ids = [v for v in v_ids if v]
    if not v_ids:
        return "Canal atualizado, sem videos recentes para sincronizar."

    v_resp = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics,status", "id": ",".join(v_ids)},
        headers=headers,
        timeout=40,
    )
    if v_resp.status_code != 200:
        return f"Canal atualizado, mas falhou leitura de stats dos videos: {v_resp.status_code} {v_resp.text[:250]}"

    for it in ((v_resp.json() or {}).get("items") or []):
        vid = (it.get("id") or "").strip()
        sn = it.get("snippet") or {}
        st = it.get("statistics") or {}
        status = it.get("status") or {}
        _youtube_append_tracker({
            "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "titulo": sn.get("title", ""),
            "status": status.get("privacyStatus", ""),
            "agendado_para": status.get("publishAt", ""),
            "arquivo_video": "",
            "canal": sn.get("channelTitle", ""),
            "view_count": st.get("viewCount", ""),
            "like_count": st.get("likeCount", ""),
            "comment_count": st.get("commentCount", ""),
        })

    try:
        memory.registrar_arquivo(channel_csv, "planilha", "metricas canal youtube")
        memory.registrar_arquivo(_youtube_tracker_path(), "planilha", "tracker videos youtube")
    except Exception:
        pass

    return (
        f"Planilhas atualizadas com sucesso. Canal: {canal_nome}. "
        f"Videos sincronizados: {len(v_ids)}. "
        f"Tracker: {_youtube_tracker_path()} | Canal: {channel_csv}"
    )


def _gerar_lote_conteudo_youtube(nicho: str, quantidade: int = 12) -> str:
    """Cria lote de conteudo (titulo/descricao/tags) para producao de videos."""
    from datetime import datetime

    nicho = (nicho or "").strip() or "geral"
    quantidade = max(3, min(int(quantidade or 12), 50))
    itens = []
    for i in range(1, quantidade + 1):
        titulo = f"{nicho.title()} #{i} - Dica rapida que melhora seu resultado"
        descricao = (
            f"Video sobre {nicho}.\n\n"
            "Neste episodio voce aprende um metodo simples e direto para aplicar hoje.\n"
            "Curta, comente e se inscreva para receber os proximos videos."
        )
        tags = [nicho, f"{nicho} brasil", "dicas", "tutorial", "youtube"]
        itens.append({"ordem": i, "titulo": titulo, "descricao": descricao, "tags": tags})

    base_dir = os.path.dirname(os.path.abspath(__file__))
    pasta = os.path.join(base_dir, "data")
    os.makedirs(pasta, exist_ok=True)
    arq = os.path.join(pasta, "youtube_lote_conteudo.json")
    payload = {"nicho": nicho, "gerado_em": datetime.now().isoformat(), "itens": itens}
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    try:
        memory.registrar_arquivo(arq, "roteiro", f"lote youtube {nicho}")
    except Exception:
        pass

    return f"Lote de conteudo criado com {quantidade} ideias em: {arq}"


def _youtube_inicializar_automacao_total(nicho: str, videos_semana: int = 4) -> str:
    """Inicializa operacao automatica: agenda, lote de conteudo e planilhas de acompanhamento."""
    nicho = (nicho or "").strip() or "geral"
    agenda_msg = _gerar_agenda_postagens_youtube(nicho, videos_semana=videos_semana, semanas=4, horario="20:00")
    lote_msg = _gerar_lote_conteudo_youtube(nicho, quantidade=max(8, videos_semana * 4))

    # Gera arquivos de planilha mesmo sem token, para ja acompanhar localmente.
    try:
        _youtube_append_tracker({
            "data_execucao": "",
            "video_id": "",
            "url": "",
            "titulo": "",
            "status": "",
            "agendado_para": "",
            "arquivo_video": "",
            "canal": "",
            "view_count": "",
            "like_count": "",
            "comment_count": "",
        })
    except Exception:
        pass

    sync_msg = _youtube_sincronizar_planilha_metricas(20)

    return (
        "Automacao YouTube inicializada.\n\n"
        + agenda_msg
        + "\n\n"
        + lote_msg
        + "\n\n"
        + sync_msg
    )


def _montar_video(imagens: list, saida: str, duracao_por_imagem: float = 3.0, musica: str = "") -> str:
    """Monta um vídeo slideshow a partir de uma lista de imagens."""
    try:
        from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
        clips = []
        for img in imagens:
            if not os.path.exists(img):
                continue
            c = ImageClip(img).with_duration(duracao_por_imagem)
            clips.append(c)
        if not clips:
            return "Nenhuma imagem válida encontrada."
        video = concatenate_videoclips(clips, method="compose")
        if musica and os.path.exists(musica):
            audio = AudioFileClip(musica).with_duration(video.duration)
            video = video.with_audio(audio)
        if not saida.endswith(".mp4"):
            saida += ".mp4"
        pasta = os.path.dirname(saida)
        if pasta and not os.path.exists(pasta):
            os.makedirs(pasta, exist_ok=True)
        video.write_videofile(saida, fps=24, logger=None)
        return f"Vídeo criado em: {saida}"
    except Exception as e:
        return f"Erro ao criar vídeo: {e}"


def _abrir_editor_video(editor: str = "") -> str:
    """Abre editor de video ou app Adobe/Creative Cloud instalado no PC."""
    import subprocess, os

    # Caminhos reais de executáveis Adobe no Windows
    CC_EXE = r"C:\Program Files\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe"

    # Mapa: chave → lista de (caminho_abs ou nome_para_shell)
    editores = {
        "creative cloud": [CC_EXE, "Creative Cloud"],
        "capcut":         ["capcut"],
        "davinci":        ["DaVinciResolve"],
        "premiere":       [
            r"C:\Program Files\Adobe\Adobe Premiere Pro 2025\Adobe Premiere Pro.exe",
            r"C:\Program Files\Adobe\Adobe Premiere Pro 2024\Adobe Premiere Pro.exe",
            "premiere",
        ],
        "after effects":  [
            r"C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe",
            r"C:\Program Files\Adobe\Adobe After Effects 2024\Support Files\AfterFX.exe",
            "AfterFX",
        ],
        "photoshop": [
            r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
            r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
            "Photoshop",
        ],
        "illustrator": [
            r"C:\Program Files\Adobe\Adobe Illustrator 2025\Support Files\Contents\Windows\Illustrator.exe",
            "Illustrator",
        ],
        "lightroom": [
            r"C:\Program Files\Adobe\Adobe Lightroom Classic\lightroom.exe",
            "Lightroom",
        ],
        "indesign": [
            r"C:\Program Files\Adobe\Adobe InDesign 2025\InDesign.exe",
            "InDesign",
        ],
        "audition": [
            r"C:\Program Files\Adobe\Adobe Audition 2025\Adobe Audition.exe",
            "Audition",
        ],
        "vegas":          ["vegas"],
        "kdenlive":       ["kdenlive"],
    }

    nome = editor.lower().strip()

    for chave, caminhos in editores.items():
        if chave in nome or (not nome and chave == "creative cloud"):
            for c in caminhos:
                try:
                    # Tenta caminho absoluto primeiro (se existe)
                    if os.path.isfile(c):
                        subprocess.Popen([c])
                        return f"Abrindo {chave} ({os.path.basename(c)})..."
                    else:
                        subprocess.Popen([c], shell=True)
                        return f"Abrindo {chave}..."
                except Exception:
                    continue

    # Fallback: tenta pelo nome informado diretamente
    try:
        if os.path.isfile(editor):
            subprocess.Popen([editor])
        else:
            subprocess.Popen([editor], shell=True)
        return f"Tentando abrir: {editor}"
    except Exception as e:
        return f"Não encontrei o app '{editor}'. Verifique se está instalado."


# ── Creative Cloud Desktop ─────────────────────────────────────────────────────

_CC_EXE = r"C:\Program Files\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe"

def _abrir_creative_cloud() -> str:
    """Abre o Adobe Creative Cloud Desktop."""
    import subprocess, os
    if not os.path.isfile(_CC_EXE):
        return "Creative Cloud Desktop não encontrado. Verifique se está instalado."
    try:
        subprocess.Popen([_CC_EXE])
        import time; time.sleep(4)
        return "Creative Cloud Desktop aberto."
    except Exception as e:
        return f"Erro ao abrir Creative Cloud: {e}"


def _listar_apps_adobe_instalados() -> str:
    """Lista todos os apps Adobe instalados no computador."""
    import os, glob
    raiz = r"C:\Program Files\Adobe"
    if not os.path.isdir(raiz):
        return "Pasta Adobe não encontrada."
    apps = []
    for item in os.listdir(raiz):
        full = os.path.join(raiz, item)
        if os.path.isdir(full):
            apps.append(item)
    if not apps:
        return "Nenhum app Adobe encontrado em Program Files."
    return "Apps Adobe instalados:\n" + "\n".join(f"• {a}" for a in sorted(apps))


def _instalar_app_adobe(app: str) -> str:
    """Abre o Creative Cloud Desktop e usa PyAutoGUI para instalar/abrir um app Adobe pelo nome."""
    import subprocess, os, time
    try:
        import pyautogui
    except ImportError:
        return "pyautogui não instalado. Execute: pip install pyautogui"

    # Abre o CC Desktop
    if os.path.isfile(_CC_EXE):
        subprocess.Popen([_CC_EXE])
    else:
        return "Creative Cloud Desktop não encontrado."

    time.sleep(5)  # aguarda a janela carregar

    # Foca a janela do Creative Cloud
    try:
        import pygetwindow as gw
        janelas = [w for w in gw.getAllTitles() if "creative cloud" in w.lower()]
        if janelas:
            win = gw.getWindowsWithTitle(janelas[0])[0]
            win.activate()
            time.sleep(1)
    except Exception:
        pass  # Se pygetwindow não estiver instalado, continua sem focar

    # Usa Ctrl+F ou a barra de pesquisa para encontrar o app
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.8)
    pyautogui.write(app, interval=0.05)
    time.sleep(1.5)

    return (
        f"Creative Cloud aberto e pesquisei por '{app}'.\n"
        "Verifique a tela — clique em 'Instalar' ou 'Abrir' para continuar."
    )


def _creative_cloud_criar_projeto(nome_projeto: str, tipo: str = "web") -> str:
    """
    Cria um novo projeto no Adobe Creative Cloud (pasta local + abre CC).
    tipo: 'web', 'video', 'design', 'foto', 'audio'
    """
    import os, json
    from datetime import datetime

    pasta_projetos = os.path.join("data", "projetos_adobe")
    os.makedirs(pasta_projetos, exist_ok=True)

    slug = nome_projeto.lower().replace(" ", "_")
    pasta_projeto = os.path.join(pasta_projetos, slug)
    os.makedirs(pasta_projeto, exist_ok=True)

    meta = {
        "nome": nome_projeto,
        "tipo": tipo,
        "criado_em": datetime.now().isoformat(),
        "status": "em_andamento",
        "pasta": pasta_projeto,
        "app_sugerido": {
            "web": "Dreamweaver ou Adobe XD",
            "video": "Premiere Pro ou After Effects",
            "design": "Photoshop ou Illustrator",
            "foto": "Lightroom ou Photoshop",
            "audio": "Audition",
        }.get(tipo, "Creative Cloud"),
    }

    meta_file = os.path.join(pasta_projeto, "projeto.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Abre o Creative Cloud Desktop
    _abrir_creative_cloud()

    return (
        f"Projeto '{nome_projeto}' criado!\n"
        f"Pasta: {pasta_projeto}\n"
        f"Tipo: {tipo}\n"
        f"App sugerido: {meta['app_sugerido']}\n"
        f"Creative Cloud Desktop aberto para você instalar/abrir o app."
    )


def _creative_cloud_listar_projetos() -> str:
    """Lista todos os projetos Adobe criados pela Evelyn."""
    import os, json
    pasta = os.path.join("data", "projetos_adobe")
    if not os.path.isdir(pasta):
        return "Nenhum projeto Adobe criado ainda."
    projetos = []
    for slug in os.listdir(pasta):
        meta_file = os.path.join(pasta, slug, "projeto.json")
        if os.path.isfile(meta_file):
            with open(meta_file, encoding="utf-8") as f:
                m = json.load(f)
            projetos.append(m)
    if not projetos:
        return "Nenhum projeto encontrado."
    linhas = ["Projetos Adobe:"]
    for p in projetos:
        linhas.append(f"• {p['nome']} | tipo: {p['tipo']} | status: {p['status']} | app: {p['app_sugerido']}")
    return "\n".join(linhas)


def _pesquisar_tendencias_video(nicho: str = "") -> str:
    """Pesquisa vídeos em alta no momento para um nicho específico."""
    try:
        from duckduckgo_search import DDGS
        query = f"vídeos virais em alta {nicho} 2026 tendência YouTube TikTok"
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=5))
        if not resultados:
            return "Nenhuma tendência encontrada."
        linhas = ["Tendências de vídeo em alta:"]
        for r in resultados:
            linhas.append(f"• {r.get('title','')}: {r.get('body','')[:150]}")
        return "\n".join(linhas)
    except Exception as e:
        return f"Erro ao buscar tendências: {e}"

def _preenchimento_generativo(imagem: str, prompt: str, area: str = "") -> str:
    """Preenchimento generativo estilo Photoshop via DALL-E 2 (OpenAI)."""
    try:
        import openai
        from PIL import Image, ImageDraw
        import io
        import urllib.request
        import config
        if not config.OPENAI_API_KEY:
            return "Erro: OPENAI_API_KEY não configurada no config.py ou variável de ambiente."
        if not os.path.exists(imagem):
            return f"Erro: imagem não encontrada em '{imagem}'."
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        img = Image.open(imagem).convert("RGBA")
        w, h = img.size
        mask = Image.new("RGBA", (w, h), (255, 255, 255, 255))  # tudo opaco = manter
        if area:
            x1, y1, x2, y2 = map(int, area.split(","))
            draw = ImageDraw.Draw(mask)
            draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 0))  # transparente = preencher
        else:
            mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # preenche tudo
        tamanho = (1024, 1024)
        img_rs  = img.resize(tamanho, Image.LANCZOS)
        mask_rs = mask.resize(tamanho, Image.NEAREST)
        buf_img  = io.BytesIO(); img_rs.save(buf_img, format="PNG"); buf_img.seek(0)
        buf_mask = io.BytesIO(); mask_rs.save(buf_mask, format="PNG"); buf_mask.seek(0)
        response = client.images.edit(
            image=buf_img,
            mask=buf_mask,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        url = response.data[0].url
        nome_base = os.path.splitext(imagem)[0]
        saida = nome_base + "_gen.png"
        urllib.request.urlretrieve(url, saida)
        os.startfile(saida)
        return f"Preenchimento concluído! Imagem salva em: {saida}"
    except Exception as e:
        return f"Erro no preenchimento generativo: {e}"


# ── Adobe Firefly ──────────────────────────────────────────────────────────────

def _firefly_token() -> str:
    """Obtém token OAuth do Adobe IMS usando Client Credentials."""
    import urllib.request, urllib.parse
    import config, json as _json
    if not config.ADOBE_CLIENT_ID or not config.ADOBE_CLIENT_SECRET:
        raise ValueError(
            "Credenciais Adobe não configuradas.\n"
            "Adicione ADOBE_CLIENT_ID e ADOBE_CLIENT_SECRET no arquivo .env\n"
            "(crie em https://developer.adobe.com/console → New project → Add API → Firefly)"
        )
    data = urllib.parse.urlencode({
        "grant_type":    "client_credentials",
        "client_id":     config.ADOBE_CLIENT_ID,
        "client_secret": config.ADOBE_CLIENT_SECRET,
        "scope":         "openid,AdobeID,firefly_enterprise,firefly_api",
    }).encode()
    req = urllib.request.Request(
        "https://ims-na1.adobelogin.com/ims/token/v3",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return _json.loads(r.read())["access_token"]


def _firefly_post(endpoint: str, payload: dict) -> dict:
    """Faz POST autenticado na API Firefly e retorna o JSON de resposta."""
    import urllib.request, json as _json, config
    token = _firefly_token()
    body  = _json.dumps(payload).encode()
    req   = urllib.request.Request(
        f"https://firefly-api.adobe.io{endpoint}",
        data=body,
        headers={
            "Authorization":  f"Bearer {token}",
            "x-api-key":      config.ADOBE_CLIENT_ID,
            "Content-Type":   "application/json",
            "Accept":         "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return _json.loads(r.read())


def _firefly_download(url: str, saida: str) -> None:
    """Baixa um arquivo da URL para o caminho de saída."""
    import urllib.request
    urllib.request.urlretrieve(url, saida)


def _firefly_gerar_imagem(prompt: str, saida: str = "", estilo: str = "") -> str:
    """Gera imagem com Adobe Firefly (text-to-image). Retorna caminho do arquivo."""
    try:
        payload: dict = {
            "prompt": prompt,
            "n":      1,
            "size":   {"width": 1024, "height": 1024},
        }
        if estilo:
            payload["styles"] = [{"presetId": estilo}]
        resp  = _firefly_post("/v3/images/generate", payload)
        img_url = resp["outputs"][0]["image"]["url"]
        if not saida:
            import tempfile
            saida = os.path.join(tempfile.gettempdir(), "firefly_imagem.png")
        _firefly_download(img_url, saida)
        os.startfile(saida)
        return f"Imagem gerada e aberta: {saida}"
    except Exception as e:
        return f"Erro Firefly gerar imagem: {e}"


def _firefly_preenchimento(imagem: str, prompt: str, mascara: str = "") -> str:
    """Preenchimento generativo Adobe Firefly (Generative Fill) em uma imagem."""
    try:
        import base64
        with open(imagem, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        payload: dict = {
            "prompt": prompt,
            "image":  {"source": {"uploadId": None, "base64": img_b64}},
        }
        if mascara and os.path.exists(mascara):
            with open(mascara, "rb") as f:
                mask_b64 = base64.b64encode(f.read()).decode()
            payload["mask"] = {"source": {"base64": mask_b64}}
        resp    = _firefly_post("/v3/images/fill", payload)
        img_url = resp["outputs"][0]["image"]["url"]
        nome_base = os.path.splitext(imagem)[0]
        saida = nome_base + "_firefly.png"
        _firefly_download(img_url, saida)
        os.startfile(saida)
        return f"Preenchimento Firefly concluído! Salvo em: {saida}"
    except Exception as e:
        return f"Erro Firefly preenchimento: {e}"


def _firefly_texto_para_video(prompt: str, saida: str = "") -> str:
    """Gera vídeo a partir de texto usando Adobe Firefly (consome créditos generativos)."""
    try:
        payload = {
            "prompt": prompt,
            "size":   {"width": 1920, "height": 1080},
            "fps":    24,
        }
        resp    = _firefly_post("/v3/video/generate", payload)
        # O endpoint pode retornar job assíncrono ou URL direta
        if "outputs" in resp:
            vid_url = resp["outputs"][0]["video"]["url"]
        elif "jobId" in resp:
            return (
                f"Vídeo sendo gerado (job {resp['jobId']}). "
                "Acesse https://firefly.adobe.com para baixar quando pronto."
            )
        else:
            return f"Resposta inesperada: {resp}"
        if not saida:
            import tempfile
            saida = os.path.join(tempfile.gettempdir(), "firefly_video.mp4")
        _firefly_download(vid_url, saida)
        os.startfile(saida)
        return f"Vídeo gerado e aberto: {saida}"
    except Exception as e:
        return f"Erro Firefly texto-para-vídeo: {e}"


_DANGEROUS_TOOL_NAMES = {"pressionar_tecla", "atalho", "digitar"}
_DANGEROUS_TEXT_MARKERS = (
    "enviar",
    "submit",
    "confirmar",
    "confirm",
    "pagar",
    "payment",
    "comprar",
    "buy",
    "finalizar",
)

# ── Telegram ────────────────────────────────────────────────────────────

def _enviar_telegram(mensagem: str) -> str:
    """Envia mensagem proativa ao dono pelo bot Telegram."""
    import config
    import requests as _req
    token   = getattr(config, "TELEGRAM_BOT_TOKEN",  "").strip()
    chat_id = getattr(config, "TELEGRAM_ALLOWED_ID", "").strip()
    if not token:
        return "TELEGRAM_BOT_TOKEN não configurado."
    if not chat_id:
        return "chat_id do dono ainda não registrado — peça para ele mandar /start ao bot primeiro."
    try:
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": mensagem},
            timeout=10,
        )
        if r.ok:
            return "Mensagem enviada no Telegram."
        return f"Erro ao enviar: {r.text}"
    except Exception as exc:
        return f"Erro ao enviar Telegram: {exc}"


# ── Definições (formato OpenAI function-calling) ──────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ver_tela",
            "description": "Tira um screenshot e analisa o que está na tela. Use ANTES de clicar em qualquer coisa para entender o estado atual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pergunta": {
                        "type": "string",
                        "description": "O que quer saber sobre a tela? Ex: 'Quais campos tem no formulário?' ou 'Qual é o botão de enviar?'",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clicar",
            "description": "Clica em uma coordenada (x, y) na tela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Coordenada X"},
                    "y": {"type": "integer", "description": "Coordenada Y"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clicar_duplo",
            "description": "Duplo clique em uma coordenada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "digitar",
            "description": "Digita (cola) texto no campo ativo. Funciona com acentos e caracteres especiais.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a digitar"},
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pressionar_tecla",
            "description": "Pressiona uma tecla. Ex: 'enter', 'tab', 'escape', 'backspace', 'f5'",
            "parameters": {
                "type": "object",
                "properties": {
                    "tecla": {"type": "string", "description": "Nome da tecla"},
                },
                "required": ["tecla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "atalho",
            "description": "Executa atalho de teclado. Ex: 'ctrl+c', 'ctrl+v', 'ctrl+t', 'alt+tab', 'ctrl+shift+t'",
            "parameters": {
                "type": "object",
                "properties": {
                    "teclas": {"type": "string", "description": "Teclas separadas por +"},
                },
                "required": ["teclas"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Rola a página uma vez com força. Positivo = sobe, Negativo = desce. Use -1 para descer, 1 para subir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quantidade": {"type": "integer"},
                },
                "required": ["quantidade"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_continuo",
            "description": "Rola a tela continuamente até o usuário mandar parar. Use quando o usuário pedir para ficar rolando.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direcao": {"type": "string", "description": "baixo ou cima"},
                },
                "required": ["direcao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parar_scroll",
            "description": "Para o scroll contínuo. Use quando o usuário disser 'para', 'chega', 'stop'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_web",
            "description": "Pesquisa na internet em segundo plano e retorna os resultados em texto (sem abrir navegador). Use para responder perguntas rápidas via chat ou Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "O que pesquisar"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_no_navegador",
            "description": "Abre o navegador, digita a pesquisa no campo do Google, pressiona Enter, vê os resultados na tela e indica onde clicar. Use SEMPRE que o usuário pedir para pesquisar algo no Google, abrir o navegador e buscar, ou quiser que você navegue até um site pelos resultados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "O que pesquisar no Google"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_no_youtube",
            "description": "Abre o navegador e pesquisa diretamente no YouTube (resultados de videos), sem passar pelo Google. Use quando o usuario pedir video, YouTube ou para assistir algo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Tema do video para pesquisar no YouTube"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "baixar_video_link",
            "description": "Baixa um video a partir de um link direto (YouTube e outros sites suportados). Use quando o usuario pedir para baixar/abaixar um video por URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Link completo do video (http/https)"},
                    "pasta_saida": {"type": "string", "description": "Pasta opcional para salvar o arquivo"},
                    "qualidade": {"type": "string", "description": "Qualidade desejada: 360, 480, 720, 1080, 1440, 2160"},
                    "apenas_audio": {"type": "boolean", "description": "Se true, baixa somente o audio (mp3)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_canais_monetizados",
            "description": "Pesquisa canais de YouTube por nicho e mostra sinais publicos de monetizacao (estimativa).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho para pesquisar canais (ex: carros, culinaria, games)"},
                    "limite": {"type": "integer", "description": "Quantidade maxima de canais (3 a 20)"},
                },
                "required": ["nicho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modelar_videos_semelhantes",
            "description": "Gera ideias e estrutura de videos semelhantes para um nicho/canal de referencia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho principal do canal"},
                    "referencia": {"type": "string", "description": "Canal ou estilo de referencia (opcional)"},
                    "quantidade": {"type": "integer", "description": "Quantidade de ideias (3 a 30)"},
                },
                "required": ["nicho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gerar_agenda_postagens_youtube",
            "description": "Cria agenda de postagem para YouTube e salva no arquivo data/youtube_agenda.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho do canal"},
                    "videos_semana": {"type": "integer", "description": "Quantos videos por semana"},
                    "semanas": {"type": "integer", "description": "Numero de semanas"},
                    "horario": {"type": "string", "description": "Horario padrao HH:MM"},
                },
                "required": ["nicho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "planejar_operacao_youtube",
            "description": "Executa plano completo para YouTube: pesquisa de canais, modelagem de videos e agenda de postagens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho principal"},
                    "referencia": {"type": "string", "description": "Canal ou estilo de referencia (opcional)"},
                    "videos_semana": {"type": "integer", "description": "Quantidade de videos por semana"},
                },
                "required": ["nicho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_publicar_e_agendar",
            "description": "Publica video no YouTube via API oficial e opcionalmente agenda publicacao automatica (100% sem clicar).",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_video": {"type": "string", "description": "Caminho completo do arquivo de video"},
                    "titulo": {"type": "string", "description": "Titulo do video"},
                    "descricao": {"type": "string", "description": "Descricao do video"},
                    "tags": {"type": "string", "description": "Tags separadas por virgula, ex: viagem,vlog,brasil"},
                    "privacidade": {"type": "string", "description": "private | public | unlisted"},
                    "agendar_em": {"type": "string", "description": "Data/hora para publicar (YYYY-MM-DD HH:MM ou ISO)"},
                    "categoria_id": {"type": "string", "description": "Categoria YouTube, ex: 2=Autos & Vehicles"},
                },
                "required": ["caminho_video", "titulo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_sincronizar_planilha_metricas",
            "description": "Atualiza planilhas de acompanhamento do canal e videos com metricas reais da API do YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limite": {"type": "integer", "description": "Quantidade de videos recentes para sincronizar"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_verificar_conta_conectada",
            "description": "Mostra qual conta/canal YouTube esta conectado pelas credenciais atuais, para confirmar que e a conta do usuario.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gerar_lote_conteudo_youtube",
            "description": "Cria um lote de titulos, descricoes e tags para produzir videos em escala.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho do canal"},
                    "quantidade": {"type": "integer", "description": "Quantidade de ideias para o lote"},
                },
                "required": ["nicho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_inicializar_automacao_total",
            "description": "Inicializa operacao automatica do YouTube: agenda, lote de conteudo e planilhas de acompanhamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho principal do canal"},
                    "videos_semana": {"type": "integer", "description": "Quantidade de videos por semana"},
                },
                "required": ["nicho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_tendencias",
            "description": "Pesquisa vídeos e conteúdos virais em alta no momento. Use quando o usuário perguntar o que está em alta, trending ou viral.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nicho": {"type": "string", "description": "Nicho ou tema (ex: fitness, receitas, tecnologia). Deixe vazio para tendências gerais."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "montar_video",
            "description": "Cria um vídeo slideshow a partir de imagens. O usuário precisa fornecer os caminhos das imagens e o nome do arquivo de saída.",
            "parameters": {
                "type": "object",
                "properties": {
                    "imagens": {"type": "array", "items": {"type": "string"}, "description": "Lista de caminhos das imagens"},
                    "saida":   {"type": "string", "description": "Caminho do arquivo de vídeo de saída (.mp4)"},
                    "duracao_por_imagem": {"type": "number", "description": "Duração em segundos de cada imagem (padrão 3)"},
                    "musica":  {"type": "string", "description": "Caminho de arquivo de áudio opcional"},
                },
                "required": ["imagens", "saida"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_editor_video",
            "description": "Abre um editor de vídeo ou app Adobe instalado no PC (CapCut, DaVinci, Premiere, Vegas, Kdenlive, Creative Cloud, Photoshop, Illustrator, After Effects).",
            "parameters": {
                "type": "object",
                "properties": {
                    "editor": {"type": "string", "description": "Nome do app: capcut, davinci, premiere, vegas, kdenlive, creative cloud, photoshop, illustrator, after effects"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_creative_cloud",
            "description": "Abre o Adobe Creative Cloud Desktop.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_apps_adobe_instalados",
            "description": "Lista todos os apps Adobe instalados no computador.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "instalar_app_adobe",
            "description": "Abre o Creative Cloud Desktop e pesquisa um app Adobe para instalar ou abrir (ex: Photoshop, Premiere, After Effects, Illustrator).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Nome do app Adobe a buscar/instalar, ex: Photoshop, Premiere Pro, After Effects"},
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "creative_cloud_criar_projeto",
            "description": "Cria um novo projeto Adobe Creative Cloud (pasta local organizada) e abre o CC Desktop. Use quando o usuário pedir para criar um projeto de design, vídeo, foto, áudio ou web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_projeto": {"type": "string", "description": "Nome do projeto"},
                    "tipo": {"type": "string", "description": "Tipo: web, video, design, foto, audio", "enum": ["web", "video", "design", "foto", "audio"]},
                },
                "required": ["nome_projeto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "creative_cloud_listar_projetos",
            "description": "Lista todos os projetos Adobe criados pela Evelyn.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preenchimento_generativo",
            "description": "Preenchimento generativo estilo Photoshop: usa IA (DALL-E) para preencher uma área de imagem com conteúdo gerado por texto. Requer OPENAI_API_KEY configurada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "imagem": {"type": "string", "description": "Caminho completo da imagem de entrada (.png ou .jpg)"},
                    "prompt": {"type": "string", "description": "O que gerar na área (ex: 'céu azul com nuvens', 'fundo desfocado')"},
                    "area":   {"type": "string", "description": "Área retangular a preencher em pixels: 'x1,y1,x2,y2'. Omita para preencher/regenerar a imagem inteira."},
                },
                "required": ["imagem", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "firefly_gerar_imagem",
            "description": "Gera uma imagem com Adobe Firefly (Creative Cloud) a partir de uma descrição de texto. Requer ADOBE_CLIENT_ID e ADOBE_CLIENT_SECRET no .env.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Descrição da imagem a gerar (em inglês para melhores resultados)"},
                    "saida":  {"type": "string", "description": "Caminho do arquivo de saída (.png). Omita para salvar na pasta temp."},
                    "estilo": {"type": "string", "description": "Estilo visual opcional (ex: 'photo', 'art', 'graphic')"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "firefly_preenchimento",
            "description": "Preenchimento generativo Adobe Firefly (Generative Fill): preenche uma área da imagem com IA. Usa créditos do Adobe Creative Cloud.",
            "parameters": {
                "type": "object",
                "properties": {
                    "imagem":  {"type": "string", "description": "Caminho da imagem de entrada (.png ou .jpg)"},
                    "prompt":  {"type": "string", "description": "O que gerar na área marcada (ex: 'blue sky with clouds')"},
                    "mascara": {"type": "string", "description": "Caminho de uma imagem de máscara (branco=preencher, preto=manter). Omita para preencher tudo."},
                },
                "required": ["imagem", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "firefly_texto_para_video",
            "description": "Gera um vídeo a partir de texto usando Adobe Firefly (consome créditos generativos do Creative Cloud). Requer plano com créditos disponíveis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Descrição do vídeo a gerar (em inglês)"},
                    "saida":  {"type": "string", "description": "Caminho de saída (.mp4). Omita para salvar na pasta temp."},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_site",
            "description": "Abre um site no navegador padrão.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa ou domínio"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_cliente",
            "description": "Salva ou atualiza informações de um cliente na memória local.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome":     {"type": "string", "description": "Nome do cliente"},
                    "contato":  {"type": "string", "description": "Email, WhatsApp ou telefone"},
                    "projeto":  {"type": "string", "description": "Projeto ou serviço contratado"},
                    "notas":    {"type": "string", "description": "Anotações importantes"},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_clientes",
            "description": "Lista todos os clientes salvos na memória.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_tarefa",
            "description": "Salva ou atualiza uma tarefa ou projeto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo":    {"type": "string"},
                    "cliente":   {"type": "string"},
                    "descricao": {"type": "string"},
                    "status":    {
                        "type": "string",
                        "enum": ["pendente", "em_andamento", "concluido", "cancelado"],
                    },
                    "prioridade": {
                        "type": "string",
                        "enum": ["baixa", "media", "alta", "urgente"],
                    },
                },
                "required": ["titulo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_tarefas",
            "description": "Lista tarefas salvas, com filtro opcional por status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "pendente | em_andamento | concluido | cancelado",
                    }
                },
                "required": [],
            },
        },
    },
    # ── Arquivos e sistema ────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "listar_arquivos",
            "description": "Lista arquivos e pastas de um diretório. Use '.' para o diretório atual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho da pasta, ex: C:\\Users\\ACER\\Desktop"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_arquivo",
            "description": "Lê o conteúdo de um arquivo de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho completo do arquivo"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escrever_arquivo",
            "description": "Cria ou sobrescreve um arquivo com o conteúdo informado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                    "conteudo": {"type": "string"},
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deletar_arquivo",
            "description": "Deleta um arquivo ou pasta vazia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_arquivo",
            "description": "Abre um arquivo ou pasta com o programa padrão do sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executar_comando",
            "description": "Executa um comando no sistema operacional (PowerShell/cmd). Use com cautela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando a executar"},
                },
                "required": ["comando"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_telegram",
            "description": "Envia uma mensagem para o dono pelo Telegram. Use quando ele pedir para te chamar no Telegram, enviar um aviso, lembrete ou notificação pelo Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mensagem": {"type": "string", "description": "Texto da mensagem a enviar"},
                },
                "required": ["mensagem"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_pasta",
            "description": "Cria uma pasta/diretório no sistema e registra para nunca esquecer o caminho.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {"type": "string", "description": "Caminho completo da pasta a criar. Ex: C:\\Users\\ACER\\Desktop\\MinhaPasta"},
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_arquivo_criado",
            "description": "Busca arquivos e pastas que eu já criei antes. Use quando o usuário perguntar onde está um arquivo ou pedir para abrir algo que foi criado anteriormente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Nome ou trecho do nome do arquivo/pasta a buscar"},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_arquivos_criados",
            "description": "Lista todos os arquivos e pastas que eu já criei. Use quando o usuário perguntar quais arquivos foram criados ou onde estão arquivos salvos.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def is_dangerous_tool(nome: str, argumentos) -> bool:
    if nome not in _DANGEROUS_TOOL_NAMES:
        return False
    args = argumentos if isinstance(argumentos, dict) else json.loads(argumentos)
    text = " ".join(str(v).lower() for v in args.values())
    return any(marker in text for marker in _DANGEROUS_TEXT_MARKERS)


# ── Executor ──────────────────────────────────────────────

def executar(nome: str, argumentos):
    args = argumentos if isinstance(argumentos, dict) else json.loads(argumentos)

    dispatch = {
        "ver_tela":        lambda: vision.descrever_tela(
                               args.get("pergunta",
                                        "O que está na tela? Descreva em detalhes em português.")),
        "clicar":          lambda: hands.clicar(args["x"], args["y"]),
        "clicar_duplo":    lambda: hands.clicar_duplo(args["x"], args["y"]),
        "digitar":         lambda: hands.digitar(args["texto"]),
        "pressionar_tecla": lambda: hands.pressionar_tecla(args["tecla"]),
        "atalho":          lambda: hands.atalho(args["teclas"]),
        "scroll":          lambda: hands.scroll(args["quantidade"]),
        "scroll_continuo": lambda: hands.scroll_continuo(args["direcao"]),
        "parar_scroll":    lambda: hands.parar_scroll(),
        "pesquisar_web":         lambda: _pesquisar_web(args["query"]),
        "pesquisar_no_navegador": lambda: _pesquisar_no_navegador(args["query"]),
        "pesquisar_no_youtube":   lambda: _pesquisar_no_youtube(args["query"]),
        "baixar_video_link":      lambda: _baixar_video_link(
            args["url"],
            args.get("pasta_saida", ""),
            args.get("qualidade", ""),
            bool(args.get("apenas_audio", False)),
        ),
        "pesquisar_canais_monetizados": lambda: _pesquisar_canais_monetizados(
            args["nicho"],
            int(args.get("limite", 8)),
        ),
        "modelar_videos_semelhantes": lambda: _modelar_videos_semelhantes(
            args["nicho"],
            args.get("referencia", ""),
            int(args.get("quantidade", 10)),
        ),
        "gerar_agenda_postagens_youtube": lambda: _gerar_agenda_postagens_youtube(
            args["nicho"],
            int(args.get("videos_semana", 4)),
            int(args.get("semanas", 4)),
            args.get("horario", "20:00"),
        ),
        "planejar_operacao_youtube": lambda: _planejar_operacao_youtube(
            args["nicho"],
            args.get("referencia", ""),
            int(args.get("videos_semana", 4)),
        ),
        "youtube_publicar_e_agendar": lambda: _youtube_publicar_e_agendar(
            args["caminho_video"],
            args["titulo"],
            args.get("descricao", ""),
            args.get("tags", []),
            args.get("privacidade", "private"),
            args.get("agendar_em", ""),
            args.get("categoria_id", ""),
        ),
        "youtube_sincronizar_planilha_metricas": lambda: _youtube_sincronizar_planilha_metricas(
            int(args.get("limite", 20)),
        ),
        "youtube_verificar_conta_conectada": lambda: _youtube_verificar_conta_conectada(),
        "gerar_lote_conteudo_youtube": lambda: _gerar_lote_conteudo_youtube(
            args["nicho"],
            int(args.get("quantidade", 12)),
        ),
        "youtube_inicializar_automacao_total": lambda: _youtube_inicializar_automacao_total(
            args["nicho"],
            int(args.get("videos_semana", 4)),
        ),
        "pesquisar_tendencias":  lambda: _pesquisar_tendencias_video(args.get("nicho", "")),
        "montar_video":          lambda: _montar_video(
                                     args["imagens"], args["saida"],
                                     float(args.get("duracao_por_imagem", 3)),
                                     args.get("musica", "")),
        "abrir_editor_video":              lambda: _abrir_editor_video(args.get("editor", "")),
        "abrir_creative_cloud":            lambda: _abrir_creative_cloud(),
        "listar_apps_adobe_instalados":    lambda: _listar_apps_adobe_instalados(),
        "instalar_app_adobe":              lambda: _instalar_app_adobe(args.get("app", "")),
        "creative_cloud_criar_projeto":    lambda: _creative_cloud_criar_projeto(
            args["nome_projeto"], args.get("tipo", "design")
        ),
        "creative_cloud_listar_projetos":  lambda: _creative_cloud_listar_projetos(),
        "preenchimento_generativo":   lambda: _preenchimento_generativo(
            args["imagem"], args["prompt"], args.get("area", "")
        ),
        "firefly_gerar_imagem":       lambda: _firefly_gerar_imagem(
            args["prompt"], args.get("saida", ""), args.get("estilo", "")
        ),
        "firefly_preenchimento":      lambda: _firefly_preenchimento(
            args["imagem"], args["prompt"], args.get("mascara", "")
        ),
        "firefly_texto_para_video":   lambda: _firefly_texto_para_video(
            args["prompt"], args.get("saida", "")
        ),
        "abrir_site":            lambda: hands.abrir_site(args["url"]),
        "salvar_cliente":  lambda: memory.salvar_cliente(
                               args["nome"],
                               args.get("contato", ""),
                               args.get("projeto", ""),
                               args.get("notas", "")),
        "listar_clientes": lambda: memory.listar_clientes(),
        "salvar_tarefa":   lambda: memory.salvar_tarefa(
                               args["titulo"],
                               args.get("cliente", ""),
                               args.get("descricao", ""),
                               args.get("status", "pendente"),
                               args.get("prioridade", "media")),
        "listar_tarefas":  lambda: memory.listar_tarefas(args.get("status")),
        # ── Arquivo e sistema ─────────────────────────────
        "listar_arquivos": lambda: _listar_arquivos(args["caminho"]),
        "ler_arquivo":     lambda: _ler_arquivo(args["caminho"]),
        "escrever_arquivo": lambda: _escrever_arquivo(args["caminho"], args["conteudo"]),
        "deletar_arquivo": lambda: _deletar_arquivo(args["caminho"]),
        "abrir_arquivo":   lambda: _abrir_arquivo(args["caminho"]),
        "executar_comando": lambda: _executar_comando(args["comando"]),
        "enviar_telegram":  lambda: _enviar_telegram(args["mensagem"]),
        "criar_pasta":              lambda: _criar_pasta(args["caminho"]),
        "buscar_arquivo_criado":    lambda: _buscar_arquivo_criado(args["nome"]),
        "listar_arquivos_criados":  lambda: memory.listar_arquivos_criados(),
    }

    fn = dispatch.get(nome)
    if fn:
        return fn()
    return f"Ferramenta '{nome}' não encontrada."


# ── Implementações de arquivo / sistema ───────────────────

import os as _os
import subprocess as _subprocess

def _listar_arquivos(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        itens = _os.listdir(path)
        linhas = []
        for item in sorted(itens):
            full = _os.path.join(path, item)
            tipo = "[pasta]" if _os.path.isdir(full) else "[arquivo]"
            linhas.append(f"{tipo} {item}")
        return "\n".join(linhas) if linhas else "Pasta vazia."
    except Exception as e:
        return f"Erro ao listar: {e}"

def _ler_arquivo(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            conteudo = f.read(8000)
        return conteudo if conteudo else "(arquivo vazio)"
    except Exception as e:
        return f"Erro ao ler arquivo: {e}"

def _escrever_arquivo(caminho: str, conteudo: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        # Registra no log para Evelyn nunca esquecer onde está
        try:
            memory.registrar_arquivo(path, tipo="arquivo")
        except Exception:
            pass
        return f"Arquivo salvo: {path}"
    except Exception as e:
        return f"Erro ao escrever arquivo: {e}"

def _deletar_arquivo(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        if _os.path.isdir(path):
            _os.rmdir(path)
        else:
            _os.remove(path)
        return f"Deletado: {path}"
    except Exception as e:
        return f"Erro ao deletar: {e}"

def _criar_pasta(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        _os.makedirs(path, exist_ok=True)
        # Registra no log para Evelyn nunca esquecer onde está
        try:
            memory.registrar_arquivo(path, tipo="pasta")
        except Exception:
            pass
        return f"Pasta criada: {path}"
    except Exception as e:
        return f"Erro ao criar pasta: {e}"

def _buscar_arquivo_criado(nome: str) -> str:
    resultados = memory.buscar_arquivo(nome)
    if not resultados:
        return f"Nenhum arquivo ou pasta com '{nome}' encontrado no registro."
    linhas = []
    for e in resultados:
        linhas.append(f"[{e['tipo']}] {e['nome']} → {e['caminho']}")
    return "\n".join(linhas)

def _abrir_arquivo(caminho: str) -> str:
    try:
        path = _os.path.expandvars(_os.path.expanduser(caminho))
        _os.startfile(path)
        return f"Abrindo: {path}"
    except Exception as e:
        return f"Erro ao abrir: {e}"

def _executar_comando(comando: str) -> str:
    try:
        result = _subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        saida = (result.stdout or "") + (result.stderr or "")
        return saida[:2000] if saida.strip() else "(sem saída)"
    except Exception as e:
        return f"Erro ao executar: {e}"
