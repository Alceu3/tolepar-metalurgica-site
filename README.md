# Floating Avatar Assistant

MVP local para Windows com Electron. A primeira versao entrega:

- avatar flutuante sempre visivel
- janela transparente sem moldura
- conversa por texto com fallback local
- fala por voz usando o sintetizador do Windows
- acesso a microfone e camera via permissoes do sistema
- tarefas basicas do PC com gatilhos seguros
- integracao pronta para Ollama local em `http://127.0.0.1:11434`

## Como rodar

```bash
npm install
npm start
```

## Telegram (opcional)

Para conversar com o avatar pelo Telegram, configure variaveis de ambiente antes de iniciar:

```powershell
$env:TELEGRAM_BOT_TOKEN = "SEU_TOKEN_DO_BOT"
$env:TELEGRAM_ALLOWED_USER_ID = "SEU_USER_ID"
npm start
```

Notas:
- `TELEGRAM_ALLOWED_USER_ID` limita respostas para o seu usuario.
- O bot responde texto e usa o mesmo cerebro local (tarefas + Ollama).

## OpenAI (opcional, recomendado para fallback)

Para usar OpenAI em vez de depender apenas do Ollama:

```powershell
$env:OPENAI_API_KEY = "SUA_CHAVE_OPENAI"
$env:OPENAI_MODEL = "gpt-4o-mini"
npm start
```

Notas:
- `gpt-4o-mini` e usado por padrao por ser um modelo mais economico.
- Se OpenAI falhar, o app tenta Ollama automaticamente.

## Como testar

- Clique em `Ouvir microfone` para validar permissao de audio.
- Clique em `Abrir camera` para validar permissao de video.
- Digite `abra o bloco de notas` ou `que horas sao`.
- Se o Ollama estiver ativo e com o modelo `llama3.2` baixado, o chat usa resposta local do modelo.

## Proximas etapas

- reconhecimento de voz offline
- memoria de conversas
- animacoes corporais mais avancadas
- tarefas do sistema com confirmacao
- avatar 3D ou Live2D