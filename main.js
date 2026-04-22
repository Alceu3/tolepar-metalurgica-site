const { app, BrowserWindow, ipcMain, shell, desktopCapturer } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFile } = require('child_process');

let mainWindow;
let telegramOffset = 0;
let telegramPollTimer;
let screenCaptureTimer;
let latestScreenBase64 = null;
let memoryFilePath;
let assistantMemory = { history: [] };
let businessFilePath;
let businessStore = { clients: [] };

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_ALLOWED_USER_ID = process.env.TELEGRAM_ALLOWED_USER_ID;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const OPENAI_MODEL = process.env.OPENAI_MODEL || 'gpt-4o-mini';
const OPENAI_VISION_MODEL = process.env.OPENAI_VISION_MODEL || 'gpt-4o-mini';
const OLLAMA_URL = 'http://127.0.0.1:11434/api/chat';

function initializeMemoryStore() {
  memoryFilePath = path.join(app.getPath('userData'), 'assistant-memory.json');

  try {
    if (fs.existsSync(memoryFilePath)) {
      const raw = fs.readFileSync(memoryFilePath, 'utf8');
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed?.history)) {
        assistantMemory = { history: parsed.history.slice(-30) };
      }
    }
  } catch (error) {
    console.error('Memory load error:', error.message);
    assistantMemory = { history: [] };
  }
}

function saveMemoryStore() {
  if (!memoryFilePath) {
    return;
  }

  try {
    fs.writeFileSync(memoryFilePath, JSON.stringify(assistantMemory, null, 2), 'utf8');
  } catch (error) {
    console.error('Memory save error:', error.message);
  }
}

function pushMemory(role, content) {
  assistantMemory.history.push({ role, content, at: new Date().toISOString() });
  if (assistantMemory.history.length > 30) {
    assistantMemory.history = assistantMemory.history.slice(-30);
  }
  saveMemoryStore();
}

function buildMemoryContext() {
  if (!assistantMemory.history.length) {
    return 'Memoria recente vazia.';
  }

  return assistantMemory.history
    .slice(-12)
    .map((item) => `${item.role}: ${item.content}`)
    .join('\n');
}

function initializeBusinessStore() {
  businessFilePath = path.join(app.getPath('userData'), 'assistant-business.json');

  try {
    if (fs.existsSync(businessFilePath)) {
      const raw = fs.readFileSync(businessFilePath, 'utf8');
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed?.clients)) {
        businessStore = { clients: parsed.clients };
      }
    }
  } catch (error) {
    console.error('Business store load error:', error.message);
    businessStore = { clients: [] };
  }
}

function saveBusinessStore() {
  if (!businessFilePath) {
    return;
  }

  try {
    fs.writeFileSync(businessFilePath, JSON.stringify(businessStore, null, 2), 'utf8');
  } catch (error) {
    console.error('Business store save error:', error.message);
  }
}

function normalizeName(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function findClientByName(name) {
  const key = normalizeName(name);
  return businessStore.clients.find((c) => normalizeName(c.name) === key) || null;
}

function upsertClientBase(name, contact = '', service = '') {
  const existing = findClientByName(name);
  const now = new Date().toISOString();

  if (existing) {
    if (contact) existing.contact = contact;
    if (service) existing.service = service;
    existing.updatedAt = now;
    saveBusinessStore();
    return existing;
  }

  const created = {
    id: `cli_${Date.now()}`,
    name: String(name || '').trim(),
    contact: String(contact || '').trim(),
    service: String(service || '').trim(),
    status: 'lead',
    agenda: '',
    proposal: '',
    lastMessage: '',
    workspacePath: '',
    reviewApprovedAt: '',
    deliveredAt: '',
    createdAt: now,
    updatedAt: now
  };

  businessStore.clients.push(created);
  saveBusinessStore();
  return created;
}

function safeFolderName(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9\s_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\s/g, '_')
    .slice(0, 80);
}

function ensureServiceWorkspace(clientName, serviceDescription = '') {
  const root = resolveUserPath(path.join('servicos-clientes', safeFolderName(clientName) || 'cliente'));
  fs.mkdirSync(root, { recursive: true });

  const summaryPath = path.join(root, 'resumo-servico.txt');
  if (!fs.existsSync(summaryPath)) {
    const content = [
      `Cliente: ${clientName}`,
      `Servico: ${serviceDescription || '-'}`,
      `Criado em: ${new Date().toLocaleString('pt-BR')}`,
      '',
      'Checklist:',
      '- [ ] Execucao concluida',
      '- [ ] Revisao interna',
      '- [ ] OK do responsavel',
      '- [ ] Entrega para cliente'
    ].join('\n');
    fs.writeFileSync(summaryPath, content, 'utf8');
  }

  const deliveryPath = path.join(root, 'mensagem-entrega.txt');
  if (!fs.existsSync(deliveryPath)) {
    const message = [
      `Ola, ${clientName}.`,
      '',
      'Seu servico foi finalizado e revisado com sucesso.',
      'Fico a disposicao para ajustes finos e suporte.',
      '',
      'Obrigado.'
    ].join('\n');
    fs.writeFileSync(deliveryPath, message, 'utf8');
  }

  return root;
}

