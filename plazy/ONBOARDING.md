# Guided team and player onboarding

The registration UI is owned by the PLAZY module. The core
addons/auth_signup/views/auth_signup_login_templates.xml is not part of
these registration routes and has not been changed.

## Journeys

- Team: welcome, manager, mobile, locality/PIN, email/passwords, team name,
  logo, 5-a-side or 7-a-side, review. Account creation follows email verification.
- Player: welcome, name, preferred position, email, mobile, age,
  locality/PIN, passwords, review. Account creation follows email verification.
- Manager invitation: welcome, player name, position, email, mobile, review.
- Invitee: welcome and invitation review, then login or password setup
  according to the existing account state.
- Confirmed team registration presents a welcome and an invitation entry
  point. Invited-player completion shows confirmation after the server
  has linked the player and team.

## Implementation

New files:

- views/plazy_onboarding_templates.xml: reusable QWeb fields, progress,
  controls, registration journeys, invitation journeys and confirmed welcome.
- static/src/js/plazy_onboarding.js: progressive wizard, validation,
  previews, editable review, asynchronous submission and draft recovery.
- static/src/scss/plazy_onboarding.scss: scoped responsive visual system,
  selection, progress, transition and reduced-motion styles.
- tests/test_onboarding.py and tests/__init__.py: backend HTTP regression tests.
- tests/onboarding_smoke.cjs: browser checks.

Updated files:

- __manifest__.py: registers templates and assets.
- models/player.py: adds optional preferred position.
- controllers/main.py: saves that position, supports the single-name player
  field, flags confirmed completions, and validates/normalizes logos into
  JSON-safe session data before OTP delivery.
- static/src/js/plazy_auth.js: preserves the OTP submitter action while
  showing its loading state.

Existing registration routes, CSRF tokens, email verification, account
creation, invitation token checks, player/team relationships and team
approval rules remain in use. The login form preserves the existing
invitation return URL through QWeb inheritance.

Step changes stay on the page. Submission uses the existing POST endpoints;
validation/network errors preserve current input and uploads. Navigation
occurs when moving to verification, login or account security. Success is
displayed only after a server-confirmed response.

Non-sensitive registration fields recover through sessionStorage for up to
24 hours in the current tab. Passwords, CSRF/invitation tokens and image
files are excluded. A restored draft asks for passwords and the logo again.
The page warns before leaving with unfinished edits. Invitation forms keep
data in memory only. Without JavaScript, all steps remain visible and the
ordinary POST form still works.

Localities use a native searchable datalist with free-text entry for places
outside the suggestions. Logos accept PNG/JPG/WebP up to 5 MB; the server
validates the image and uses Odoo's image processing before verification.
AI logo generation is visibly disabled and marked coming soon.

## Verification

Five backend HTTP tests pass with SMTP delivery mocked:

- Team registration including a real PNG upload, OTP verification, manager
  invitation, invited-player password setup, relationship creation,
  approval eligibility and invitation replay rejection.
- Player registration, position persistence and no-JavaScript name fallback.
- Password mismatch and OTP resend.
- Preservation of an invitation's login return URL.
- Invalid image rejection before verification.

Browser checks pass for team/player step navigation, validation, Enter,
password visibility, name/logo previews, format/position selection, review
editing, multipart POST payload, server errors, draft recovery, no-JS and
reduced-motion behavior, and widths of 320, 390, 768 and 1440 pixels.
Desktop and mobile screenshots were inspected. Real email delivery and
physical-device/browser coverage beyond Chromium are not covered by these tests.

Run backend checks:

    ./.venv/bin/python odoo-bin -c odoo.conf -d plzy_testing -u plazy --test-enable --test-tags /plazy:TestOnboarding --stop-after-init --http-port 8093

Run browser checks with Playwright available:

    PLAZY_URL=http://localhost:8092 node PLAZY20/plazy/tests/onboarding_smoke.cjs

PLAYWRIGHT_MODULE and CHROMIUM_PATH can select existing local installations.

Restart existing Odoo workers and upgrade plazy when deploying; this change
adds a model field and frontend bundle entries. The preview on port 8092
uses the upgraded plzy_testing database.
