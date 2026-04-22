const assistantText = document.getElementById('assistant-text');
const promptInput = document.getElementById('prompt-input');
const avatarPhoto = document.getElementById('avatar-photo');
const lipCanvas = document.getElementById('lip-canvas');

let currentResponse = 'Digite sua mensagem...';
let isSpeaking = false;

const ANIMATION_PROFILES = {
  sutil: {
    mouth: 0.78,
    face: 0.72,
    emotion: 0.70,
    blink: 0.90
  },
  natural: {
    mouth: 1.0,
    face: 1.0,
    emotion: 1.0,
    blink: 1.0
  },
  expressivo: {
    mouth: 1.25,
    face: 1.28,
    emotion: 1.22,
    blink: 1.08
  }
};

// ─── Sincronização labial ────────────────────────────────────────────────────
// Fallback inicial; valores reais sao calibrados automaticamente pela foto.
let MOUTH = { cxF: 0.481, cyF: 0.248, rxF: 0.046, ryClosed: 0.009 };
let FACE = {
  leftEye: { xF: 0.43, yF: 0.18, wF: 0.060, hF: 0.022 },
  rightEye: { xF: 0.57, yF: 0.18, wF: 0.060, hF: 0.022 },
  leftBrow: { xF: 0.43, yF: 0.145, wF: 0.074, hF: 0.020 },
  rightBrow: { xF: 0.57, yF: 0.145, wF: 0.074, hF: 0.020 }
};

async function autoCalibrateMouthFromPhoto() {
  try {
    const vision = await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14');
    const { FilesetResolver, FaceLandmarker } = vision;
    const filesetResolver = await FilesetResolver.forVisionTasks(
      'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm'
    );

    const faceLandmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
      baseOptions: {
        modelAssetPath:
          'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task',
        delegate: 'GPU'
      },
      runningMode: 'IMAGE',
      numFaces: 1
    });

    const result = faceLandmarker.detect(avatarPhoto);
    const landmarks = result?.faceLandmarks?.[0];
    if (!landmarks || !landmarks.length) return;

    // Indices MediaPipe FaceMesh para boca.
    const leftCorner = landmarks[61];
    const rightCorner = landmarks[291];
    const upperInner = landmarks[13];
    const lowerInner = landmarks[14];

    if (!leftCorner || !rightCorner || !upperInner || !lowerInner) return;

    const cxF = (leftCorner.x + rightCorner.x) / 2;
    const cyF = (upperInner.y + lowerInner.y) / 2;
    const widthF = Math.max(0.025, Math.abs(rightCorner.x - leftCorner.x));
    const heightF = Math.max(0.006, Math.abs(lowerInner.y - upperInner.y));

    MOUTH = {
      cxF,
      cyF,
      rxF: widthF * 0.56,
      ryClosed: heightF * 0.85
    };

    const leftEyeOuter = landmarks[33];
    const leftEyeInner = landmarks[133];
    const leftEyeUpper = landmarks[159];
    const leftEyeLower = landmarks[145];
    const rightEyeOuter = landmarks[263];
    const rightEyeInner = landmarks[362];
    const rightEyeUpper = landmarks[386];
    const rightEyeLower = landmarks[374];
    const leftBrowMid = landmarks[105];
    const rightBrowMid = landmarks[334];

    if (
      leftEyeOuter && leftEyeInner && leftEyeUpper && leftEyeLower &&
      rightEyeOuter && rightEyeInner && rightEyeUpper && rightEyeLower &&
      leftBrowMid && rightBrowMid
    ) {
      const leftEyeW = Math.max(0.03, Math.abs(leftEyeInner.x - leftEyeOuter.x));
      const leftEyeH = Math.max(0.008, Math.abs(leftEyeLower.y - leftEyeUpper.y));
      const rightEyeW = Math.max(0.03, Math.abs(rightEyeOuter.x - rightEyeInner.x));
      const rightEyeH = Math.max(0.008, Math.abs(rightEyeLower.y - rightEyeUpper.y));

      FACE = {
        leftEye: {
          xF: (leftEyeOuter.x + leftEyeInner.x) / 2,
          yF: (leftEyeUpper.y + leftEyeLower.y) / 2,
          wF: leftEyeW,
          hF: leftEyeH
        },
        rightEye: {
          xF: (rightEyeOuter.x + rightEyeInner.x) / 2,
          yF: (rightEyeUpper.y + rightEyeLower.y) / 2,
          wF: rightEyeW,
          hF: rightEyeH
        },
        leftBrow: {
          xF: leftBrowMid.x,
          yF: leftBrowMid.y,
          wF: leftEyeW * 1.2,
          hF: leftEyeH * 1.0
        },
        rightBrow: {
          xF: rightBrowMid.x,
          yF: rightBrowMid.y,
          wF: rightEyeW * 1.2,
          hF: rightEyeH * 1.0
        }
      };
    }
  } catch (_error) {
    // Mantem fallback se a calibracao automatica nao estiver disponivel.
  }
}