function buildBusinessContext() {
  if (!businessStore.clients.length) {
    return 'Pipeline comercial vazio.';
  }

  return businessStore.clients
    .slice(-8)
    .map((c) => {
      return `${c.name} | status: ${c.status} | servico: ${c.service || '-'} | agenda: ${c.agenda || '-'} | proposta: ${c.proposal || '-'}`;
    })
    .join('\n');
}

function getDesktopRoot() {
  return os.homedir();
}

function resolveUserPath(inputPath) {
  const raw = String(inputPath || '').trim();

  if (!raw) {
    return getDesktopRoot();
  }

  if (path.isAbsolute(raw)) {
    return path.normalize(raw);
  }

  return path.normalize(path.join(getDesktopRoot(), raw));
}

function listDirectory(targetPath) {
  const resolved = resolveUserPath(targetPath);
  const entries = fs.readdirSync(resolved, { withFileTypes: true });
  const preview = entries
    .slice(0, 120)
    .map((entry) => (entry.isDirectory() ? `[DIR] ${entry.name}` : entry.name));

  return `Pasta: ${resolved}\n${preview.join('\n') || '(vazia)'}`;
}

function readTextFile(targetPath) {
  const resolved = resolveUserPath(targetPath);
  const data = fs.readFileSync(resolved, 'utf8');
  const limited = data.length > 14000 ? `${data.slice(0, 14000)}\n\n[conteudo truncado]` : data;
  return `Arquivo: ${resolved}\n\n${limited}`;
}

function writeTextFile(targetPath, content) {
  const resolved = resolveUserPath(targetPath);
  const dirPath = path.dirname(resolved);
  fs.mkdirSync(dirPath, { recursive: true });
  fs.writeFileSync(resolved, String(content || ''), 'utf8');
  return `Arquivo salvo: ${resolved}`;
}

function replaceInTextFile(targetPath, fromText, toText) {
  const resolved = resolveUserPath(targetPath);
  const source = fs.readFileSync(resolved, 'utf8');
  const needle = String(fromText || '');
  if (!needle) {
    throw new Error('Texto de busca vazio.');
  }

  if (!source.includes(needle)) {
    throw new Error('Texto para substituir nao encontrado no arquivo.');
  }

  const output = source.split(needle).join(String(toText || ''));
  fs.writeFileSync(resolved, output, 'utf8');
  return `Substituicao aplicada em: ${resolved}`;
}

function scaffoldWebProject(projectName) {
  const safeName = String(projectName || 'meu-site')
    .trim()
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '-');

  const root = resolveUserPath(path.join('sites', safeName || 'meu-site'));
  fs.mkdirSync(root, { recursive: true });

  const html = `<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${safeName || 'meu-site'}</title>
    <link rel="stylesheet" href="./styles.css" />
  </head>
  <body>
    <header class="hero">
      <h1>Site Base</h1>
      <p>Projeto HTML, CSS e JavaScript pronto para evoluir.</p>
      <button id="action-btn">Clique aqui</button>
    </header>

    <main class="content">
      <section class="card">
        <h2>Comece a programar</h2>
        <p>Edite os arquivos e construa o seu produto.</p>
      </section>
    </main>

    <script src="./script.js"></script>
  </body>
</html>
`;

  const css = `:root {
  --bg: #f3f6fb;
  --ink: #102033;
  --accent: #1f7ae0;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "Segoe UI", Tahoma, sans-serif;
  background: linear-gradient(120deg, #eef4ff, var(--bg));
  color: var(--ink);
}

.hero {
  padding: 48px 20px;
  text-align: center;
}

.hero h1 {
  margin: 0 0 12px;
  font-size: 2rem;
}

#action-btn {
  border: none;
  border-radius: 10px;
  padding: 10px 16px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}

.content {
  max-width: 920px;
  margin: 0 auto;
  padding: 12px 20px 40px;
}

.card {
  background: #fff;
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 10px 30px rgba(13, 38, 66, 0.1);
}
`;

  const js = `const button = document.getElementById('action-btn');

button?.addEventListener('click', () => {
  alert('Projeto base pronto. Vamos construir juntos.');
});
`;

  fs.writeFileSync(path.join(root, 'index.html'), html, 'utf8');
  fs.writeFileSync(path.join(root, 'styles.css'), css, 'utf8');
  fs.writeFileSync(path.join(root, 'script.js'), js, 'utf8');

  return root;
}

