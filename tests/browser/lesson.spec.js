import { test, expect } from '@playwright/test';

async function camera(page) {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 640, 480);
      window.syntheticCamera = canvas;
      window.syntheticStream = canvas.captureStream(10);
      return window.syntheticStream;
    };
  });
  await page.goto('/');
  await page.locator('.settings summary').click();
  await page.locator('#auto').uncheck();
  await page.locator('#start').click();
  await expect(page.locator('#capture')).toBeEnabled();
  await expect.poll(() => page.locator('#view').evaluate(canvas =>
    canvas.getContext('2d').getImageData(320, 240, 1, 1).data[0])).toBe(255);
  await page.locator('#cloud').check();
}
function observation(question = '第一題') {
  return { observation: { question, student_answer: '2', subject: '數學', concept: '測試',
    quality: 'clear', confidence: 0.95, clarification: '' }, source: 'openai' };
}
function teaching(level) {
  return { hint: `提示層級 ${Math.min(level, 2)}`, concept: '測試概念', feedback: '一起學習',
    verdict: 'needs_work', verification: 'model', source: 'openai',
    explanation: level === 3 ? '保留完整教學說明' : '',
    exercises: level === 3 ? [{ question: '練習題', answer: '4', explanation: '練習說明' }] : [] };
}
async function moveCamera(page, color) {
  const previous = await page.locator('#view').evaluate(canvas => canvas.toDataURL());
  await page.evaluate(color => {
    const ctx = window.syntheticCamera.getContext('2d');
    ctx.fillStyle = color; ctx.fillRect(0, 0, 640, 480);
    window.syntheticStream.getVideoTracks()[0].requestFrame();
  }, color);
  await expect.poll(() => page.locator('#view').evaluate((canvas, previous) =>
    canvas.toDataURL() !== previous, previous)).toBe(true);
}

test('movement, idle, crop and flips preserve teaching and answers until explicit next', async ({ page }) => {
  const captures = [], requests = [];
  await page.route('**/api/observe', async route => {
    captures.push(route.request().postDataJSON());
    await route.fulfill({ json: observation(captures.length === 1 ? '第一題' : '第二題') });
  });
  await page.route('**/api/tutor', async route => {
    const data = route.request().postDataJSON(); requests.push(data);
    await route.fulfill({ json: teaching(data.hint_level) });
  });
  await camera(page);
  await page.locator('#capture').click();
  await expect(page.locator('#status')).toContainText('提示已準備好');
  await page.locator('#confirm').click();
  await expect(page.locator('#hintLabel')).toHaveText('HINT 01');
  await page.locator('#hint').click();
  await expect(page.locator('#hintLabel')).toHaveText('HINT 02');
  await page.locator('#solution').click();
  await expect(page.locator('#explanation')).toHaveText('保留完整教學說明');
  await page.locator('.exercise textarea').fill('我的作答，還在想');
  await page.locator('.exercise summary').click();
  const requestCount = requests.length;
  await page.locator('#auto').check();
  await page.clock.install();
  // Large changes exceed both the old re-recognition threshold and motion threshold.
  for (const color of ['black', 'white', 'red']) {
    await moveCamera(page, color);
    await page.clock.runFor(600);
    await page.clock.fastForward(65000);
    await page.clock.runFor(600);
  }
  await page.locator('#flipHorizontal').click();
  await page.locator('#flipVertical').click();
  await page.locator('#resetCrop').click();
  await page.locator('#camera').selectOption({ index: 0 });
  await expect(page.locator('#status')).toContainText('本題教學繼續保留');
  await moveCamera(page, 'blue');
  const box = await page.locator('#view').boundingBox();
  await page.mouse.move(box.x + box.width * .2, box.y + box.height * .2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .6, box.y + box.height * .6);
  await page.mouse.up();
  await page.clock.fastForward(65000); await page.clock.runFor(600);
  await expect(page.locator('#question')).toHaveValue('第一題');
  await expect(page.locator('#hintLabel')).toHaveText('HINT 02');
  await expect(page.locator('#hintText')).toHaveText('提示層級 2');
  await expect(page.locator('#explanationBlock')).toBeVisible();
  await expect(page.locator('.exercise textarea')).toHaveValue('我的作答，還在想');
  await expect(page.locator('.exercise details')).toHaveAttribute('open');
  await expect(page.locator('#capture')).toBeDisabled();
  expect(captures).toHaveLength(1); expect(requests).toHaveLength(requestCount);
  // Editing an answer preserves the existing lesson but requires confirmation again.
  await page.locator('#answer').fill('3');
  await expect(page.locator('#solution')).toBeDisabled();
  await expect(page.locator('#hintText')).toHaveText('提示層級 2');
  await expect(page.locator('#explanationBlock')).toBeVisible();
  await expect(page.locator('.exercise textarea')).toHaveValue('我的作答，還在想');
  await page.locator('#confirm').click();
  await expect.poll(() => requests.length).toBe(requestCount + 1);
  expect(requests.at(-1).image).toBe(captures[0].image);
  await expect(page.locator('#status')).toContainText('慢慢來');
  await page.locator('#auto').uncheck();
  await page.locator('#nextQuestion').click();
  await expect(page.locator('#question')).toHaveValue('');
  await expect(page.locator('#explanationBlock')).toBeHidden();
  await expect(page.locator('.exercise')).toHaveCount(0);
  await expect(page.locator('#hintLabel')).toHaveText('A SMALL NUDGE');
  await expect(page.locator('#subject')).toBeEnabled();
  await expect(page.locator('#capture')).toBeEnabled();
  await page.locator('#auto').check();
  await page.clock.fastForward(3000); await page.clock.runFor(600);
  await expect(page.locator('#question')).toHaveValue('第二題');
  expect(captures).toHaveLength(2);
  expect(captures[1].image).not.toBe(captures[0].image);
});

