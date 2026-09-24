import { test, expect } from '@playwright/test';

function deferred() {
  let resolve;
  return { promise: new Promise(done => { resolve = done; }), resolve: () => resolve() };
}
const observation = { observation: { question: '8 + 2 = ?', student_answer: '9',
  quality: 'clear', confidence: 0.95, clarification: '', concept: '加法', subject: '數學' } };
const teaching = { hint: '從 8 再往後數兩個數。', concept: '加法', feedback: '一起想想',
  verdict: 'needs_work', verification: 'model', explanation: '', exercises: [], source: 'openai' };
async function setup(page, withCamera = false) {
  await page.route('**/api/config', route => route.fulfill({ json: {
    token: 'mock-token', authenticated: true, model: 'gpt-6-astra', message: '測試用',
    calls: 0, max_calls: 120, input_tokens: 0, output_tokens: 0,
  } }));
  await page.goto('/');
  await page.locator('.settings summary').click(); await page.locator('#auto').uncheck();
  if (withCamera) {
    await page.locator('#start').click(); await expect(page.locator('#capture')).toBeEnabled();
  } else {
    await page.locator('#question').fill('8 + 2 = ?');
  }
  await page.locator('#cloud').check();
}

test('full-page modal blocks background and stays open from recognition through hint preparation', async ({ page }) => {
  const read = deferred(), teach = deferred();
  await page.route('**/api/observe', async route => {
    await read.promise; await route.fulfill({ json: observation });
  });
  await page.route('**/api/tutor', async route => {
    await teach.promise; await route.fulfill({ json: teaching });
  });
  await setup(page, true); await page.clock.install();
  await page.evaluate(() => {
    window.processingCloses = 0;
    document.querySelector('#processingDialog').addEventListener('close', () => window.processingCloses++);
  });
  await page.locator('#capture').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(page.locator('#processingTitle')).toContainText('AI 正在辨識');
  expect(await dialog.evaluate(element => element.matches(':modal'))).toBe(true);
  await expect(page.locator('main')).toHaveAttribute('aria-busy', 'true');
  expect(await dialog.boundingBox()).toMatchObject({ x: 0, y: 0, width: 1440, height: 1100 });
  // Attempt to click the covered clear button and tab into the background.
  const clear = await page.locator('#clear').boundingBox();
  await page.mouse.click(clear.x + clear.width / 2, clear.y + clear.height / 2);
  await expect(dialog).toBeVisible();
  await expect(page.locator('#sourceBadge')).toHaveText('即時鏡頭 · 本機預覽');
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.querySelector('#processingDialog').contains(document.activeElement))).toBe(true);
  await page.clock.fastForward(21000);
  await expect(page.locator('#processingElapsed')).toContainText('已等待 21 秒');
  await page.screenshot({ path: 'test-results/processing-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('#cancelProcessing')).toBeInViewport();
  expect(await dialog.evaluate(element => element.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/processing-mobile.png' });
  read.resolve();
  await expect(page.locator('#processingTitle')).toContainText('正在整理提示');
  expect(await page.evaluate(() => window.processingCloses)).toBe(0);
  await expect(dialog).toBeVisible();
  teach.resolve();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('main')).not.toHaveAttribute('aria-busy');
  await expect(page.locator('#question')).toHaveValue('8 + 2 = ?');
  await expect(page.locator('#confirm')).toBeEnabled();
});

for (const action of ['observe', 'tutor']) {
  test(`${action} failure removes the overlay and allows retry`, async ({ page }) => {
    const release = deferred();
    await page.route(`**/api/${action}`, async route => {
      await release.promise;
      await route.fulfill({ status: 503, json: { detail: '測試：服務暫時無法使用，請重試。' } });
    });
    await setup(page, action === 'observe');
    await page.locator(action === 'observe' ? '#capture' : '#confirm').click();
    await expect(page.getByRole('dialog')).toBeVisible();
    release.resolve();
    await expect(page.getByRole('dialog')).not.toBeVisible();
    await expect(page.locator('#notice')).toContainText('服務暫時無法使用');
    await expect(page.locator(action === 'observe' ? '#capture' : '#confirm')).toBeEnabled();
    await expect(page.locator('html')).not.toHaveClass(/processing/);
    if (action === 'tutor') await expect(page.locator('#question')).toHaveValue('8 + 2 = ?');
  });
}

test('cancel and Escape preserve the lesson; an old response cannot dismiss a new overlay', async ({ page }) => {
  const first = deferred(), second = deferred(), firstStarted = deferred(), secondStarted = deferred();
  let calls = 0;
  await page.route('**/api/tutor', async route => {
    const index = ++calls;
    (index === 1 ? firstStarted : secondStarted).resolve();
    await (index === 1 ? first : second).promise;
    await route.fulfill({ json: teaching }).catch(() => {});
  });
  await setup(page);
  await page.locator('#confirm').click(); await firstStarted.promise;
  await page.locator('#cancelProcessing').click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#question')).toHaveValue('8 + 2 = ?');
  await expect(page.locator('#auto')).not.toBeChecked();
  await page.locator('#confirm').click(); await secondStarted.promise;
  first.resolve();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('#processingTitle')).toContainText('正在整理提示');
  await page.keyboard.press('Escape'); second.resolve();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#question')).toHaveValue('8 + 2 = ?');
  await expect(page.locator('#notice')).toContainText('原有教學仍保留');
  await expect(page.locator('#confirm')).toBeEnabled();
});