function searchFiles(rootPath, keyword) {
  const resolvedRoot = resolveUserPath(rootPath);
  const query = String(keyword || '').toLowerCase().trim();
  const results = [];

  function walk(currentPath, depth) {
    if (depth > 5 || results.length >= 80) {
      return;
    }

    let items;
    try {
      items = fs.readdirSync(currentPath, { withFileTypes: true });
    } catch (_error) {
      return;
    }

    for (const item of items) {
      if (results.length >= 80) {
        break;
      }

      const fullPath = path.join(currentPath, item.name);
      const matchesName = item.name.toLowerCase().includes(query);
      if (matchesName) {
        results.push(fullPath);
      }

      if (item.isDirectory()) {
        walk(fullPath, depth + 1);
      }
    }
  }

  walk(resolvedRoot, 0);
  return `Busca em: ${resolvedRoot}\nTermo: ${query}\n\n${results.join('\n') || 'Nenhum arquivo encontrado.'}`;
}

function parseLocalCommand(prompt) {
  const text = String(prompt || '').trim();

  if (/^listar\s+/i.test(text)) {
    return { type: 'list', arg: text.replace(/^listar\s+/i, '') };
  }

  if (/^ler\s+/i.test(text)) {
    return { type: 'read', arg: text.replace(/^ler\s+/i, '') };
  }

  const findMatch = text.match(/^buscar\s+(.+?)\s+em\s+(.+)$/i);
  if (findMatch) {
    return { type: 'search', keyword: findMatch[1], root: findMatch[2] };
  }

  const createWebMatch = text.match(/^criar\s+projeto\s+(?:site|html|web)\s+(.+)$/i);
  if (createWebMatch) {
    return { type: 'create-web-project', name: createWebMatch[1].trim() };
  }

  const writeMatch = text.match(/^escrever\s+arquivo\s+(.+?)\s*::\s*([\s\S]+)$/i);
  if (writeMatch) {
    return { type: 'write-file', target: writeMatch[1].trim(), content: writeMatch[2] };
  }

  const replaceMatch = text.match(/^substituir\s+arquivo\s+(.+?)\s*::\s*([\s\S]+?)\s*=>\s*([\s\S]+)$/i);
  if (replaceMatch) {
    return {
      type: 'replace-file',
      target: replaceMatch[1].trim(),
      fromText: replaceMatch[2],
      toText: replaceMatch[3]
    };
  }

  return null;
}

function parseBusinessCommand(prompt) {
  const text = String(prompt || '').trim();
  if (!text) return null;

  const takeMatch = text.match(/^pegar\s+servico\s+(.+)$/i) || text.match(/^iniciar\s+servico\s+(.+)$/i);
  if (takeMatch?.[1]) {
    const parts = takeMatch[1].split('|').map((p) => p.trim()).filter(Boolean);
    return {
      type: 'take-service',
      name: parts[0] || '',
      service: parts[1] || ''
    };
  }

  const reviewMatch = text.match(/^revisar\s+servico\s+(.+)$/i);
  if (reviewMatch?.[1]) {
    return { type: 'review-service', name: reviewMatch[1].trim() };
  }

  const approveMatch = text.match(/^ok\s+servico\s+(.+)$/i) || text.match(/^aprovar\s+servico\s+(.+)$/i);
  if (approveMatch?.[1]) {
    return { type: 'approve-service', name: approveMatch[1].trim() };
  }

  const deliverMatch = text.match(/^entregar\s+servico\s+(.+)$/i) || text.match(/^enviar\s+servico\s+(.+)$/i);
  if (deliverMatch?.[1]) {
    return { type: 'deliver-service', name: deliverMatch[1].trim() };
  }

  const registerMatch = text.match(/^cadastrar\s+cliente\s+(.+)$/i);
  if (registerMatch?.[1]) {
    const parts = registerMatch[1].split('|').map((p) => p.trim()).filter(Boolean);
    return {
      type: 'register-client',
      name: parts[0] || '',
      contact: parts[1] || '',
      service: parts[2] || ''
    };
  }

  const scheduleMatch = text.match(/^agendar\s+servico\s+(.+)$/i) || text.match(/^agendar\s+(.+)$/i);
  if (scheduleMatch?.[1]) {
    const parts = scheduleMatch[1].split('|').map((p) => p.trim()).filter(Boolean);
    return {
      type: 'schedule-service',
      name: parts[0] || '',
      when: parts[1] || '',
      details: parts[2] || ''
    };
  }

  const proposalMatch = text.match(/^criar\s+proposta\s+(.+)$/i) || text.match(/^proposta\s+(.+)$/i);
  if (proposalMatch?.[1]) {
    const parts = proposalMatch[1].split('|').map((p) => p.trim()).filter(Boolean);
    return {
      type: 'create-proposal',
      name: parts[0] || '',
      value: parts[1] || '',
      details: parts[2] || ''
    };
  }

  const talkMatch = text.match(/^conversa\s+cliente\s+(.+)$/i) || text.match(/^mensagem\s+cliente\s+(.+)$/i);
  if (talkMatch?.[1]) {
    const parts = talkMatch[1].split('|').map((p) => p.trim()).filter(Boolean);
    return {
      type: 'client-message',
      name: parts[0] || '',
      message: parts[1] || ''
    };
  }

  const closeMatch = text.match(/^fechar\s+servico\s+(.+)$/i) || text.match(/^fechar\s+cliente\s+(.+)$/i);
  if (closeMatch?.[1]) {
    return { type: 'close-service', name: closeMatch[1].trim() };
  }

  if (/^(pipeline|listar\s+clientes|painel\s+comercial)$/i.test(text)) {
    return { type: 'list-pipeline' };
  }

  return null;
}