test('movement during initial recognition keeps its captured question; next discards delayed teaching', async ({ page }) => {
  let releaseObservation, releaseTutor, tutorStarted;
  const observationWait = new Promise(resolve => { releaseObservation = resolve; });
  const tutorWait = new Promise(resolve => { releaseTutor = resolve; });
  const started = new Promise(resolve => { tutorStarted = resolve; });
  await page.route('**/api/observe', async route => {
    await observationWait; await route.fulfill({ json: observation() });
  });
  await page.route('**/api/tutor', async route => {
    tutorStarted(); await tutorWait;
    await route.fulfill({ json: teaching(3) }).catch(() => {});
  });
  await camera(page); await page.locator('#capture').click();
  await expect(page.locator('#nextQuestion')).toBeEnabled();
  await moveCamera(page, 'black');
  releaseObservation();
  await expect(page.locator('#question')).toHaveValue('第一題');
  await started;
  await page.locator('#cancelProcessing').click();
  await page.locator('#nextQuestion').click(); releaseTutor();
  await expect(page.locator('#question')).toHaveValue('');
  await expect(page.locator('#explanationBlock')).toBeHidden();
  await expect(page.locator('.exercise')).toHaveCount(0);
  await expect(page.locator('#coachTitle')).toHaveText('不急，我在這裡。');
});

test('cancelling the first read allows retry after pausing and resuming', async ({ page }) => {
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  await page.route('**/api/observe', async route => {
    await wait;
    await route.fulfill({ json: observation() }).catch(() => {});
  });
  await camera(page); await page.locator('#capture').click();
  await expect(page.locator('#nextQuestion')).toBeEnabled();
  await page.locator('#cancelProcessing').click();
  await page.locator('#pause').click();
  await expect(page.locator('#capture')).toBeDisabled();
  await page.locator('#pause').click(); release();
  await expect(page.locator('#capture')).toBeEnabled();
  await expect(page.locator('#question')).toHaveValue('');
});

