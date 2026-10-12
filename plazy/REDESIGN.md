# PLAZY Football homepage

## Architecture and scope

PLAZY is an Odoo 20 module depending on web, mail and social_media, without
the Website builder module. Public pages use server-rendered QWeb; existing
authentication helpers use OWL and the web.assets_frontend bundle.

The original homepage already contained nine storytelling sections. This
iteration completes the ten-section structure and adds audience coverage,
an expandable journey, feature availability, local typography, metadata,
responsive navigation and accessible motion fallbacks.

Existing routes reused:

| Purpose | Route |
| --- | --- |
| Home and editorial sections | / and homepage anchors |
| Registration choice | /plazy/join |
| Player registration | /plazy/player/join |
| Team registration | /plazy/team/join |
| Login | /web/login |
| Role-aware dashboard | /plazy/dashboard |
| Password recovery | /plazy/forgot-password |

Player/team registration, OTP, password reset, invitation acceptance and
password setup, team approval, models, access rules and controllers were
not rewritten. Shared header/footer styling applies to registration,
authentication and portal pages.

## Files

Created:

- views/plazy_home_templates.xml: QWeb inheritance for homepage, metadata,
  navigation and a document layout with one main landmark.
- static/src/scss/plazy_home.scss: public design system, extracted from the
  authentication stylesheet and expanded for the redesign.
- static/src/js/plazy_home.js: public navigation and motion.
- static/src/img/plazy-hero-bengaluru.webp and plazy-story-kerala.webp:
  optimized derivatives of the existing project images.
- tests/homepage_smoke.cjs: repeatable browser smoke checks.
- REDESIGN.md: implementation and verification notes.

Modified:

- __manifest__.py: registers the new view and frontend assets.
- static/src/scss/plazy_auth.scss: public homepage styles moved out.
- static/src/js/plazy_auth.js: public motion moved out; form behavior retained.

Reused: website_layout, portal_header, portal_footer, home, all registration
and dashboard templates, existing brand mark, football images, bundled
Oswald font and bundled Font Awesome font.

## Design and interactions

Near-black, forest green, off-white and selective lime are balanced by a
cool pale-blue next-generation section. Locally served Oswald provides
consistent condensed headings. Fixed breakpoint font sizes and flexible
grids keep layouts predictable.

Motion uses IntersectionObserver for one-time reveals and a passive,
requestAnimationFrame-throttled scroll listener for restrained parallax.
Reduced-motion users get static content. Content remains visible if
JavaScript fails. No animation library or video dependency was added.

The mobile navigation supports native disclosure semantics, Escape,
outside click, focus departure and closing after link selection. Journey
disclosures work without JavaScript. Buttons use existing real routes.

The two WebP images total about 280 KB versus roughly 4.7 MB for the PNGs.
The hero is preloaded, the story image is lazy-loaded with dimensions.

## Verification

Odoo module upgrade succeeded against local plzy_testing. SCSS compiled
with the project's Sass toolchain. Chromium/Playwright checks passed at
320, 390, 768 and 1440 pixels: ten sections, no page-width overflow,
navigation, internal link responses, registration/login/recovery forms
with CSRF fields, invalid invitation handling, reduced motion and no-JS
visibility. Desktop full-page and mobile screenshots were inspected.

Run tests with Playwright available:

    PLAZY_URL=http://localhost:8092 node PLAZY20/plazy/tests/homepage_smoke.cjs

Optional PLAYWRIGHT_MODULE and CHROMIUM_PATH environment variables select
an existing local installation and browser. No new npm dependency is
required by the production application.

## Limits and launch notes

- End-to-end email delivery, successful authenticated login, OTP completion,
  invitation acceptance and approval mutations were not exercised with
  real accounts. Their existing business logic remains unchanged.
- Browser checks are Chromium checks, not a real Android network/device
  performance audit or a complete accessibility audit.
- Game discovery, public team directories, community discovery, schedules,
  tournaments and events still need backend development. They are labelled
  as planned; no fake matches, metrics or testimonials are introduced.
- Stories are editorial illustrations. Existing project images are reused,
  not verified evidence of actual PLAZY members or city launches.
- No suitable local video, verified contact details or legal pages exist,
  so these were not invented. Social links use existing company settings;
  their account ownership has not been independently verified.
- Canonical and Open Graph URLs use Odoo's configured base URL. Configure
  the final public domain before launch.
- Restart existing Odoo workers after deploying the changed manifest,
  upgrade plazy, and let Odoo rebuild its frontend assets.
- Local preview: http://localhost:8092 using the existing plzy_testing DB.