async function runBusinessCommand(command) {
  if (!command) {
    return 'Comando comercial vazio.';
  }

  if (command.type === 'take-service') {
    if (!command.name) {
      return 'Use: pegar servico Nome do Cliente | descricao do servico';
    }

    const client = upsertClientBase(command.name, '', command.service || '');
    if (command.service) {
      client.service = command.service;
    }

    client.workspacePath = ensureServiceWorkspace(client.name, client.service);
    client.status = 'em execucao';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Servico em execucao para ${client.name}. Pasta criada em: ${client.workspacePath}. Quando terminar, use: revisar servico ${client.name}`;
  }

  if (command.type === 'review-service') {
    if (!command.name) {
      return 'Use: revisar servico Nome do Cliente';
    }

    const client = findClientByName(command.name);
    if (!client) {
      return `Nao encontrei cliente com nome ${command.name}.`;
    }

    client.workspacePath = client.workspacePath || ensureServiceWorkspace(client.name, client.service);
    client.status = 'em revisao';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();

    await shell.openPath(client.workspacePath);
    return `Revisao iniciada para ${client.name}. Confirme com: ok servico ${client.name}`;
  }

  if (command.type === 'approve-service') {
    if (!command.name) {
      return 'Use: ok servico Nome do Cliente';
    }

    const client = findClientByName(command.name);
    if (!client) {
      return `Nao encontrei cliente com nome ${command.name}.`;
    }

    client.status = 'aprovado';
    client.reviewApprovedAt = new Date().toISOString();
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `OK registrado para ${client.name}. Proximo passo: entregar servico ${client.name}`;
  }

  if (command.type === 'deliver-service') {
    if (!command.name) {
      return 'Use: entregar servico Nome do Cliente';
    }

    const client = findClientByName(command.name);
    if (!client) {
      return `Nao encontrei cliente com nome ${command.name}.`;
    }

    if (client.status !== 'aprovado' && client.status !== 'fechado') {
      return `O servico de ${client.name} ainda nao esta aprovado. Rode: ok servico ${client.name}`;
    }

    client.workspacePath = client.workspacePath || ensureServiceWorkspace(client.name, client.service);
    const deliveryMessage = `Ola, ${client.name}. Seu servico foi concluido e revisado. Podemos finalizar a entrega agora.`;
    const contactDigits = String(client.contact || '').replace(/\D/g, '');
    if (contactDigits.length >= 10) {
      await shell.openExternal(`https://wa.me/55${contactDigits}?text=${encodeURIComponent(deliveryMessage)}`);
    } else {
      await shell.openPath(client.workspacePath);
    }

    client.status = 'entregue';
    client.deliveredAt = new Date().toISOString();
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Entrega executada para ${client.name}. Status atualizado para entregue.`;
  }

  if (command.type === 'register-client') {
    if (!command.name) {
      return 'Use: cadastrar cliente Nome | Contato | Servico';
    }

    const client = upsertClientBase(command.name, command.contact, command.service);
    client.status = 'cadastro';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Cliente cadastrado: ${client.name}. Proximo passo sugerido: agendar servico ${client.name} | data/hora | detalhes`;
  }

  if (command.type === 'schedule-service') {
    if (!command.name || !command.when) {
      return 'Use: agendar servico Nome | data/hora | detalhes';
    }

    const client = upsertClientBase(command.name);
    client.agenda = command.details ? `${command.when} - ${command.details}` : command.when;
    client.status = 'agendado';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Servico agendado para ${client.name}: ${client.agenda}. Proximo passo: criar proposta ${client.name} | valor | detalhes`;
  }

  if (command.type === 'create-proposal') {
    if (!command.name || !command.value) {
      return 'Use: criar proposta Nome | valor | detalhes';
    }

    const client = upsertClientBase(command.name);
    const proposal = `Valor ${command.value}${command.details ? ` | ${command.details}` : ''}`;
    client.proposal = proposal;
    client.status = 'proposta enviada';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Proposta registrada para ${client.name}: ${proposal}. Proximo passo: conversa cliente ${client.name} | mensagem de follow-up`;
  }

  if (command.type === 'client-message') {
    if (!command.name || !command.message) {
      return 'Use: conversa cliente Nome | mensagem';
    }

    const client = upsertClientBase(command.name);
    client.lastMessage = command.message;
    client.status = 'em negociacao';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Mensagem registrada para ${client.name}. Proximo passo: fechar servico ${client.name} quando o cliente aprovar.`;
  }

  if (command.type === 'close-service') {
    if (!command.name) {
      return 'Use: fechar servico Nome';
    }

    const client = findClientByName(command.name);
    if (!client) {
      return `Nao encontrei cliente com nome ${command.name}.`;
    }

    client.status = 'fechado';
    client.updatedAt = new Date().toISOString();
    saveBusinessStore();
    return `Servico fechado com ${client.name}. Execucao autorizada.`;
  }

  if (command.type === 'list-pipeline') {
    const lines = businessStore.clients.map((c) => {
      return `- ${c.name} | ${c.status} | agenda: ${c.agenda || '-'} | proposta: ${c.proposal || '-'} | pasta: ${c.workspacePath || '-'} | ok: ${c.reviewApprovedAt ? 'sim' : 'nao'} | entregue: ${c.deliveredAt ? 'sim' : 'nao'}`;
    });

    return lines.length ? `Pipeline comercial:\n${lines.join('\n')}` : 'Pipeline comercial vazio.';
  }

  return 'Comando comercial nao reconhecido.';
}

function runPowerShell(script) {
  return new Promise((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { windowsHide: true },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error(stderr || error.message));
          return;
        }

        resolve((stdout || '').trim());
      }
    );
  });
}

function parseAutomationCommand(prompt) {
  const raw = String(prompt || '').trim();
  if (!raw) return null;

  const n = normalizePt(raw);

  const searchMatch = raw.match(/(?:buscar|pesquisar|procura(?:r)?|google)(?:\s+no\s+navegador|\s+na\s+internet|\s+no\s+google)?\s+(.+)/i);
  if (searchMatch?.[1]) {
    return { type: 'browser-search', query: searchMatch[1].trim() };
  }

  if (/(cursor|mouse)/i.test(n) && /(mover|move|mexe|mexa)/i.test(n)) {
    const pxMatch = n.match(/(\d+)\s*(px|pixels?)?/i);
    const pixels = Math.min(1200, Math.max(20, Number(pxMatch?.[1] || 140)));

    if (/esquerda/i.test(n)) return { type: 'cursor-move', dx: -pixels, dy: 0 };
    if (/direita/i.test(n)) return { type: 'cursor-move', dx: pixels, dy: 0 };
    if (/cima/i.test(n)) return { type: 'cursor-move', dx: 0, dy: -pixels };
    if (/(baixo|baixo\b|baixo$)/i.test(n)) return { type: 'cursor-move', dx: 0, dy: pixels };
  }

  if (/(rola|rolar|scroll)/i.test(n) && /(tela|pagina|página|site|navegador)/i.test(n)) {
    const stepsMatch = n.match(/(\d+)\s*(vez|vezes|passos?)?/i);
    const steps = Math.min(25, Math.max(1, Number(stepsMatch?.[1] || 3)));
    const up = /cima/i.test(n);
    const down = /baixo/i.test(n);

    if (up || down) {
      return { type: 'scroll', direction: up ? 'up' : 'down', steps };
    }
  }

  return null;
}

async function runAutomationCommand(command) {
  if (!command) {
    return 'Comando de automacao vazio.';
  }

  if (command.type === 'browser-search') {
    const q = String(command.query || '').trim();
    if (!q) {
      return 'Me diga o que pesquisar no navegador.';
    }

    const url = `https://www.google.com/search?q=${encodeURIComponent(q)}`;
    await shell.openExternal(url);
    return `Pesquisando no navegador: ${q}`;
  }

  if (command.type === 'cursor-move') {
    const dx = Number(command.dx || 0);
    const dy = Number(command.dy || 0);
    const script = [
      'Add-Type -AssemblyName System.Windows.Forms',
      'Add-Type -AssemblyName System.Drawing',
      '$p = [System.Windows.Forms.Cursor]::Position',
      `$nx = [Math]::Max(0, $p.X + (${dx}))`,
      `$ny = [Math]::Max(0, $p.Y + (${dy}))`,
      '[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($nx, $ny)',
      'Write-Output "ok"'
    ].join('; ');

    await runPowerShell(script);
    return 'Cursor movido.';
  }

  if (command.type === 'scroll') {
    const direction = command.direction === 'up' ? 1 : -1;
    const steps = Math.min(25, Math.max(1, Number(command.steps || 3)));
    const delta = 120 * direction * steps;
    const script = [
      'Add-Type @"',
      'using System.Runtime.InteropServices;',
      'public static class NativeMouse {',
      '  [DllImport("user32.dll", CharSet = CharSet.Auto, CallingConvention = CallingConvention.StdCall)]',
      '  public static extern void mouse_event(long dwFlags, long dx, long dy, long cButtons, long dwExtraInfo);',
      '}',
      '"@',
      `[NativeMouse]::mouse_event(0x0800, 0, 0, ${delta}, 0)`,
      'Write-Output "ok"'
    ].join('; ');

    await runPowerShell(script);
    return command.direction === 'up' ? 'Rolando tela para cima.' : 'Rolando tela para baixo.';
  }

  return 'Nao entendi o comando de automacao.';
}