async function prepareReread(page, rereadResponse) {
  const captures = [], requests = [];
  await page.route('**/api/observe', async route => {
    captures.push(route.request().postDataJSON());
    if (captures.length === 1) await route.fulfill({ json: observation() });
    else await rereadResponse(route);
  });
  await page.route('**/api/tutor', async route => {
    const body = route.request().postDataJSON(); requests.push(body);
    await route.fulfill({ json: teaching(body.hint_level) });
  });
  await camera(page);
  await expect(page.locator('#reread')).toBeDisabled();
  await page.locator('#capture').click();
  await expect(page.locator('#status')).toContainText('提示已準備好');
  await page.locator('#confirm').click();
  await expect(page.locator('#solution')).toBeEnabled();
  await page.locator('#solution').click();
  await expect(page.locator('#explanationBlock')).toBeVisible();
  await page.locator('.exercise textarea').fill('保留我的練習作答');
  return { captures, requests };
}
async function expectOriginalLesson(page) {
  await expect(page.locator('#question')).toHaveValue('第一題');
  await expect(page.locator('#explanation')).toHaveText('保留完整教學說明');
  await expect(page.locator('#explanationBlock')).toBeVisible();
  await expect(page.locator('.exercise textarea')).toHaveValue('保留我的練習作答');
  await expect(page.locator('#solution')).toBeEnabled();
}

test('reread commits a fresh camera snapshot only after success and requires confirmation again', async ({ page }) => {
  let finish;
  const hold = new Promise(resolve => { finish = resolve; });
  const { captures, requests } = await prepareReread(page, async route => {
    await hold; await route.fulfill({ json: observation('修正後的本題') });
  });
  await page.locator('#pause').click();
  await expect(page.locator('#reread')).toBeDisabled();
  await page.locator('#pause').click();
  await expect(page.locator('#reread')).toBeEnabled();
  await moveCamera(page, 'black');
  await page.locator('#reread').click();
  await expect(page.locator('#processingTitle')).toHaveText('AI 正在重新讀取本題…');
  await expect(page.locator('#reread')).toBeDisabled();
  await expectOriginalLesson(page);
  finish();
  await expect(page.locator('#processingDialog')).not.toBeVisible();
  await expect(page.locator('#question')).toHaveValue('修正後的本題');
  await expect(page.locator('#solution')).toBeDisabled();
  await expect(page.locator('#explanationBlock')).toBeHidden();
  await expect(page.locator('.exercise')).toHaveCount(0);
  expect(captures).toHaveLength(2);
  expect(captures[1].image).not.toBe(captures[0].image);
  expect(requests).toHaveLength(3); // Rereading itself does not start teaching.
  await page.locator('#confirm').click();
  await expect.poll(() => requests.length).toBe(4);
  expect(requests.at(-1).image).toBe(captures[1].image);
  expect(requests.at(-1).question).toBe('修正後的本題');
});

for (const result of ['error', 'unclear', 'cancel']) {
  test(`reread ${result} preserves the complete lesson and its original image`, async ({ page }) => {
    let finish;
    const hold = new Promise(resolve => { finish = resolve; });
    const { captures, requests } = await prepareReread(page, async route => {
      await hold;
      const response = observation('不應覆蓋本題');
      if (result === 'unclear') Object.assign(response.observation, { confidence: 0.2, quality: 'blurred' });
      await route.fulfill(result === 'error'
        ? { status: 503, json: { detail: '測試：重新辨識失敗' } }
        : { json: response }).catch(() => {});
    });
    await moveCamera(page, 'black');
    await page.locator('#reread').click();
    await expect(page.locator('#processingDialog')).toBeVisible();
    await expect.poll(() => captures.length).toBe(2);
    if (result === 'cancel') await page.locator('#cancelProcessing').click();
    finish();
    await expect(page.locator('#processingDialog')).not.toBeVisible();
    await expectOriginalLesson(page);
    await expect(page.locator('#reread')).toBeEnabled();
    // A later teaching request must still use the original captured image.
    const count = requests.length;
    await page.locator('#confirm').click();
    await expect.poll(() => requests.length).toBe(count + 1);
    expect(requests.at(-1).image).toBe(captures[0].image);
    expect(requests.at(-1).question).toBe('第一題');
  });
}

test('reread cannot bypass cloud consent', async ({ page }) => {
  const { captures } = await prepareReread(page, route => route.fulfill({ json: observation() }));
  await page.locator('#cloud').uncheck();
  await page.locator('#reread').click();
  await expect(page.locator('#cloudReminder')).toBeVisible();
  expect(captures).toHaveLength(1);
  await expectOriginalLesson(page);
});
