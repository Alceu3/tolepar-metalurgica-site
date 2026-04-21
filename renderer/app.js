const statusPill = document.getElementById('status-pill');
const micLevel = document.getElementById('mic-level');
const messages = document.getElementById('messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const voiceButton = document.getElementById('voice-button');
const listenButton = document.getElementById('listen-button');
const cameraButton = document.getElementById('camera-button');
const cameraPanel = document.getElementById('camera-panel');
const cameraFeed = document.getElementById('camera-feed');
const mouth = document.getElementById('mouth');
const pinButton = document.getElementById('pin-button');
const minimizeButton = document.getElementById('minimize-button');
const closeButton = document.getElementById('close-button');

let currentResponse = 'Oi. Eu sou sua base local de avatar e posso conversar, usar voz, camera e acionar tarefas simples.';
let audioStream;
let videoStream;
let isListening = false;

function setStatus(text) {
  statusPill.textContent = text;
}

function addMessage(role, text) {
  const item = document.createElement('div');
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function setTalking(talking) {
  mouth.classList.toggle('talking', talking);
}

function speak(text) {
  currentResponse = text;

  if (!('speechSynthesis' in window)) {
    setStatus('Sem voz do sistema');
    return;
  }

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'pt-BR';
  utterance.rate = 1;
  utterance.pitch = 1.08;
  utterance.onstart = () => {
    setTalking(true);
    setStatus('Falando');
  };
  utterance.onend = () => {
    setTalking(false);
    setStatus('Pronta');
  };
  utterance.onerror = () => {
    setTalking(false);
    setStatus('Falha na voz');
  };

  window.speechSynthesis.speak(utterance);
}

function inferTask(text) {
  const normalized = text.toLowerCase();

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
  const response = await fetch('http://127.0.0.1:11434/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'llama3.2',
      stream: false,
      messages: [
        {
          role: 'system',
          content: 'Voce e um avatar local para Windows. Responda em portugues, de forma curta e prestativa.'
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
  return data.message?.content?.trim() || 'Sem resposta do modelo local.';
}

async function handlePrompt(prompt) {
  addMessage('user', prompt);
  setStatus('Processando');

  const task = inferTask(prompt);
  if (task) {
    try {
      const result = await window.desktopBridge.runTask(task);
      addMessage('assistant', result);
      currentResponse = result;
      setStatus('Tarefa concluida');
      return;
    } catch (error) {
      const failure = `Nao consegui executar a tarefa: ${error.message}`;
      addMessage('assistant', failure);
      currentResponse = failure;
      setStatus('Falha na tarefa');
      return;
    }
  }

  try {
    const answer = await askOllama(prompt);
    addMessage('assistant', answer);
    currentResponse = answer;
    setStatus('Resposta local');
  } catch (_error) {
    const fallback = 'Ainda nao consegui falar com o Ollama. Posso continuar com voz, camera e tarefas simples enquanto voce instala ou baixa um modelo.';
    addMessage('assistant', fallback);
    currentResponse = fallback;
    setStatus('Fallback local');
  }
}

async function startMicrophone() {
  if (isListening) {
    audioStream?.getTracks().forEach((track) => track.stop());
    audioStream = null;
    isListening = false;
    micLevel.textContent = 'Mic: inativo';
    listenButton.textContent = 'Ouvir microfone';
    setStatus('Pronta');
    return;
  }

  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(audioStream);
    const analyser = audioContext.createAnalyser();
    const data = new Uint8Array(analyser.frequencyBinCount);

    source.connect(analyser);
    analyser.fftSize = 256;
    isListening = true;
    setStatus('Ouvindo');
    listenButton.textContent = 'Parar audio';

    const tick = () => {
      if (!isListening) {
        audioContext.close();
        return;
      }

      analyser.getByteFrequencyData(data);
      const average = data.reduce((sum, value) => sum + value, 0) / data.length;
      micLevel.textContent = `Mic: ${Math.round(average)}%`;
      requestAnimationFrame(tick);
    };

    tick();
  } catch (error) {
    setStatus('Mic bloqueado');
    micLevel.textContent = 'Mic: sem permissao';
    addMessage('assistant', `Nao consegui acessar o microfone: ${error.message}`);
  }
}

async function toggleCamera() {
  if (videoStream) {
    videoStream.getTracks().forEach((track) => track.stop());
    videoStream = null;
    cameraFeed.srcObject = null;
    cameraPanel.classList.add('hidden');
    cameraButton.textContent = 'Abrir camera';
    setStatus('Pronta');
    return;
  }

  try {
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    cameraFeed.srcObject = videoStream;
    cameraPanel.classList.remove('hidden');
    cameraButton.textContent = 'Fechar camera';
    setStatus('Camera ativa');
  } catch (error) {
    setStatus('Camera bloqueada');
    addMessage('assistant', `Nao consegui abrir a camera: ${error.message}`);
  }
}

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = chatInput.value.trim();
  if (!prompt) {
    return;
  }

  chatInput.value = '';
  await handlePrompt(prompt);
});

voiceButton.addEventListener('click', () => speak(currentResponse));
listenButton.addEventListener('click', startMicrophone);
cameraButton.addEventListener('click', toggleCamera);

document.querySelectorAll('[data-task]').forEach((button) => {
  button.addEventListener('click', async () => {
    const result = await window.desktopBridge.runTask(button.dataset.task);
    addMessage('assistant', result);
    currentResponse = result;
    setStatus('Tarefa concluida');
  });
});

pinButton.addEventListener('click', async () => {
  const pinned = await window.desktopBridge.togglePin();
  pinButton.textContent = pinned ? 'Soltar' : 'Fixar';
});

minimizeButton.addEventListener('click', () => {
  window.desktopBridge.minimizeWindow();
});

closeButton.addEventListener('click', () => {
  window.desktopBridge.closeWindow();
});

addMessage('assistant', currentResponse);