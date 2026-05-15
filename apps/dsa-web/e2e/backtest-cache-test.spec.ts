import { test, expect } from '@playwright/test';

test('debug network requests on repeat load', async ({ page }) => {
  const networkLog: Array<{url: string, method: string}> = [];
  page.on('request', req => {
    networkLog.push({url: req.url(), method: req.method()});
  });
  
  await page.goto('http://localhost:5173/backtest');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2000);
  
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button'))
      .find(b => b.textContent?.includes('纯技术回测'));
    if (btn) btn.click();
  });
  await page.waitForTimeout(1000);
  
  // First load
  console.log('--- First load ---');
  await page.locator('input[placeholder*="股票代码"]').first().fill('600519');
  await page.locator('button', { hasText: '加载K线' }).click();
  await page.waitForTimeout(5000);
  
  const firstRequests = networkLog.filter(r => r.url.includes('/chart'));
  firstRequests.forEach(r => console.log('REQ1:', r.url));
  
  // Clear log
  networkLog.length = 0;
  
  // Second load
  console.log('--- Second load ---');
  await page.locator('button', { hasText: '加载K线' }).click();
  await page.waitForTimeout(5000);
  
  const secondRequests = networkLog.filter(r => r.url.includes('/chart'));
  secondRequests.forEach(r => console.log('REQ2:', r.url));
  
  console.log('First load requests:', firstRequests.length);
  console.log('Second load requests:', secondRequests.length);
});
