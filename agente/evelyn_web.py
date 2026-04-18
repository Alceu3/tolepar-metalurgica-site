"""
Servidor simples para Evelyn no celular
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, request, jsonify
import json
from datetime import datetime
import brain

app = Flask(__name__)

# HTML da interface
HTML = '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Evelyn</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui;background:linear-gradient(135deg,#667eea,#764ba2);height:100vh;display:flex;flex-direction:column}#container{display:flex;flex-direction:column;height:100%;max-width:600px;margin:0 auto;background:white;box-shadow:0 20px 60px rgba(0,0,0,0.3)}#header{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:20px;text-align:center}#header h1{font-size:28px;margin-bottom:5px}#chat{flex:1;overflow-y:auto;padding:15px;display:flex;flex-direction:column;gap:10px;background:#f5f5f5}#chat .msg{display:flex;animation:slideIn 0.3s ease-out}@keyframes slideIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}#chat .msg.user{justify-content:flex-end}#chat .msg-text{max-width:80%;padding:12px 16px;border-radius:18px;word-wrap:break-word;line-height:1.4;font-size:15px}#chat .msg.user .msg-text{background:#667eea;color:white;border-bottom-right-radius:4px}#chat .msg.bot .msg-text{background:white;color:#333;border:1px solid #ddd;border-bottom-left-radius:4px;box-shadow:0 1px 2px rgba(0,0,0,0.05)}#input-area{padding:15px;border-top:1px solid #ddd;background:white;display:flex;gap:8px;align-items:flex-end}#input{flex:1;border:1px solid #ddd;border-radius:24px;padding:12px 16px;font-size:15px;outline:none}#input:focus{border-color:#667eea}#send{background:#667eea;color:white;border:none;border-radius:24px;width:44px;height:44px;cursor:pointer;font-size:18px;flex-shrink:0}</style></head><body><div id="container"><div id="header"><h1>Evelyn</h1><div>Chat Local</div></div><div id="chat"></div><div id="input-area"><input type="text" id="input" placeholder="Digite..."><button id="send">→</button></div></div><script>const chat=document.getElementById("chat");const inp=document.getElementById("input");const send=document.getElementById("send");function addMsg(tipo,txt){const d=document.createElement("div");d.className="msg "+tipo;const t=document.createElement("div");t.className="msg-text";t.textContent=txt;d.appendChild(t);chat.appendChild(d);chat.scrollTop=chat.scrollHeight}function enviar(){const txt=inp.value.trim();if(!txt)return;addMsg("user",txt);inp.value="";fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({texto:txt})}).then(r=>r.json()).then(d=>{addMsg("bot",d.resposta)}).catch(e=>addMsg("bot","Erro: "+e))}send.onclick=enviar;inp.onkeypress=e=>{if(e.key==="Enter")enviar()}</script></body></html>'''

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    texto = data.get("texto", "").strip()
    if not texto:
        return jsonify({"resposta": "Digite algo!"})
    resposta = brain.processar(texto)
    return jsonify({"resposta": resposta})

if __name__ == "__main__":
    print("\n[OK] Evelyn Web rodando")
    print("[*] PC: http://localhost:5000")
    print("[*] Celular: http://192.168.18.7:5000")
    print("")
    app.run(host="0.0.0.0", port=5000, debug=False)
