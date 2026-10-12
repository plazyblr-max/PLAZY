// Run against an upgraded local Odoo database. Requires Playwright.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
    const browser = await chromium.launch({
        headless: true,
        ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
    });
    const baseURL = process.env.PLAZY_URL || 'http://localhost:8092';
    const errors = [];
    try {
        const page = await browser.newPage();
        page.on('pageerror', error => errors.push(error.message));
        for (const width of [320, 390, 768, 1440]) {
            await page.setViewportSize({ width, height: 900 });
            await page.goto(baseURL, { waitUntil: 'networkidle' });
            assert.match(await page.title(), /PLAZY Football.*More Than a Game/);
            assert.equal(await page.locator('main > section').count(), 10);
            assert.equal(await page.locator('h1').count(), 1);
            assert.equal(await page.locator('main').count(), 1);
            assert.equal(await page.locator('meta[property="og:image"]').count(), 1);
            assert.equal(await page.locator('link[rel="canonical"]').count(), 1);
            assert.match(await page.locator('h1').evaluate(el => getComputedStyle(el).fontFamily), /Plazy Display/);
            for (const section of await page.locator('main > section').all()) {
                await section.scrollIntoViewIfNeeded();
                assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            }
            if (width < 801) {
                await page.evaluate(() => scrollTo(0, 0));
                await page.locator('.plazy-mobile-nav summary').click();
                assert.notEqual(await page.locator('.fa-bars').evaluate(el => getComputedStyle(el, '::before').content), 'none');
                assert.equal(await page.locator('.plazy-mobile-nav').getAttribute('open'), '');
                await page.keyboard.press('Escape');
                assert.equal(await page.locator('.plazy-mobile-nav').getAttribute('open'), null);
                await page.locator('.plazy-mobile-nav summary').click();
                await page.locator('.plazy-mobile-nav a[href="/#story"]').click();
                assert.equal(await page.locator('.plazy-mobile-nav').getAttribute('open'), null);
            }
        }
        await page.goto(baseURL);
        const links = await page.locator('a[href]').evaluateAll(elements =>
            [...new Set(elements.map(el => el.getAttribute('href')))].filter(href => href.startsWith('/')));
        for (const href of links) {
            const response = await page.request.get(baseURL + href);
            assert.ok(response.status() < 400, href + ': ' + response.status());
        }
        for (const path of ['/web/login', '/plazy/player/join', '/plazy/team/join', '/plazy/forgot-password']) {
            await page.goto(baseURL + path);
            assert.ok(await page.locator('form input[name="csrf_token"]').count(), path);
            assert.ok(await page.locator('form button[type="submit"]').count(), path);
        }
        await page.goto(baseURL + '/plazy/player/invitation?token=invalid');
        assert.ok(await page.locator('main').count());
        const noJS = await browser.newContext({ javaScriptEnabled: false });
        const fallback = await noJS.newPage();
        await fallback.goto(baseURL);
        assert.equal(await fallback.locator('[data-plazy-reveal]').first().evaluate(el => getComputedStyle(el).opacity), '1');
        await noJS.close();
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.goto(baseURL);
        assert.equal(await page.locator('[data-plazy-reveal]').first().evaluate(el => getComputedStyle(el).opacity), '1');
        assert.deepEqual(errors, []);
        console.log('PASS: responsive layouts, ten sections, mobile menu, links, form entry points, invalid invitation, no-JS and reduced-motion fallbacks.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
