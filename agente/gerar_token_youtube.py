import json
import os
import pathlib
import secrets
import urllib.parse

import requests


def _load_env() -> None:
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def _ask_value(label: str, default: str = "") -> str:
    if default:
        raw = input(f"{label} [{default}]: ").strip()
        return raw or default
    return input(f"{label}: ").strip()


def main() -> None:
    _load_env()

    print("=== Gerador de Refresh Token YouTube (conta do usuario) ===")
    print("Use credenciais OAuth Client ID de tipo Desktop App no Google Cloud.")
    print()

    client_id = _ask_value("YOUTUBE_CLIENT_ID", os.environ.get("YOUTUBE_CLIENT_ID", ""))
    client_secret = _ask_value("YOUTUBE_CLIENT_SECRET", os.environ.get("YOUTUBE_CLIENT_SECRET", ""))
    redirect_uri = _ask_value("Redirect URI", "http://127.0.0.1")

    if not client_id or not client_secret:
        print("Erro: YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET sao obrigatorios.")
        return

    scope = "https://www.googleapis.com/auth/youtube"
    state = secrets.token_urlsafe(24)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    print("1) Abra este link no navegador e faca login na SUA conta:")
    print(auth_url)
    print()
    print("2) Depois de autorizar, copie o parametro 'code' da URL de retorno.")
    print("   Exemplo de URL de retorno:")
    print("   http://127.0.0.1/?state=...&code=4/0Abc...&scope=...")
    print()

    code = _ask_value("Cole aqui o CODE")
    if not code:
        print("Erro: code nao informado.")
        return

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )

    if token_resp.status_code != 200:
        print(f"Erro ao trocar code por token: {token_resp.status_code}")
        print(token_resp.text)
        return

    payload = token_resp.json()
    refresh_token = payload.get("refresh_token", "")
    access_token = payload.get("access_token", "")

    if not refresh_token:
        print("Nao veio refresh_token.")
        print("Dica: revogue acesso no Google Account > Security > Third-party apps e tente novamente com prompt=consent.")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print()
    print("=== TOKENS GERADOS ===")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
    print(f"ACCESS_TOKEN_TEMP={access_token}")
    print()
    print("Agora adicione no seu .env:")
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
