import { MotionGate } from './motion.js';
import { drawCameraRegion } from './camera.js';

const $ = id => document.getElementById(id);
const view = $('view'), video = $('video'), ctx = view.getContext('2d');
const crop = document.createElement('canvas'), cropCtx = crop.getContext('2d');
const tiny = document.createElement('canvas'); tiny.width = 64; tiny.height = 48;
const tinyCtx = tiny.getContext('2d', { willReadFrequently: true });
const gate = new MotionGate(performance.now());
let stream = null, demoMode = false, paused = true, busy = false, confirmed = false;
let flipX = false, flipY = false, cameraGeneration = 0;
let roi = { x: 0.06, y: 0.08, w: 0.88, h: 0.8 }, drag = null, snapshot = null;
let token = '', generation = 0, controller = null, activeHint = null, hintLevel = 0;
let session = [], currentExercises = [], latestSample = null;
let processingTimer = null, processingStarted = 0;
let lastTick = 0, editorFocused = false, lessonActive = false, reading = false;

function notice(text = '') { $('notice').textContent = text; $('notice').hidden = !text; }
function status(text) { $('status').textContent = text; }
function context() { return { grade: $('grade').value, subject: $('subject').value }; }
function showProcessing(title, description) {
  $('processingTitle').textContent = title;
  $('processingDescription').textContent = description;
  if ($('processingDialog').open) return; // Keep the overlay up between reading and preparing hints.
  processingStarted = performance.now();
  $('processingElapsed').textContent = '已等待 0 秒';
  document.documentElement.classList.add('processing');
  document.querySelector('main').setAttribute('aria-busy', 'true');
  $('processingDialog').showModal();
  processingTimer = setInterval(() => {
    const seconds = Math.floor((performance.now() - processingStarted) / 1000);
    $('processingElapsed').textContent = `已等待 ${seconds} 秒${seconds >= 20 ? ' · 較複雜的題目可能需要更久，請稍候。' : ''}`;
  }, 1000);
}
function hideProcessing() {
  clearInterval(processingTimer); processingTimer = null;
  if ($('processingDialog').open) $('processingDialog').close();
  document.documentElement.classList.remove('processing');
  document.querySelector('main').removeAttribute('aria-busy');
}
function cancelProcessing() {
  cancel(); $('auto').checked = false;
  gate.reset(performance.now());
  status('已取消這次處理，可手動重試');
  notice('已停止等待，原有教學仍保留。已送出的模型處理可能仍會使用額度。');
}
$('cancelProcessing').onclick = cancelProcessing;
$('processingDialog').addEventListener('cancel', event => {
  event.preventDefault(); cancelProcessing();
});

