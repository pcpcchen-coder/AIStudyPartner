import { test, expect } from '@playwright/test';

const models = ['astra', 'sol', 'luna'].map(name => ({
  id: `gpt-6-${name}`, label: `GPT-6 ${name[0].toUpperCase()}${name.slice(1)}`,
}));
async function setup(page) {
  await page.route('**/api/config', route => route.fulfill({ json: {
    token: 'mock-token', authenticated: true, model: 'gpt-6-astra', models,
    message: '模型權限依帳號為準', calls: 0, max_calls: 120, input_tokens: 0, output_tokens: 0,
  } }));
  await page.goto('/');
  await expect(page.locator('#modelStatus')).toHaveText('模型權限依帳號為準');
}
const teaching = { hint: '試試看先算十位數。', concept: '加法', feedback: '慢慢想',
  verdict: 'needs_work', verification: 'ai_advisory', explanation: '完整說明',
  exercises: [{ question: '12+3=?', answer: '15', explanation: '十位數與個位數分開算' }], source: 'openai' };

test('selection persists, preserves teaching, and routes new requests to selected model', async ({ page }) => {
  const used = [];
  await page.route('**/api/tutor', route => {
    used.push(route.request().postDataJSON().model);
    return route.fulfill({ json: teaching });
  });
  await setup(page);
  await expect(page.locator('#model option')).toHaveText(models.map(model => model.label));
  await page.locator('#model').selectOption('gpt-6-sol');
  await page.reload();
  await expect(page.locator('#model')).toHaveValue('gpt-6-sol');
  await page.locator('#question').fill('12+3=?');
  await page.locator('#cloud').check();
  await page.locator('#confirm').click();
  await expect(page.locator('#hintText')).toHaveText(teaching.hint);
  await page.getByLabel('複習題 1 的回答').fill('我的作答');
  await page.locator('#model').selectOption('gpt-6-luna');
  await expect(page.locator('#hintText')).toHaveText(teaching.hint);
  await expect(page.locator('#explanation')).toHaveText('完整說明');
  await expect(page.getByLabel('複習題 1 的回答')).toHaveValue('我的作答');
  await page.locator('#hint').click();
  await expect.poll(() => used).toEqual(['gpt-6-sol', 'gpt-6-luna']);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('camera and follow-up teaching keep the same model while the modal is busy', async ({ page }) => {
  let finish;
  const hold = new Promise(resolve => { finish = resolve; });
  const used = [];
  await page.route('**/api/observe', async route => {
    used.push(route.request().postDataJSON().model);
    await hold;
    await route.fulfill({ json: { observation: { question: '12+3=?', student_answer: '',
      quality: 'clear', confidence: 0.99, clarification: '', subject: '數學' } } });
  });
  await page.route('**/api/tutor', route => {
    used.push(route.request().postDataJSON().model);
    return route.fulfill({ json: teaching });
  });
  await setup(page);
  await page.locator('#model').selectOption('gpt-6-luna');
  await page.locator('#start').click();
  await page.locator('#cloud').check();
  await page.locator('#capture').click();
  await expect(page.locator('#model')).toBeDisabled();
  await expect(page.locator('#processingTitle')).toHaveText('AI 正在辨識題目…');
  finish();
  await expect(page.locator('#processingDialog')).not.toBeVisible();
  await expect(page.locator('#model')).toBeEnabled();
  expect(used).toEqual(['gpt-6-luna', 'gpt-6-luna']);
});