function normalizePt(text) {
  return String(text || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function getLastUserPrompt() {
  for (let i = assistantMemory.history.length - 1; i >= 0; i -= 1) {
    const item = assistantMemory.history[i];
    if (item?.role === 'user' && item?.content) {
      return String(item.content);
    }
  }

  return '';
}

function hasVideoIntent(text) {
  const n = normalizePt(text);
  return (
    n.includes('video') ||
    n.includes('youtube') ||
    n.includes('short') ||
    n.includes('reel') ||
    n.includes('tiktok')
  );
}

function cleanVideoQuery(text) {
  return String(text || '')
    .replace(/escreve\s+na\s+caixa\s+de\s+mensagem/gi, ' ')
    .replace(/(video|videos|youtube|procura|pesquisa|buscar|busca|quero|me\s+mostra)/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function inferVideoSearch(prompt) {
  const raw = String(prompt || '').trim();
  if (!raw) return null;

  const lastUser = getLastUserPrompt();
  const isRefinement = raw.split(/\s+/).length <= 4;
  const contextHasVideo = hasVideoIntent(lastUser);
  const currentHasVideo = hasVideoIntent(raw);

  if (!currentHasVideo && !(isRefinement && contextHasVideo)) {
    return null;
  }

  const merged = currentHasVideo ? raw : `${lastUser} ${raw}`;
  let query = cleanVideoQuery(merged);

  const n = normalizePt(query);
  const wantsVertical = n.includes('vertical') || n.includes('short') || n.includes('reel');
  if (wantsVertical && !/shorts?/i.test(query)) {
    query = `${query} shorts vertical`;
  }

  if (query.length < 3) {
    return null;
  }

  return { query };
}

async function captureScreenSnapshot() {
  try {
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 1280, height: 720 }
    });

    if (!sources.length) {
      return;
    }

    latestScreenBase64 = sources[0].thumbnail.toPNG().toString('base64');
  } catch (error) {
    console.error('Screen capture error:', error.message);
  }
}

function startScreenWatcher() {
  captureScreenSnapshot();
  screenCaptureTimer = setInterval(captureScreenSnapshot, 2000);
}

function stopScreenWatcher() {
  clearInterval(screenCaptureTimer);
}

function wantsScreenAnalysis(prompt) {
  const text = String(prompt || '').toLowerCase();
  return (
    text.includes('minha tela') ||
    text.includes('o que tem na tela') ||
    text.includes('visao da tela') ||
    text.includes('analisar tela')
  );
}

function createWindow() {
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
  
  const windowWidth = 250;
  const windowHeight = 420;
  const x = Math.round(screenWidth - windowWidth - 20);
  const y = Math.round(screenHeight / 2 - windowHeight / 2);
  
  mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x: x,
    y: y,
    minWidth: 220,
    minHeight: 320,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    resizable: true,
    hasShadow: false,
    show: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.setAlwaysOnTop(true, 'screen-saver');
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

function launchProgram(program) {
  return new Promise((resolve, reject) => {
    execFile(program, (error) => {
      if (error) {
        reject(error);
        return;
      }

      resolve();
    });
  });
}

async function runSystemTask(task) {
  switch (task) {
    case 'open-notepad':
      await launchProgram('notepad.exe');
      return 'Bloco de Notas aberto.';
    case 'open-calculator':
      await launchProgram('calc.exe');
      return 'Calculadora aberta.';
    case 'open-browser':
      await shell.openExternal('https://www.bing.com');
      return 'Navegador aberto.';
    case 'tell-time':
      return `Agora sao ${new Date().toLocaleTimeString('pt-BR')}.`;
    default:
      throw new Error('Tarefa nao suportada.');
  }
}

function inferTask(text) {
  const normalized = String(text || '').toLowerCase();

  if (normalized.includes('bloco') || normalized.includes('notepad')) {
    return 'open-notepad';
  }

  if (normalized.includes('calculadora') || normalized.includes('calcular')) {
    return 'open-calculator';
  }

  if (normalized.includes('navegador') || normalized.includes('browser')) {
    return 'open-browser';
  }

  if (normalized.includes('hora')) {
    return 'tell-time';
  }

  return null;
}

async function askOllama(prompt) {
  try {
    const response = await fetch(OLLAMA_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'llama3.2',
        stream: false,
        messages: [
          {
            role: 'system',
            content: `Voce e Aria, assistente proativa de operacao comercial e execucao no Windows.\nFoque em: cadastro de cliente, agenda de servico, proposta, follow-up, fechamento e proximo passo acionavel.\nResponda em portugues, de forma curta e objetiva.\n\nMemoria recente:\n${buildMemoryContext()}\n\nPipeline comercial:\n${buildBusinessContext()}`
          },
          {
            role: 'user',
            content: prompt
          }
        ]
      })
    });

    if (!response.ok) {
      throw new Error('Ollama indisponivel');
    }

    const data = await response.json();
    return data.message?.content?.trim() || 'Desculpe, nao consegui processar.';
  } catch (_error) {
    return 'Ollama nao esta disponivel. Verifique se esta rodando em http://127.0.0.1:11434';
  }
}

