"""
Ponte ARIA local <-> ARIA nuvem.

Uso:
  python local_bridge.py pull
  python local_bridge.py push PED-20260415-120000-001 "C:\\caminho\\da\\pasta"
"""
import os
import re
import io
import json
import sys
import zipfile
from pathlib import Path

import requests

import config


def _sanitize(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._ -]", "", s)
    return re.sub(r"\s+", "_", s).strip("_") or "sem_nome"


def _base_url() -> str:
    url = str(getattr(config, "CLOUD_API_URL", "") or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("CLOUD_API_URL não configurado no .env")
    return url


def _headers() -> dict:
    token = str(getattr(config, "CLOUD_API_TOKEN", "") or "").strip()
    h = {"Accept": "application/json"}
    if token:
        h["X-API-Token"] = token
    return h


def pull_orders() -> str:
    base = _base_url()
    projects_dir = Path(getattr(config, "LOCAL_PROJECTS_DIR", "")).resolve()
    projects_dir.mkdir(parents=True, exist_ok=True)

    r = requests.get(f"{base}/api/pedidos", params={"status": "novo"}, headers=_headers(), timeout=30)
    r.raise_for_status()
    pedidos = r.json().get("pedidos", [])
    if not pedidos:
        return "Sem pedidos novos na nuvem."

    criados = 0
    for p in pedidos:
        pedido_id = p.get("id", "")
        cliente = _sanitize(p.get("cliente", "cliente"))
        servico = _sanitize(p.get("servico", "servico"))
        pasta = projects_dir / f"{pedido_id}__{cliente}__{servico}"
        pasta.mkdir(parents=True, exist_ok=True)

        pedido_json = pasta / "pedido.json"
        with open(pedido_json, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)

        status_payload = {
            "status": "em_execucao_local",
            "pasta_local": str(pasta),
            "resumo_entrega": "",
        }
        u = requests.patch(
            f"{base}/api/pedidos/{pedido_id}/status",
            json=status_payload,
            headers={**_headers(), "Content-Type": "application/json"},
            timeout=30,
        )
        u.raise_for_status()
        criados += 1

    return f"{criados} pedido(s) puxado(s) da nuvem para {projects_dir}."


def _zip_dir(folder: Path) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(folder):
            for fn in files:
                fp = Path(root) / fn
                rel = fp.relative_to(folder)
                zf.write(fp, arcname=str(rel))
    return mem.getvalue()


def push_result(order_id: str, folder_path: str) -> str:
    base = _base_url()
    pasta = Path(folder_path).resolve()
    if not pasta.exists() or not pasta.is_dir():
        raise RuntimeError(f"Pasta inválida: {pasta}")

    zip_bytes = _zip_dir(pasta)
    files = {"arquivo": (f"{order_id}.zip", zip_bytes, "application/zip")}

    r = requests.post(
        f"{base}/api/pedidos/{order_id}/resultado",
        headers=_headers(),
        files=files,
        timeout=120,
    )
    r.raise_for_status()

    status_payload = {
        "status": "entregue_para_nuvem",
        "pasta_local": str(pasta),
        "resumo_entrega": "Projeto finalizado e enviado pela ARIA local.",
    }
    u = requests.patch(
        f"{base}/api/pedidos/{order_id}/status",
        json=status_payload,
        headers={**_headers(), "Content-Type": "application/json"},
        timeout=30,
    )
    u.raise_for_status()
    return f"Pedido {order_id} enviado para a nuvem com sucesso."


def _usage() -> str:
    return (
        "Uso:\n"
        "  python local_bridge.py pull\n"
        "  python local_bridge.py push <PEDIDO_ID> <PASTA_PROJETO>\n"
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print(_usage())
            raise SystemExit(1)

        cmd = sys.argv[1].lower().strip()
        if cmd == "pull":
            print(pull_orders())
        elif cmd == "push":
            if len(sys.argv) < 4:
                print(_usage())
                raise SystemExit(1)
            print(push_result(sys.argv[2], sys.argv[3]))
        else:
            print(_usage())
            raise SystemExit(1)
    except Exception as ex:
        print(f"Erro: {ex}")
        raise SystemExit(2)
