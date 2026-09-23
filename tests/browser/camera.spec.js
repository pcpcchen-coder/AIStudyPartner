import { test, expect } from '@playwright/test';

// An asymmetric, synthetic camera image proves actual pixel orientation and ROI mapping.
// No physical camera, student image or model request is used.
test('flips preview and captured ROI together in every orientation', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      const context = canvas.getContext('2d');
      for (const [color, x, y] of [['red', 0, 0], ['lime', 320, 0], ['blue', 0, 240], ['yellow', 320, 240]]) {
        context.fillStyle = color; context.fillRect(x, y, 320, 240);
      }
      window.syntheticCamera = canvas;
      return canvas.captureStream(5);
    };
  });
  const captures = [];
  await page.route('**/api/observe', async route => {
    captures.push(route.request().postDataJSON().image);
    await route.fulfill({ json: { source: 'openai', observation: {
      question: 'test question', student_answer: '', subject: '數學', concept: '',
      confidence: 0.2, quality: 'blurred', clarification: 'synthetic test only',
    } } });
  });
  await page.goto('/');
  await expect(page.locator('#flipHorizontal')).toBeDisabled();
  await page.locator('.settings summary').click(); await page.locator('#auto').uncheck();
  await page.locator('#start').click(); await expect(page.locator('#capture')).toBeEnabled();
  await page.locator('#cloud').check();
  const box = await page.locator('#view').boundingBox();
  await page.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.1);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.7);
  await page.mouse.up();

  async function colors(image = null) {
    return page.evaluate(async image => {
      let canvas = document.querySelector('#view');
      if (image) {
        const decoded = new Image(); decoded.src = image; await decoded.decode();
        canvas = document.createElement('canvas'); canvas.width = decoded.width; canvas.height = decoded.height;
        canvas.getContext('2d').drawImage(decoded, 0, 0);
      }
      const points = image ? [[.15,.15],[.85,.15],[.15,.85],[.85,.85]] : [[.25,.25],[.75,.25],[.25,.75],[.75,.75]];
      return points.map(([x, y]) => {
        const [r, g, b] = canvas.getContext('2d').getImageData(Math.floor(x * canvas.width), Math.floor(y * canvas.height), 1, 1).data;
        if (r > 120 && g > 120 && b < 80) return 'yellow';
        if (r > g * 2 && r > b * 2) return 'red';
        if (g > r * 2 && g > b * 2) return 'green';
        if (b > r * 2 && b > g * 2) return 'blue';
        return [r, g, b];
      });
    }, image);
  }
  for (const [button, horizontal, vertical, expected] of [
    [null, false, false, ['red', 'green', 'blue', 'yellow']],
    ['flipHorizontal', true, false, ['green', 'red', 'yellow', 'blue']],
    ['flipVertical', true, true, ['yellow', 'blue', 'green', 'red']],
    ['flipHorizontal', false, true, ['blue', 'yellow', 'red', 'green']],
    ['resetOrientation', false, false, ['red', 'green', 'blue', 'yellow']],
  ]) {
    if (button) {
      await page.locator(`#${button}`).click();
      await expect(page.locator('#question')).toHaveValue('');
    }
    await expect(page.locator('#flipHorizontal')).toHaveAttribute('aria-pressed', String(horizontal));
    await expect(page.locator('#flipVertical')).toHaveAttribute('aria-pressed', String(vertical));
    await expect.poll(() => colors()).toEqual(expected);
    const count = captures.length;
    await page.locator('#capture').click();
    await expect(page.locator('#question')).toHaveValue('test question');
    expect(captures.length).toBe(count + 1);
    expect(await colors(captures.at(-1))).toEqual(expected);
  }
  await page.locator('#pause').click();
  await page.locator('#flipVertical').click();
  await expect(page.locator('#capture')).toBeDisabled();
  await expect(page.locator('#status')).toContainText('仍暫停');
  await expect.poll(() => colors()).toEqual(['blue', 'yellow', 'red', 'green']);
  await page.locator('#clear').click();
  await expect(page.locator('#flipVertical')).toBeDisabled();
});
