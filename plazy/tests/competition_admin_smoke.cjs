const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PLAZY_URL || 'http://localhost:8094';

(async () => {
    if (!process.env.PLAZY_ADMIN_PASSWORD) throw new Error('Set credentials for the isolated review database.');
    const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
    const page = await browser.newPage();
    try {
        await page.goto(base + '/web/login');
        await page.locator('input[name="login"]').fill(process.env.PLAZY_ADMIN_LOGIN || 'admin');
        await page.locator('input[name="password"]').fill(process.env.PLAZY_ADMIN_PASSWORD);
        await page.locator('button[type="submit"]').click();
        await page.waitForURL(url => !url.pathname.includes('/web/login'));
        for (const width of [1440, 390]) {
            await page.setViewportSize({width, height: 950});
            assert.equal((await page.goto(base + '/plazy/competition/dashboard', {waitUntil: 'networkidle'})).status(), 200);
            await page.screenshot({path: `/tmp/plazy-competition-admin-${width}.png`, fullPage: true});
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            const link = page.locator('a.pz-invite-row[href^="/plazy/admin/tournament/"]').first();
            await link.click();
            await page.waitForLoadState('networkidle');
            assert.ok(await page.locator('.pz-table tbody tr').count() > 0);
            await page.locator('a[href$="/result"]').first().click();
            await page.waitForLoadState('networkidle');
            assert.ok(await page.locator('textarea[name="reason"]').count() > 0);
            assert.equal((await page.goto(base + '/plazy/admin/tournament/new', {waitUntil: 'networkidle'})).status(), 200);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        }
        console.log('PASS: administrator dashboard, tournament management, correction screen and tournament creation form on desktop/mobile.');
    } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