class LipSync {
  constructor(canvas, imgEl) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.imgEl = imgEl;
    this.amplitude = 0;
    this.raf = null;
    this.analyser = null;
    this.dataArray = null;
    this.audioCtx = null;
    this.blink = 0;
    this.nextBlinkAt = 0;
    this.blinkStart = 0;
    this.blinkUntil = 0;
    this.smile = 0;
    this.energy = 0;
    this.lastAmp = 0;
    this.moodTarget = { valence: 0, arousal: 0.5, seriousness: 0.4 };
    this.moodCurrent = { valence: 0, arousal: 0.5, seriousness: 0.4 };
    this.audioEl = null;
    this.speechPlan = [];
    this.speechStartedAt = 0;
    this.profileName = 'natural';
    this.profile = ANIMATION_PROFILES.natural;
  }

  setProfile(name) {
    const key = String(name || '').toLowerCase();
    if (!ANIMATION_PROFILES[key]) return false;
    this.profileName = key;
    this.profile = ANIMATION_PROFILES[key];
    return true;
  }

  setMood(mood) {
    this.moodTarget = {
      valence: Math.max(-1, Math.min(1, Number(mood?.valence ?? 0))),
      arousal: Math.max(0, Math.min(1, Number(mood?.arousal ?? 0.5))),
      seriousness: Math.max(0, Math.min(1, Number(mood?.seriousness ?? 0.4)))
    };
  }

  rand(min, max) {
    return min + Math.random() * (max - min);
  }

  renderStatic() {
    const { w, h } = this.syncSize();
    this.ctx.clearRect(0, 0, w, h);
    this.ctx.drawImage(this.imgEl, 0, 0, w, h);
  }

  syncSize() {
    const r = this.imgEl.getBoundingClientRect();
    const w = Math.round(r.width);
    const h = Math.round(r.height);
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
      this.canvas.style.width = w + 'px';
      this.canvas.style.height = h + 'px';
    }
    return { w, h };
  }

  connectAudio(audioEl) {
    this.audioEl = audioEl;
    this.speechStartedAt = performance.now() * 0.001;
    this.audioCtx = new AudioContext();
    const source = this.audioCtx.createMediaElementSource(audioEl);
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.smoothingTimeConstant = 0.80;
    source.connect(this.analyser);
    this.analyser.connect(this.audioCtx.destination);
    this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
  }

  setSpeechText(text) {
    const raw = String(text || '').toLowerCase();
    const chars = raw.replace(/[^a-z0-9aeiouãõáéíóúâêôç\s]/gi, ' ').split('');
    const plan = [];
    const durationBase = 0.08;
    const durationVowel = 0.12;
    let t = 0;

    for (const ch of chars) {
      if (ch.trim() === '') {
        t += 0.04;
        continue;
      }

      const viseme = { open: 0.22, wide: 0.22, round: 0.18 };
      if (/a|á|â|ã/.test(ch)) viseme.open = 0.95;
      if (/e|é|ê/.test(ch)) { viseme.open = 0.62; viseme.wide = 0.82; }
      if (/i|í/.test(ch)) { viseme.open = 0.42; viseme.wide = 1.0; }
      if (/o|ó|ô|õ/.test(ch)) { viseme.open = 0.68; viseme.round = 0.9; }
      if (/u|ú/.test(ch)) { viseme.open = 0.55; viseme.round = 1.0; }
      if (/m|b|p/.test(ch)) viseme.open = 0.08;
      if (/f|v/.test(ch)) { viseme.open = 0.22; viseme.wide = 0.55; }

      const d = /[aeiouáéíóúâêôãõ]/.test(ch) ? durationVowel : durationBase;
      plan.push({ start: t, end: t + d, ...viseme });
      t += d;
    }

    this.speechPlan = plan;
  }

  getCurrentViseme(nowSeconds) {
    if (!this.speechPlan.length) return { open: 0.25, wide: 0.3, round: 0.2 };

    let elapsed = nowSeconds - this.speechStartedAt;
    if (this.audioEl && Number.isFinite(this.audioEl.currentTime) && this.audioEl.currentTime > 0) {
      elapsed = this.audioEl.currentTime;
    }

    const hit = this.speechPlan.find((p) => elapsed >= p.start && elapsed < p.end) || this.speechPlan[this.speechPlan.length - 1];
    return { open: hit.open, wide: hit.wide, round: hit.round };
  }

  getSpeechElapsed(nowSeconds) {
    let elapsed = nowSeconds - this.speechStartedAt;
    if (this.audioEl && Number.isFinite(this.audioEl.currentTime) && this.audioEl.currentTime >= 0) {
      elapsed = this.audioEl.currentTime;
    }
    return Math.max(0, elapsed);
  }

  getSpeechDrive(nowSeconds) {
    if (!this.speechPlan.length) return 0;
    const elapsed = this.getSpeechElapsed(nowSeconds);
    const active = this.speechPlan.find((p) => elapsed >= p.start && elapsed < p.end);
    if (!active) return 0.08;

    const d = Math.max(0.05, active.end - active.start);
    const localT = (elapsed - active.start) / d;
    const pulse = Math.sin(Math.PI * Math.max(0, Math.min(1, localT)));
    return Math.max(0, (active.open * 0.75 + active.wide * 0.20 + active.round * 0.15) * pulse);
  }

  getAmplitude() {
    if (!this.analyser) return 0;
    this.analyser.getByteFrequencyData(this.dataArray);
    let sum = 0;
    for (let i = 2; i < 28; i++) sum += this.dataArray[i];
    return sum / (26 * 255);
  }

  updateExpression(nowSeconds, amp, drive = amp) {
    if (!this.nextBlinkAt) {
      this.nextBlinkAt = nowSeconds + this.rand(1.8, 4.2);
    }

    if (nowSeconds >= this.nextBlinkAt) {
      this.blinkStart = nowSeconds;
      this.blinkUntil = nowSeconds + this.rand(0.10, 0.16);
      this.nextBlinkAt = nowSeconds + this.rand(2.0, 4.8);
    }

    if (nowSeconds < this.blinkUntil) {
      const total = Math.max(0.08, this.blinkUntil - this.blinkStart);
      const progress = (nowSeconds - this.blinkStart) / total;
      const p = Math.min(1, Math.max(0, progress));
      this.blink = Math.sin(p * Math.PI);
    } else {
      this.blink *= 0.72;
      if (this.blink < 0.01) this.blink = 0;
    }

    const moodBlend = 0.08;
    this.moodCurrent.valence += (this.moodTarget.valence - this.moodCurrent.valence) * moodBlend;
    this.moodCurrent.arousal += (this.moodTarget.arousal - this.moodCurrent.arousal) * moodBlend;
    this.moodCurrent.seriousness += (this.moodTarget.seriousness - this.moodCurrent.seriousness) * moodBlend;

    const targetSmile = Math.min(
      1,
      Math.max(
        0,
        ((drive - 0.02) * 4.5 + this.moodCurrent.valence * 0.40 - this.moodCurrent.seriousness * 0.20) * this.profile.emotion
      )
    );
    this.smile += (targetSmile - this.smile) * 0.18;

    const delta = Math.max(0, drive - this.lastAmp);
    const targetEnergy = Math.min(
      1,
      (drive * (1.0 + this.moodCurrent.arousal * 0.7) + delta * 2.0 + this.moodCurrent.arousal * 0.08) * this.profile.face
    );
    this.energy += (targetEnergy - this.energy) * 0.16;
    this.lastAmp = drive;
  }

  drawRoundedCapsule(x, y, w, h, radius) {
    const r = Math.min(radius, w * 0.5, h * 0.5);
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  drawArmGesture(side, amp, nowSeconds) {
    const { w, h } = this.syncSize();
    const ctx = this.ctx;
    const dir = side === 'left' ? -1 : 1;
    const moodArousal = this.moodCurrent.arousal;
    const moodSerious = this.moodCurrent.seriousness;
    const speechDrive = this.getSpeechDrive(nowSeconds);
    const drive = Math.max(amp, speechDrive);
    const talk = Math.min(1, drive * (1.8 + moodArousal * 1.0) + this.energy * (0.55 + moodArousal * 0.30));
    const rhythmic = Math.sin(nowSeconds * (5.7 + talk * 2.2) + (side === 'left' ? 0.5 : 1.9));
    const lift = Math.max(0, talk * (0.68 + moodArousal * 0.30 - moodSerious * 0.25) + rhythmic * (0.10 + moodArousal * 0.12));

    const srcW = w * 0.24;
    const srcH = h * 0.42;
    const srcX = side === 'left' ? w * 0.01 : w - srcW - w * 0.01;
    const srcY = h * 0.46;

    const shoulderX = side === 'left' ? w * 0.24 : w * 0.76;
    const shoulderY = h * 0.50;
    const angle = dir * (0.025 + lift * (0.18 + moodArousal * 0.08)) + rhythmic * (0.02 + moodArousal * 0.03);

    ctx.save();
    ctx.translate(shoulderX, shoulderY);
    ctx.rotate(angle);

    const dstX = side === 'left' ? -srcW * 0.82 : -srcW * 0.18;
    const dstY = -srcH * 0.12 - lift * h * (0.011 + moodArousal * 0.007);

    this.drawRoundedCapsule(dstX, dstY, srcW * 0.90, srcH * 0.96, srcW * 0.28);
    ctx.clip();
    ctx.drawImage(this.imgEl, srcX, srcY, srcW, srcH, dstX, dstY, srcW, srcH);
    ctx.restore();
  }

  drawEyeWarp(eye, blinkFactor, eyeLiftPx) {
    const { w, h } = this.syncSize();
    const ctx = this.ctx;
    const ex = w * eye.xF;
    const ey = h * eye.yF - eyeLiftPx;
    const ew = w * eye.wF;
    const eh = h * eye.hF;
    const srcX = ex - ew * 1.15;
    const srcY = ey - eh * 1.4;
    const srcW = ew * 2.3;
    const srcH = eh * 2.8;
    const dstH = Math.max(1, srcH * (1 - blinkFactor * 0.78));
    const dstY = ey - dstH / 2;

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(ex, ey, ew * 1.05, eh * 1.02, 0, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(this.imgEl, srcX, srcY, srcW, srcH, srcX, dstY, srcW, dstH);
    ctx.restore();
  }

  drawBrowWarp(brow, risePx) {
    const { w, h } = this.syncSize();
    const ctx = this.ctx;
    const bx = w * brow.xF;
    const by = h * brow.yF;
    const bw = w * brow.wF;
    const bh = h * brow.hF;
    const srcX = bx - bw * 0.9;
    const srcY = by - bh * 0.9;
    const srcW = bw * 1.8;
    const srcH = bh * 1.8;

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(bx, by, bw * 0.95, bh * 0.85, 0, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(this.imgEl, srcX, srcY, srcW, srcH, srcX, srcY - risePx, srcW, srcH);
    ctx.restore();
  }

  drawCheekTone(cx, cy, rx, ry, intensity) {
    const ctx = this.ctx;
    if (intensity <= 0.02) return;
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 168, 168, ${Math.min(0.14, intensity * 0.12)})`;
    ctx.fill();
    ctx.restore();
  }

  draw() {
    const { w, h } = this.syncSize();
    const ctx = this.ctx;
    const amp = this.amplitude;
    const now = performance.now() * 0.001;
    const speechDrive = this.getSpeechDrive(now);
    const drive = Math.max(amp, speechDrive);
    this.updateExpression(now, amp, drive);

    // Mantem a foto totalmente estavel (sem chacoalhar).
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(this.imgEl, 0, 0, w, h);

    const blinkFactor = this.blink * (0.92 + this.moodCurrent.arousal * 0.16) * this.profile.blink;
    const eyeLiftPx = h * (this.smile * 0.004 + this.energy * 0.0035 + this.moodCurrent.valence * 0.0015) * this.profile.face;
    const browRisePx = h * (
      this.smile * 0.008 +
      (1 - blinkFactor) * 0.002 +
      this.moodCurrent.valence * 0.003 -
      this.moodCurrent.seriousness * 0.002
    ) * this.profile.face;
    const talkSwayX = 0;
    const talkSwayY = 0;

    const leftEye = { ...FACE.leftEye, xF: FACE.leftEye.xF + talkSwayX / w, yF: FACE.leftEye.yF + talkSwayY / h };
    const rightEye = { ...FACE.rightEye, xF: FACE.rightEye.xF + talkSwayX / w, yF: FACE.rightEye.yF + talkSwayY / h };
    const leftBrow = { ...FACE.leftBrow, xF: FACE.leftBrow.xF + talkSwayX / w, yF: FACE.leftBrow.yF + talkSwayY / h };
    const rightBrow = { ...FACE.rightBrow, xF: FACE.rightBrow.xF + talkSwayX / w, yF: FACE.rightBrow.yF + talkSwayY / h };

    this.drawEyeWarp(leftEye, blinkFactor, eyeLiftPx);
    this.drawEyeWarp(rightEye, blinkFactor, eyeLiftPx);
    this.drawBrowWarp(leftBrow, browRisePx);
    this.drawBrowWarp(rightBrow, browRisePx);

    const cheekIntensity = (this.smile + this.energy * 0.25 + Math.max(0, this.moodCurrent.valence) * 0.20) * this.profile.emotion;
    this.drawCheekTone(w * (leftEye.xF - 0.01), h * (leftEye.yF + 0.11), w * 0.050, h * 0.030, cheekIntensity);
    this.drawCheekTone(w * (rightEye.xF + 0.01), h * (rightEye.yF + 0.11), w * 0.050, h * 0.030, cheekIntensity);

    if (drive < 0.02) return;

    const cx  = w * MOUTH.cxF + talkSwayX * 0.55;
    const cy  = h * MOUTH.cyF + talkSwayY * 0.40;
    const rx  = w * MOUTH.rxF;
    const ryBase = h * MOUTH.ryClosed;
    const viseme = this.getCurrentViseme(now);
    const opening = (drive * h * (0.020 + this.moodCurrent.arousal * 0.008) + h * 0.014 * viseme.open) * this.profile.mouth;
    const widthScale = 0.86 + viseme.wide * 0.34 - viseme.round * 0.16;
    const mouthW = rx * 2.15 * widthScale;
    const mouthH = Math.max(ryBase * 3.2, h * 0.020);
    const sx = cx - mouthW / 2;
    const sy = cy - mouthH / 2;

    // Recorta a regiao da boca e move os dois semiplanos da propria imagem.
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, cy + opening * 0.22, rx * (1.18 + viseme.round * 0.12), mouthH * 0.95 + opening * 0.25, 0, 0, Math.PI * 2);
    ctx.clip();

    const halfH = mouthH / 2;
    // Labio superior (quase fixo)
    ctx.drawImage(this.imgEl, sx, sy, mouthW, halfH, sx, sy - opening * 0.10, mouthW, halfH);
    // Labio inferior (desce ao falar)
    ctx.drawImage(this.imgEl, sx, sy + halfH, mouthW, halfH, sx, sy + halfH + opening * 0.92, mouthW, halfH);

    if (opening > 0.9) {
      ctx.beginPath();
      ctx.ellipse(cx, cy + opening * 0.42, rx * 0.64, opening * 0.58, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(46, 12, 18, 0.42)';
      ctx.fill();
    }

    ctx.restore();
  }

  start() {
    this.nextBlinkAt = 0;
    this.blinkStart = 0;
    this.blinkUntil = 0;
    this.energy = 0;
    this.lastAmp = 0;
    const loop = () => {
      const raw = this.getAmplitude();
      const speed = raw > this.amplitude ? 0.40 : 0.15;
      this.amplitude += (raw - this.amplitude) * speed;
      this.draw();
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop() {
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = null; }
    this.renderStatic();
    this.amplitude = 0;
    this.audioEl = null;
    this.speechPlan = [];
    if (this.audioCtx) {
      this.audioCtx.close().catch(() => {});
      this.audioCtx = null;
      this.analyser = null;
    }
  }
}

const lipSync = new LipSync(lipCanvas, avatarPhoto);
// Sincroniza tamanho inicial e calibra boca automaticamente pela foto.
avatarPhoto.addEventListener('load', async () => {
  await autoCalibrateMouthFromPhoto();
  lipSync.renderStatic();
});
if (avatarPhoto.complete) {
  autoCalibrateMouthFromPhoto().finally(() => lipSync.renderStatic());
}
// ─────────────────────────────────────────────────────────────────────────────

// Fallback: Web Speech com pitch alto caso OpenAI TTS falhe
function speakFallback(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'pt-BR';
  utterance.rate = 1;
  utterance.pitch = 1.4;
  window.speechSynthesis.speak(utterance);
}

function inferMoodFromText(text) {
  const t = String(text || '').toLowerCase();
  const exclamations = (t.match(/!/g) || []).length;

  const positive = /(otimo|excelente|perfeito|maravilha|legal|feliz|alegre|show|sucesso|parabens|amei|adorei)/i.test(t);
  const negative = /(erro|falha|problema|nao consegui|nao foi possivel|desculpe|infelizmente|triste|ruim)/i.test(t);
  const serious = /(atencao|importante|cuidado|aviso|critico|urgente|risco|erro grave)/i.test(t);
  const calm = /(calma|tranquilo|respira|sem pressa|ok|certo|entendi)/i.test(t);

  let valence = 0;
  let arousal = 0.45;
  let seriousness = 0.35;

  if (positive) valence += 0.55;
  if (negative) valence -= 0.45;
  if (serious) seriousness += 0.45;
  if (calm) arousal -= 0.12;

  arousal += Math.min(0.35, exclamations * 0.08);
  if (positive && exclamations > 0) arousal += 0.08;
  if (negative && serious) arousal += 0.10;

  valence = Math.max(-1, Math.min(1, valence));
  arousal = Math.max(0.15, Math.min(1, arousal));
  seriousness = Math.max(0, Math.min(1, seriousness));

  return { valence, arousal, seriousness };
}

async function speak(text) {
  currentResponse = text;
  if (isSpeaking) return;

  lipSync.setMood(inferMoodFromText(text));
  lipSync.setSpeechText(text);

  // Tenta OpenAI TTS (voz "nova" — feminina e natural)
  if (window.desktopBridge?.tts) {
    try {
      isSpeaking = true;
      const base64 = await window.desktopBridge.tts(text);
      if (base64) {
        const audio = new Audio(`data:audio/mpeg;base64,${base64}`);
        lipSync.connectAudio(audio);
        lipSync.start();
        audio.onended = () => {
          isSpeaking = false;
          setTimeout(() => lipSync.stop(), 200);
        };
        audio.onerror = () => {
          isSpeaking = false;
          lipSync.stop();
          speakFallback(text);
        };
        await audio.play();
        return;
      }
    } catch (_e) {
      // silencioso
    }
  }

  isSpeaking = false;
  speakFallback(text);
}

function setAssistantText(text) {
  assistantText.textContent = text;
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

async function askAssistant(prompt) {
  if (window.desktopBridge?.chatAssistant) {
    return window.desktopBridge.chatAssistant(prompt);
  }

  return 'Nao consegui acessar o assistente agora.';
}

async function handlePrompt(prompt) {
  const cleanedPrompt = String(prompt || '').trim();
  if (!cleanedPrompt) {
    return;
  }

  const task = inferTask(cleanedPrompt);
  let answer;

  if (task) {
    try {
      answer = await window.desktopBridge.runTask(task);
    } catch (_error) {
      answer = 'Nao consegui executar essa tarefa agora.';
    }
  } else {
    try {
      answer = await askAssistant(cleanedPrompt);
    } catch (_error) {
      answer = 'Desculpe, nao consegui processar sua mensagem.';
    }
  }

  setAssistantText(answer);
  speak(answer);
}

promptInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') {
    return;
  }

  event.preventDefault();
  const value = promptInput.value;
  promptInput.value = '';
  handlePrompt(value);
});

if (window.desktopBridge?.onAssistantSpeak) {
  window.desktopBridge.onAssistantSpeak((text) => {
    if (!text) {
      return;
    }

    setAssistantText(text);
    speak(text);
  });
}

setAssistantText(currentResponse);
console.log('Avatar assistant inicializado com texto e voz.');
