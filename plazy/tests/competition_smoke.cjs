const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PLAZY_URL || 'http://localhost:8094';

(async () => {
    const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && message.text().includes('compiling')) errors.push(message.text()); });
    try {
        for (const width of [1440, 390, 320]) {
            await page.setViewportSize({width, height: 950});
            const response = await page.goto(base + '/plazy/tournaments', {waitUntil: 'networkidle'});
            assert.equal(response.status(), 200);
            const tournament = await page.locator('.pz-tournament').first().getAttribute('href');
            for (const tab of ['overview', 'teams', 'fixtures', 'results', 'standings', 'bracket', 'rules']) {
                const result = await page.goto(base + tournament + '?tab=' + tab, {waitUntil: 'networkidle'});
                assert.equal(result.status(), 200, `${width}: ${tab}`);
                assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${width}: ${tab} overflow`);
                assert.equal(await page.locator('h1').count(), 1);
                assert.equal(await page.locator('.pz-competition').evaluate(el => getComputedStyle(el).maxWidth), '1200px');
                if (tab === 'standings' || tab === 'bracket') await page.screenshot({path: `/tmp/plazy-competition-${tab}-${width}.png`, fullPage: true});
                if (tab === 'bracket') {
                    assert.ok(await page.locator('.pz-bracket-match').count() > 0);
                    assert.equal((await page.locator('.pz-bracket').innerText()).includes('built-in'), false);
                }
            }
            await page.goto(base + tournament + '?tab=results');
            const match = await page.locator('.pz-fixture').first().getAttribute('href');
            assert.equal((await page.goto(base + match)).status(), 200);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        }
        assert.deepEqual(errors, []);
        console.log('PASS: all seven tournament tabs and match centre at 1440, 390 and 320 pixels; no JS errors or document overflow.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