function cancel() {
  generation++; controller?.abort(); controller = null; busy = false;
  window.speechSynthesis?.cancel();
  // A cancelled first read has no lesson to preserve; allow a manual retry.
  if (reading && !$('question').value.trim()) setLessonActive(false);
  reading = false; hideProcessing();
}
function clearLesson() {
  confirmed = false; activeHint = null; hintLevel = 0;
  $('hint').disabled = !$('question').value.trim(); $('confirm').disabled = !$('question').value.trim();
  $('solution').disabled = true; $('explanationBlock').hidden = true;
  $('verdict').textContent = '確認文字後再檢查答案';
  $('hintTitle').textContent = '先給自己一點思考時間';
  $('hintText').textContent = '需要的時候，按下「給我提示」。我會先給方向，不急著說出答案。';
  $('hintLabel').textContent = 'A SMALL NUDGE';
  $('exercises').replaceChildren(); currentExercises = []; $('reviewEmpty').hidden = false;
}
function setLessonActive(active) {
  lessonActive = active;
  $('nextQuestion').disabled = !active; $('demo').disabled = active;
  $('subject').disabled = active; $('grade').disabled = active;
  $('capture').disabled = active || paused || !stream;
  $('lessonStatus').textContent = active
    ? '本題已保留。看懂提示、完成練習後，再按「我理解了，下一題」。'
    : '等待讀取題目；讀取後會保留到你主動切換下一題。';
}
function resetLesson() {
  cancel(); snapshot = null; latestSample = null; gate.reset(performance.now());
  $('question').value = ''; $('answer').value = '';
  clearLesson(); setLessonActive(false);
  $('explanation').textContent = ''; $('confidence').textContent = '等待畫面';
  $('coachTitle').textContent = '不急，我在這裡。';
  $('coachText').textContent = '準備好作業後，我們先看看題目在問什麼。';
}
function cameraChanged() {
  latestSample = null; gate.reset(performance.now());
  // Camera geometry is independent of the captured question and its teaching.
  if (!lessonActive) { cancel(); snapshot = null; }
}
async function config() {
  const response = await fetch('/api/config');
  if (!response.ok) throw new Error('無法連接本機服務。');
  const result = await response.json(); token = result.token;
  $('login').hidden = result.authenticated; $('logout').hidden = !result.authenticated;
  $('modelStatus').textContent = `${result.model} · ${result.message}`;
  $('usage').textContent = `本次啟動 ${result.calls} / ${result.max_calls} 次模型請求 · 輸入 ${result.input_tokens}、輸出 ${result.output_tokens} tokens`;
}
async function api(path, payload, signal) {
  const response = await fetch(path, { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'X-Study-Token': token,
      'X-Study-Cloud': $('cloud').checked ? 'enabled' : 'disabled' }, body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || '請求失敗，請稍後再試。');
  return data;
}
function stopCamera() {
  cameraGeneration++;
  stream?.getTracks().forEach(track => track.stop()); stream = null; video.srcObject = null;
  $('capture').disabled = true; $('pause').disabled = true; $('resetCrop').disabled = true;
  for (const id of ['flipHorizontal', 'flipVertical', 'resetOrientation']) $(id).disabled = true;
}
async function startCamera() {
  stopCamera(); paused = true; cameraChanged();
  if (!lessonActive) demoMode = false;
  const cameraEpoch = cameraGeneration;
  try {
    status('正在開啟攝影機…');
    const deviceId = $('camera').value;
    const next = await navigator.mediaDevices.getUserMedia({ audio: false, video: {
      width: { ideal: 1920 }, height: { ideal: 1080 }, ...(deviceId ? { deviceId: { exact: deviceId } } : {}) } });
    if (cameraEpoch !== cameraGeneration) { next.getTracks().forEach(t => t.stop()); return; }
    stream = next; video.srcObject = stream; await video.play();
    if (cameraEpoch !== cameraGeneration) return;
    view.width = video.videoWidth; view.height = video.videoHeight;
    $('placeholder').hidden = true; $('frameLabel').hidden = false; $('resume').hidden = true;
    $('sourceBadge').textContent = '即時鏡頭 · 本機預覽';
    $('capture').disabled = lessonActive; $('pause').disabled = false; $('resetCrop').disabled = false;
    for (const id of ['flipHorizontal', 'flipVertical', 'resetOrientation']) $(id).disabled = false;
    $('pause').textContent = '暫停陪讀'; paused = false; gate.reset(performance.now());
    status(lessonActive ? '相機已開啟，本題教學繼續保留' : '請拖曳框選目前題目');
    if (!lessonActive) notice('請先框選單一題目，避開姓名與人臉，再開啟雲端分析。');
    const devices = await navigator.mediaDevices.enumerateDevices();
    const selected = stream.getVideoTracks()[0].getSettings().deviceId;
    $('camera').replaceChildren(...devices.filter(d => d.kind === 'videoinput').map((d, i) => {
      const option = document.createElement('option'); option.value = d.deviceId;
      option.textContent = d.label || `攝影機 ${i + 1}`; option.selected = d.deviceId === selected; return option;
    }));
    stream.getVideoTracks()[0].onended = () => {
      cancel(); stopCamera(); paused = true; $('resume').hidden = false;
      status('攝影機已中斷'); notice('攝影機連線中斷，請重新開啟。');
    };
  } catch (error) {
    if (cameraEpoch !== cameraGeneration) return;
    stopCamera(); status('攝影機尚未開啟'); $('resume').hidden = false;
    notice('無法開啟鏡頭。請在瀏覽器與 macOS「隱私權與安全性 → 攝影機」允許存取，並使用 localhost 網址。');
  }
}
function captureImage() {
  if (!stream || !video.videoWidth) throw new Error('請先開啟鏡頭。');
  const sw = roi.w * video.videoWidth, sh = roi.h * video.videoHeight;
  const scale = Math.min(1, 1600 / Math.max(sw, sh));
  crop.width = Math.max(32, Math.round(sw * scale)); crop.height = Math.max(32, Math.round(sh * scale));
  drawCameraRegion(cropCtx, video, video.videoWidth, video.videoHeight, roi, flipX, flipY);
  return crop.toDataURL('image/jpeg', 0.88);
}
function motionSample() {
  drawCameraRegion(tinyCtx, video, video.videoWidth, video.videoHeight, roi, flipX, flipY);
  const rgba = tinyCtx.getImageData(0, 0, 64, 48).data;
  const gray = new Uint8Array(64 * 48);
  for (let i = 0; i < gray.length; i++) gray[i] = (rgba[i * 4] + rgba[i * 4 + 1] + rgba[i * 4 + 2]) / 3;
  return gray;
}
function paint() {
  if (stream && video.readyState >= 2) {
    drawCameraRegion(ctx, video, video.videoWidth, video.videoHeight,
      { x: 0, y: 0, w: 1, h: 1 }, flipX, flipY);
    const x = roi.x * view.width, y = roi.y * view.height, w = roi.w * view.width, h = roi.h * view.height;
    ctx.fillStyle = 'rgba(20,45,39,.28)';
    ctx.fillRect(0, 0, view.width, y); ctx.fillRect(0, y + h, view.width, view.height - y - h);
    ctx.fillRect(0, y, x, h); ctx.fillRect(x + w, y, view.width - x - w, h);
    ctx.strokeStyle = '#a9edbb'; ctx.lineWidth = Math.max(3, view.width / 350); ctx.strokeRect(x, y, w, h);
  }
  const now = performance.now();
  if (stream && !paused && !demoMode && !drag && video.readyState >= 2 && now - lastTick >= 500) {
    lastTick = now; latestSample = motionSample();
    const signal = gate.tick(latestSample, now, { interval: +$('interval').value, idle: +$('idle').value });
    $('motionText').textContent = lessonActive
      ? '本題已固定；畫面移動不會重新辨識或清除教學。'
      : (signal.moving ? '作業區域有變化，等畫面穩定再看。' : `畫面穩定約 ${signal.idleSeconds} 秒 · 等待讀題`);
    if (signal.nudge && !busy && !editorFocused && hintLevel === 0 && (!lessonActive || activeHint)) {
      gate.nudge(now);
      showHint(activeHint?.hint || '可以先想一想：題目要找的是什麼？需要的話，按「給我提示」。', activeHint ? 1 : 0);
      if (activeHint) hintLevel = 1;
    }
    if (!lessonActive && signal.analyze && $('auto').checked && $('cloud').checked && !busy && !editorFocused) observe();
  }
  requestAnimationFrame(paint);
}
function applyObservation(observation) {
  $('question').value = observation.question; $('answer').value = observation.student_answer;
  clearLesson(); setLessonActive(true);
  $('confidence').textContent = demoMode ? '人工編寫示範' : `模型自評 ${Math.round(observation.confidence * 100)}% · 非校準機率`;
  const usable = observation.quality === 'clear' && observation.confidence >= 0.85 && observation.question.trim();
  notice(usable ? '' : (observation.clarification || '題目看不清楚，請修正文字，或按「下一題」後重新框選讀取，暫不判斷對錯。'));
  $('coachTitle').textContent = usable ? '先看看，我有沒有讀對。' : '我們先把題目看清楚。';
  $('coachText').textContent = `現在陪你練習${$('subject').value}，提示會依${$('grade').value}調整。`;
  return usable;
}
async function observe() {
  if (busy || paused || !stream || lessonActive) return;
  if (!$('cloud').checked) { notice('請先開啟雲端分析，才會將框選作業送至 OpenAI。'); return; }
  busy = true; const epoch = generation; const abort = new AbortController(); controller = abort;
  try {
    const image = captureImage(), sample = motionSample();
    setLessonActive(true); reading = true;
    gate.markSent(sample, performance.now()); status('Astra 正在看題目…');
    showProcessing('Astra 正在辨識題目…', '正在閱讀框選的作業與作答，接著會準備適合這一題的提示。');
    const data = await api('/api/observe', { image, ...context() }, abort.signal);
    if (epoch !== generation) return;
    reading = false; snapshot = image;
    const usable = applyObservation(data.observation); status('題目已讀取');
    busy = false;
    if (usable) await tutor(1, false, true);
  } catch (error) {
    if (epoch === generation && !snapshot && !$('question').value.trim()) setLessonActive(false);
    fail(error, epoch);
  }
  finally { if (epoch === generation) { reading = false; busy = false; controller = null; hideProcessing(); } config().catch(() => {}); }
}
function fail(error, epoch) {
  if (error.name === 'AbortError' || epoch !== generation) return;
  $('auto').checked = false; notice(error.message); status('自動分析已停止，可手動重試');
}
async function tutor(level = 1, confirm = confirmed, quiet = false) {
  if (busy || !$('question').value.trim()) return;
  if (!demoMode && !$('cloud').checked) { notice('請先開啟雲端分析。'); return; }
  busy = true; const epoch = generation; const abort = new AbortController(); controller = abort;
  status('Astra 正在整理提示…');
  showProcessing(demoMode ? '正在準備示範教學…' : (level === 3 ? 'Astra 正在整理說明與複習題…' : 'Astra 正在整理提示…'),
    demoMode ? '正在載入固定教材，這次不會呼叫 AI。' : (level === 3 ? '正在準備一步一步的說明，以及幫助理解的練習。' : '正在思考這一題，準備適合你的引導。'));
  try {
    const data = await api('/api/tutor', { ...context(), question: $('question').value.trim(),
      student_answer: $('answer').value.trim(), image: snapshot, confirmed: confirm,
      hint_level: level, demo: demoMode }, abort.signal);
    if (epoch !== generation) return;
    activeHint = data; confirmed = confirm; hintLevel = Math.max(hintLevel, quiet ? 0 : level);
    $('solution').disabled = !confirmed; $('hint').disabled = false;
    const labels = { correct: '答案相符', needs_work: '再一起檢查', in_progress: '還在作答中', uncertain: '待確認／開放題' };
    $('verdict').textContent = `${labels[data.verdict]} · ${data.verification === 'exact_arithmetic' ? '算式核算' : 'AI 建議'}`;
    if (!quiet) showHint(data.hint, Math.min(level, 2));
    $('coachTitle').textContent = data.concept || '一起想一想'; $('coachText').textContent = data.feedback;
    if (data.explanation) {
      $('explanation').textContent = data.explanation; $('explanationBlock').hidden = false;
      renderExercises(data.exercises);
    }
    if (!quiet) {
      session.push({ time: new Date().toISOString(), ...context(), question: $('question').value,
        student_answer: $('answer').value, verdict: data.verdict, verification: data.verification,
        hint_level: level, source: data.source, concept: data.concept });
    }
    notice(demoMode ? '示範模式：這是人工編寫的固定教材，沒有呼叫 AI，也沒有辨識真實影像。' : '');
    status(quiet ? '提示已準備好，先讓你想一想' : '慢慢來，我陪你想');
  } catch (error) { fail(error, epoch); }
  finally { if (epoch === generation) { busy = false; controller = null; hideProcessing(); } config().catch(() => {}); }
}
function showHint(text, level) {
  $('hintLabel').textContent = level ? `HINT ${String(level).padStart(2, '0')}` : 'TAKE YOUR TIME';
  $('hintTitle').textContent = level === 2 ? '再往前一小步' : '給你一個小方向';
  $('hintText').textContent = text;
  if ($('voice').checked) speak(text);
}
function speak(text) {
  const synth = window.speechSynthesis;
  if (!synth) { notice('此瀏覽器不支援語音朗讀。'); return; }
  const voice = synth.getVoices().find(v => v.localService && /^zh[-_]TW/i.test(v.lang)) ||
    synth.getVoices().find(v => v.localService && /^zh/i.test(v.lang));
  if (!voice) { notice('未找到已安裝的本機中文語音，請先在 macOS 下載中文語音。'); return; }
  synth.cancel(); const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = voice; utterance.lang = voice.lang; utterance.rate = 0.9; synth.speak(utterance);
}
function renderExercises(exercises) {
  $('exercises').replaceChildren(); currentExercises = exercises.map(e => ({ ...e, response: '' }));
  $('reviewEmpty').hidden = exercises.length > 0;
  currentExercises.forEach((exercise, i) => {
    const article = document.createElement('article'); article.className = 'exercise';
    const label = document.createElement('span'); label.className = 'eyebrow'; label.textContent = `TRY ${i + 1}`;
    const question = document.createElement('p'); question.textContent = exercise.question;
    const input = document.createElement('textarea'); input.placeholder = '先寫下自己的想法…'; input.maxLength = 2000;
    input.setAttribute('aria-label', `複習題 ${i + 1} 的回答`);
    input.addEventListener('input', () => { exercise.response = input.value; });
    const details = document.createElement('details'), summary = document.createElement('summary');
    summary.textContent = '我試過了，對照參考答案';
    const answer = document.createElement('p'); answer.textContent = `${exercise.answer}\n${exercise.explanation}`;
    answer.className = 'prewrap'; details.append(summary, answer);
    article.append(label, question, input, details); $('exercises').append(article);
  });
}
async function loadDemo() {
  if (lessonActive) return;
  stopCamera(); paused = true; demoMode = true; resetLesson();
  const epoch = generation;
  const response = await fetch(`/api/demo/${encodeURIComponent($('subject').value)}`);
  const data = await response.json(); if (epoch !== generation) return;
  view.width = 1200; view.height = 750; ctx.fillStyle = '#f6f3e9'; ctx.fillRect(0, 0, 1200, 750);
  ctx.fillStyle = '#fffefa'; ctx.fillRect(115, 55, 970, 640);
  ctx.fillStyle = '#7a8b7e'; ctx.font = '24px sans-serif'; ctx.fillText(`STUDY NOTES  /  ${$('subject').value}`, 170, 125);
  ctx.fillStyle = '#293f37'; ctx.font = '32px sans-serif';
  const text = data.observation.question; let line = '', y = 235;
  for (const char of text) { if (ctx.measureText(line + char).width > 850) { ctx.fillText(line, 170, y); y += 55; line = ''; } line += char; }
  ctx.fillText(line, 170, y); ctx.fillStyle = '#4775a1'; ctx.font = '40px sans-serif';
  ctx.fillText(data.observation.student_answer, 190, y + 110);
  ctx.strokeStyle = '#dfe7dc'; ctx.lineWidth = 2;
  for (let row = y + 130; row < 650; row += 60) { ctx.beginPath(); ctx.moveTo(170, row); ctx.lineTo(1030, row); ctx.stroke(); }
  $('placeholder').hidden = true; $('frameLabel').hidden = true; $('sourceBadge').textContent = '示範作業 · 無 AI 呼叫';
  $('resume').hidden = false; $('confidence').textContent = '人工編寫示範';
  applyObservation(data.observation); notice('示範模式使用固定教材，可體驗提示、解釋與複習流程。');
  status('正在體驗示範作業');
}
function point(event) { const r = view.getBoundingClientRect(); return { x: Math.max(0, Math.min(1, (event.clientX - r.left) / r.width)), y: Math.max(0, Math.min(1, (event.clientY - r.top) / r.height)) }; }
view.addEventListener('pointerdown', event => {
  if (!stream || paused) return; drag = point(event); view.setPointerCapture(event.pointerId); cameraChanged();
});
view.addEventListener('pointermove', event => {
  if (!drag) return; const p = point(event);
  roi = { x: Math.min(p.x, drag.x), y: Math.min(p.y, drag.y), w: Math.max(0.03, Math.abs(p.x - drag.x)), h: Math.max(0.03, Math.abs(p.y - drag.y)) };
  roi.w = Math.min(roi.w, 1 - roi.x); roi.h = Math.min(roi.h, 1 - roi.y);
});
function endDrag() {
  if (!drag) return; drag = null;
  if (roi.w < 0.05 || roi.h < 0.05) roi = { x: 0.06, y: 0.08, w: 0.88, h: 0.8 };
  gate.reset(performance.now()); status(lessonActive ? '框選已更新，本題保留到你按下一題' : '題目範圍已更新');
}
view.addEventListener('pointerup', endDrag); view.addEventListener('pointercancel', endDrag);
$('start').onclick = startCamera; $('resume').onclick = startCamera; $('camera').onchange = startCamera;
$('demo').onclick = () => loadDemo().catch(e => notice(e.message));
$('capture').onclick = observe;
$('pause').onclick = () => {
  paused = !paused; cancel();
  $('pause').textContent = paused ? '繼續陪讀' : '暫停陪讀'; $('capture').disabled = paused || lessonActive;
  gate.reset(performance.now()); status(paused ? '已暫停分析與提醒；鏡頭仍預覽' : '繼續陪讀');
};
$('resetCrop').onclick = () => { roi = { x: 0.06, y: 0.08, w: 0.88, h: 0.8 }; cameraChanged(); };
function setOrientation(horizontal, vertical) {
  if (!stream) return;
  // Keep the selected physical question in the frame as its display position changes.
  if (horizontal !== flipX) roi.x = Math.max(0, 1 - roi.x - roi.w);
  if (vertical !== flipY) roi.y = Math.max(0, 1 - roi.y - roi.h);
  flipX = horizontal; flipY = vertical; drag = null; latestSample = null;
  $('flipHorizontal').setAttribute('aria-pressed', String(flipX));
  $('flipVertical').setAttribute('aria-pressed', String(flipY));
  cameraChanged();
  status(paused ? '畫面方向已更新；陪讀仍暫停' : '畫面方向已更新，請確認框選題目');
  notice(lessonActive ? '畫面方向已更新；本題圖片與教學保留，按下一題後才使用新畫面。' : '預覽、框選截圖與停筆偵測已同步翻轉。');
}
$('flipHorizontal').onclick = () => setOrientation(!flipX, flipY);
$('flipVertical').onclick = () => setOrientation(flipX, !flipY);
$('resetOrientation').onclick = () => setOrientation(false, false);
$('confirm').onclick = () => tutor(1, true);
$('hint').onclick = () => {
  if (activeHint && hintLevel === 0) { showHint(activeHint.hint, 1); hintLevel = 1; return; }
  tutor(Math.min(2, hintLevel + 1));
};
$('solution').onclick = () => tutor(3, confirmed);
$('thinking').onclick = () => { gate.snooze(performance.now()); window.speechSynthesis?.cancel(); status('接下來兩分鐘不主動提醒'); };
$('speak').onclick = () => speak($('hintText').textContent);
$('voice').onchange = () => { if (!$('voice').checked) window.speechSynthesis?.cancel(); };
$('cloud').onchange = () => { cancel(); gate.reset(performance.now()); status($('cloud').checked ? '雲端分析已開啟' : '雲端分析已關閉'); };
for (const id of ['question', 'answer']) {
  $(id).addEventListener('focus', () => { editorFocused = true; });
  $(id).addEventListener('blur', () => { editorFocused = false; });
  $(id).addEventListener('input', () => {
    cancel(); confirmed = false; activeHint = null;
    if ($('question').value.trim()) setLessonActive(true);
    $('confirm').disabled = !$('question').value.trim();
    $('hint').disabled = !$('question').value.trim(); $('solution').disabled = true;
    $('verdict').textContent = '文字已修改，請重新確認';
    notice('原有提示、說明與複習作答保留；文字修改後，請按「文字正確，幫我看看」重新檢查。');
  });
}
for (const id of ['subject', 'grade']) $(id).onchange = () => {
  if (lessonActive) return;
  cameraChanged(); status('學習設定已更新，請讀取題目');
};
$('nextQuestion').onclick = () => {
  if (!lessonActive) return;
  if (currentExercises.length) session.push({ time: new Date().toISOString(), ...context(),
    question: $('question').value, review: currentExercises.map(exercise => ({ ...exercise })) });
  resetLesson(); demoMode = false;
  if (!stream) {
    ctx.clearRect(0, 0, view.width, view.height);
    $('placeholder').hidden = false; $('frameLabel').hidden = true;
    $('sourceBadge').textContent = '尚未開啟鏡頭';
  }
  status('準備下一題，請先框選題目');
  notice('上一題已結束。框選下一題後，可按「看一下這一題」或等待自動讀取。');
};
$('clear').onclick = async () => {
  cancel(); stopCamera(); paused = true; demoMode = false; resetLesson(); session = [];
  ctx.clearRect(0, 0, view.width, view.height); cropCtx.clearRect(0, 0, crop.width, crop.height);
  tinyCtx.clearRect(0, 0, 64, 48); latestSample = null;
  $('cloud').checked = false; $('placeholder').hidden = false; $('frameLabel').hidden = true; $('resume').hidden = true;
  $('sourceBadge').textContent = '尚未開啟鏡頭'; $('confidence').textContent = '等待畫面';
  $('coachTitle').textContent = '今天辛苦了，下次再一起學。'; $('coachText').textContent = '本機頁面的學習紀錄與圖片已清除。';
  status('已結束陪讀'); notice();
  try { await api('/api/clear', {}); } catch { notice('頁面資料已清除；後端清除失敗，請關閉本機服務以清空快取。'); }
};
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), events: session,
    review: currentExercises, note: 'AI 建議及自填練習紀錄，非正式成績。未包含作業影像。' }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = `study-session-${new Date().toISOString().slice(0, 10)}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
document.addEventListener('visibilitychange', () => {
  if (document.hidden && stream && !paused) {
    paused = true; cancel(); $('pause').textContent = '繼續陪讀'; $('capture').disabled = true; status('離開分頁，已暫停分析');
  }
});
window.addEventListener('pagehide', () => { cancel(); stopCamera(); });
config().catch(e => notice(e.message)); requestAnimationFrame(paint);

$('login').onclick = async () => {
  // The browser opens only the official URL returned by the local Codex login flow.
  try {
    const result = await api('/api/auth/login', {});
    const url = new URL(result.auth_url);
    if (url.protocol !== 'https:' || !['auth.openai.com', 'chatgpt.com'].includes(url.hostname)) throw new Error('登入網址不符合官方網域。');
    $('loginLink').href = url.href; $('loginLink').hidden = false;
    window.open(url.href, '_blank', 'noopener,noreferrer');
    notice('請在官方網頁完成登入，再按「登入後重新檢查」。若未跳出視窗，可點下方登入連結。');
  } catch (error) { notice(error.message); }
};
$('refreshAuth').onclick = () => config().then(() => {
  $('loginLink').hidden = true; notice('登入狀態已更新。');
}).catch(e => notice(e.message));
$('logout').onclick = async () => {
  cancel(); $('cloud').checked = false;
  try { await api('/api/auth/logout', {}); await config(); notice('已登出伴讀專案的 ChatGPT 帳號。'); }
  catch (error) { notice(error.message); }
};