async function askOpenAI(prompt) {
  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${OPENAI_API_KEY}`
      },
      body: JSON.stringify({
        model: OPENAI_MODEL,
        temperature: 0.4,
        messages: [
          {
            role: 'system',
            content: `Voce e Aria, assistente proativa de operacao comercial e execucao no Windows.\nFoque em: cadastro de cliente, agenda de servico, proposta, follow-up, fechamento e proximo passo acionavel.\nResponda em portugues, de forma curta e objetiva.\n\nMemoria recente:\n${buildMemoryContext()}\n\nPipeline comercial:\n${buildBusinessContext()}`
          },
          {
            role: 'user',
            content: prompt
          }
        ]
      })
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`OpenAI HTTP ${response.status}: ${errorText}`);
    }

    const data = await response.json();
    const content = data?.choices?.[0]?.message?.content?.trim();
    return content || 'Desculpe, nao consegui processar.';
  } catch (error) {
    console.error('OpenAI error:', error.message);
    throw error;
  }
}

async function askOpenAIVision(prompt) {
  if (!OPENAI_API_KEY || !latestScreenBase64) {
    return null;
  }

  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${OPENAI_API_KEY}`
      },
      body: JSON.stringify({
        model: OPENAI_VISION_MODEL,
        temperature: 0.2,
        messages: [
          {
            role: 'system',
            content: 'Descreva de forma objetiva o que aparece na tela do usuario, em portugues.'
          },
          {
            role: 'user',
            content: [
              { type: 'text', text: prompt },
              {
                type: 'image_url',
                image_url: {
                  url: `data:image/png;base64,${latestScreenBase64}`
                }
              }
            ]
          }
        ]
      })
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data?.choices?.[0]?.message?.content?.trim() || null;
  } catch (_error) {
    return null;
  }
}

