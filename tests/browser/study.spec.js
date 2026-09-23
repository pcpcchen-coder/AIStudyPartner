import { test, expect } from '@playwright/test';

test('demo gives progressive hints, explanation and review without cloud requests', async ({ page }) => {
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await page.getByRole('button', { name: '先用示範作業試試' }).click();
  await expect(page.locator('#question')).toHaveValue('24 ÷ 3 + 5 = ?');
  await expect(page.locator('#cloud')).not.toBeChecked();
  await page.getByRole('button', { name: '文字正確，幫我看看' }).click();
  await expect(page.locator('#verdict')).toContainText('算式核算');
  await expect(page.locator('#hintText')).not.toContainText('13');
  await page.getByRole('button', { name: '給我提示' }).click();
  await expect(page.locator('#hintLabel')).toHaveText('HINT 02');
  await page.getByRole('button', { name: '我已試過，想看完整說明與複習題' }).click();
  await expect(page.locator('#explanation')).toContainText('13');
  await expect(page.locator('.exercise')).toHaveCount(2);
  await expect(page.locator('.exercise details').first()).not.toHaveAttribute('open');
  await page.locator('.exercise textarea').first().fill('10');
  await page.locator('.exercise summary').first().click();
  await expect(page.locator('.exercise details').first()).toHaveAttribute('open');
  await page.screenshot({ path: 'test-results/demo-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '結束並清除' }).click();
  await expect(page.locator('#question')).toHaveValue('');
  await expect(page.locator('.exercise')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('subject switch invalidates old lesson; open-ended answers remain advisory', async ({ page }) => {
  await page.goto('/'); await page.locator('#demo').click();
  await page.locator('#subject').selectOption('英文');
  await expect(page.locator('#question')).toHaveValue(/She/);
  await page.locator('#confirm').click();
  await expect(page.locator('#hintText')).toContainText('主詞');
  await page.locator('#subject').selectOption('國語');
  await expect(page.locator('#solution')).toBeDisabled();
  await page.locator('#confirm').click();
  await expect(page.locator('#verdict')).toContainText('開放題');
  await page.locator('#answer').fill('修改文字');
  await expect(page.locator('#solution')).toBeDisabled();
});

test('fake camera starts locally and pause prevents analysis', async ({ page }) => {
  const observations = [];
  page.on('request', r => { if (r.url().endsWith('/api/observe')) observations.push(r); });
  await page.goto('/'); await page.locator('#start').click();
  await expect(page.locator('#sourceBadge')).toHaveText('即時鏡頭 · 本機預覽');
  await page.locator('#capture').click();
  await expect(page.locator('#notice')).toContainText('請先開啟雲端分析');
  expect(observations).toHaveLength(0);
  await page.locator('#pause').click();
  await expect(page.locator('#status')).toContainText('已暫停');
  await expect(page.locator('#capture')).toBeDisabled();
  await page.locator('#clear').click();
  await expect(page.locator('#placeholder')).toBeVisible();
});

test('mobile layout has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/');
  await expect(page.locator('#start')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/mobile.png', fullPage: true });
});

test('OAuth login exposes only an official browser URL, no API key form', async ({ page, context }) => {
  await context.route('https://auth.openai.com/**', route => route.fulfill({ body: 'Mock official login' }));
  await page.route('**/api/auth/login', route => route.fulfill({ json: { auth_url: 'https://auth.openai.com/authorize?state=test-only' } }));
  await page.goto('/');
  const popupPromise = page.waitForEvent('popup');
  await page.locator('#login').click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/auth.openai.com/);
  await expect(page.locator('#loginLink')).toHaveAttribute('href', /auth.openai.com/);
  expect(await page.locator('input[type=password]').count()).toBe(0);
});

test('clearing during an in-flight observation cannot restore old homework', async ({ page }) => {
  let resolveObserved;
  const observed = new Promise(resolve => { resolveObserved = resolve; });
  let release;
  const delayed = new Promise(resolve => { release = resolve; });
  await page.route('**/api/observe', async route => {
    resolveObserved(); await delayed;
    await route.fulfill({ json: { source: 'openai', observation: { question: 'OLD HOMEWORK', student_answer: 'old', subject: '數學', confidence: 0.2, quality: 'blurred', clarification: 'retry', concept: 'old' } } }).catch(() => {});
  });
  await page.goto('/'); await page.locator('.settings summary').click(); await page.locator('#auto').uncheck();
  await page.locator('#start').click(); await expect(page.locator('#capture')).toBeEnabled();
  await page.locator('#cloud').check(); await page.locator('#capture').click(); await observed;
  await page.locator('#clear').click(); release();
  await expect(page.locator('#question')).toHaveValue('');
  await expect(page.locator('#coachTitle')).toContainText('今天辛苦了');
});
