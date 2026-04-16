import base64
import requests
from PIL import ImageGrab

# ===================== CONFIGURAÇÃO =====================
OPENROUTER_API_KEY = "sua-chave-aqui"  # https://openrouter.ai/keys
MODEL = "google/gemini-2.0-flash-exp:free"  # modelo gratuito com visão
PERGUNTA = "O que você vê nessa tela? Descreva em detalhes."
# ========================================================

def capturar_tela():
    img = ImageGrab.grab()
    img.save("screen_temp.png")
    with open("screen_temp.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def perguntar_sobre_tela(imagem_b64, pergunta):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{imagem_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": pergunta
                    }
                ]
            }
        ]
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload
    )

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"Erro {response.status_code}: {response.text}"

if __name__ == "__main__":
    print("Capturando tela...")
    imagem = capturar_tela()

    print("Enviando para o modelo...")
    resposta = perguntar_sobre_tela(imagem, PERGUNTA)

    print("\n=== RESPOSTA DO MODELO ===")
    print(resposta)