async function handleAssistantPrompt(prompt) {
  const videoSearch = inferVideoSearch(prompt);
  if (videoSearch) {
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(videoSearch.query)}`;
    await shell.openExternal(url);
    const answer = `Abrindo YouTube com: ${videoSearch.query}`;
    pushMemory('user', String(prompt));
    pushMemory('assistant', answer);
    return answer;
  }

  const businessCommand = parseBusinessCommand(prompt);
  if (businessCommand) {
    const answer = await runBusinessCommand(businessCommand);
    pushMemory('user', String(prompt));
    pushMemory('assistant', answer);
    return answer;
  }

  const automationCommand = parseAutomationCommand(prompt);
  if (automationCommand) {
    try {
      const answer = await runAutomationCommand(automationCommand);
      pushMemory('user', String(prompt));
      pushMemory('assistant', answer);
      return answer;
    } catch (error) {
      const fail = `Nao consegui executar automacao: ${error.message}`;
      pushMemory('user', String(prompt));
      pushMemory('assistant', fail);
      return fail;
    }
  }

  const localCommand = parseLocalCommand(prompt);
  if (localCommand) {
    try {
      if (localCommand.type === 'list') {
        const output = listDirectory(localCommand.arg);
        pushMemory('user', String(prompt));
        pushMemory('assistant', output);
        return output;
      }

      if (localCommand.type === 'read') {
        const output = readTextFile(localCommand.arg);
        pushMemory('user', String(prompt));
        pushMemory('assistant', output);
        return output;
      }

      if (localCommand.type === 'search') {
        const output = searchFiles(localCommand.root, localCommand.keyword);
        pushMemory('user', String(prompt));
        pushMemory('assistant', output);
        return output;
      }

      if (localCommand.type === 'create-web-project') {
        const root = scaffoldWebProject(localCommand.name);
        const output = `Projeto web criado em: ${root}\nArquivos: index.html, styles.css, script.js`;
        pushMemory('user', String(prompt));
        pushMemory('assistant', output);
        return output;
      }

      if (localCommand.type === 'write-file') {
        const output = writeTextFile(localCommand.target, localCommand.content);
        pushMemory('user', String(prompt));
        pushMemory('assistant', output);
        return output;
      }

      if (localCommand.type === 'replace-file') {
        const output = replaceInTextFile(localCommand.target, localCommand.fromText, localCommand.toText);
        pushMemory('user', String(prompt));
        pushMemory('assistant', output);
        return output;
      }
    } catch (error) {
      return `Erro ao acessar arquivos: ${error.message}`;
    }
  }

  if (wantsScreenAnalysis(prompt)) {
    const visionAnswer = await askOpenAIVision(prompt);
    if (visionAnswer) {
      pushMemory('user', String(prompt));
      pushMemory('assistant', visionAnswer);
      return visionAnswer;
    }
  }

  const task = inferTask(prompt);

  if (task) {
    try {
      const taskAnswer = await runSystemTask(task);
      pushMemory('user', String(prompt));
      pushMemory('assistant', taskAnswer);
      return taskAnswer;
    } catch (_error) {
      return 'Nao consegui executar essa tarefa agora.';
    }
  }

  if (OPENAI_API_KEY) {
    try {
      const openAIAnswer = await askOpenAI(prompt);
      pushMemory('user', String(prompt));
      pushMemory('assistant', openAIAnswer);
      return openAIAnswer;
    } catch (_error) {
      // Fallback automatico para Ollama se OpenAI falhar.
    }
  }

  const ollamaAnswer = await askOllama(prompt);
  if (/^Ollama nao esta disponivel/i.test(ollamaAnswer)) {
    const offlineAnswer = OPENAI_API_KEY
      ? 'Nao consegui responder agora. OpenAI falhou e o Ollama esta offline em http://127.0.0.1:11434.'
      : 'Nao consegui responder agora. Configure OPENAI_API_KEY ou inicie o Ollama em http://127.0.0.1:11434.';

    pushMemory('user', String(prompt));
    pushMemory('assistant', offlineAnswer);
    return offlineAnswer;
  }

  pushMemory('user', String(prompt));
  pushMemory('assistant', ollamaAnswer);
  return ollamaAnswer;
}

function getTelegramApiUrl(method) {
  return `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${method}`;
}

async function sendTelegramMessage(chatId, text) {
  await fetch(getTelegramApiUrl('sendMessage'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text
    })
  });
}

async function processTelegramUpdate(update) {
  const message = update?.message;
  if (!message || !message.chat) {
    return;
  }

  const senderId = String(message.from?.id || '');
  const chatId = message.chat.id;

  if (TELEGRAM_ALLOWED_USER_ID && senderId !== String(TELEGRAM_ALLOWED_USER_ID)) {
    return;
  }

  const text = String(message.text || '').trim();
  if (!text) {
    await sendTelegramMessage(chatId, 'Envie uma mensagem de texto para conversar comigo.');
    return;
  }

  if (text === '/start') {
    const welcomeText = 'Oi! Pode falar comigo por aqui.';
    await sendTelegramMessage(chatId, welcomeText);

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('assistant:speak', welcomeText);
    }

    return;
  }

  const answer = await handleAssistantPrompt(text);
  await sendTelegramMessage(chatId, answer);

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('assistant:speak', answer);
  }
}

async function pollTelegram() {
  if (!TELEGRAM_BOT_TOKEN) {
    return;
  }

  try {
    const response = await fetch(getTelegramApiUrl('getUpdates'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        timeout: 20,
        offset: telegramOffset
      }),
      signal: AbortSignal.timeout(25000)
    });

    if (!response.ok) {
      throw new Error(`Telegram HTTP ${response.status}`);
    }

    const payload = await response.json();
    const updates = Array.isArray(payload?.result) ? payload.result : [];

    for (const update of updates) {
      telegramOffset = Math.max(telegramOffset, Number(update.update_id) + 1);
      await processTelegramUpdate(update);
    }
  } catch (error) {
    console.error('Telegram polling error:', error.message);
  } finally {
    telegramPollTimer = setTimeout(pollTelegram, 800);
  }
}

function startTelegramBridge() {
  if (!TELEGRAM_BOT_TOKEN) {
    console.log('Telegram bridge desativado: defina TELEGRAM_BOT_TOKEN para habilitar.');
    return;
  }

  console.log('Telegram bridge ativo.');
  pollTelegram();
}

function stopTelegramBridge() {
  clearTimeout(telegramPollTimer);
}

ipcMain.handle('window:minimize', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

ipcMain.handle('window:close', () => {
  if (mainWindow) {
    mainWindow.close();
  }
});

ipcMain.handle('window:pin', () => {
  if (!mainWindow) {
    return false;
  }

  const next = !mainWindow.isAlwaysOnTop();
  mainWindow.setAlwaysOnTop(next, 'screen-saver');
  return next;
});

ipcMain.handle('system:runTask', async (_event, task) => {
  return runSystemTask(task);
});

ipcMain.handle('assistant:chat', async (_event, prompt) => {
  return handleAssistantPrompt(prompt);
});

ipcMain.handle('assistant:tts', async (_event, text) => {
  if (!OPENAI_API_KEY) return null;

  try {
    const response = await fetch('https://api.openai.com/v1/audio/speech', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${OPENAI_API_KEY}`
      },
      body: JSON.stringify({
        model: 'tts-1',
        voice: 'nova',
        input: String(text).slice(0, 4096)
      })
    });

    if (!response.ok) {
      console.error('TTS error:', response.status);
      return null;
    }

    const arrayBuffer = await response.arrayBuffer();
    return Buffer.from(arrayBuffer).toString('base64');
  } catch (error) {
    console.error('TTS fetch error:', error.message);
    return null;
  }
});

app.whenReady().then(() => {
  initializeMemoryStore();
  initializeBusinessStore();
  createWindow();
  startTelegramBridge();
  startScreenWatcher();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  stopTelegramBridge();
  stopScreenWatcher();

  if (process.platform !== 'darwin') {
    app.quit();
  }
});