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