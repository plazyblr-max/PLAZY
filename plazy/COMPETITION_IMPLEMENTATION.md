# Competition Implementation

Implemented in the existing `plazy` addon, version `20.0.4.1.0`. Updated after the continued implementation and verification on 13 October 2026. This is a working competition release, not completion of every advanced option in COMPETITION_PLAN.md.

## Available Now

- Existing guided registration, OTP verification, login, password setup and invitation links retained.
- Email-first invitation wizard with debounced exact-email lookup, safe name/position preview, existing-player autofill and no disclosure of stored mobile numbers. Existing players skip mobile collection. Prefix search returns only available players who explicitly enable discovery in their dashboard; discovery defaults off. Searches are company-scoped, throttled, limited to five results and escape SQL wildcard characters.
- Cross-team membership checks, duplicate pending invitation checks, roster capacity checks on send/resend/accept, player dashboard accept/reject, scheduled invitation expiry.
- Seven-a-side minimum eight and maximum ten occupied roster/invitation places. Five-a-side defaults six/ten, configurable on the company form.
- Eligibility based on current players with user accounts. Company-scoped player/team management, restricted to system or competition administrators; portal changes use owned, guarded controller routes. The new Competition Administrator group does not grant system administration.
- Tournament creation, registration windows, format/capacity validation, applications, administrator approval/rejection/waitlisting, manager withdrawal before fixtures and competition roster locking.
- Tournament lifecycle with opening/closing registration, publication, postponement/resumption, cancellation and completion.
- Balanced automatic group allocation or administrator-created groups and entrant assignments; deterministic single/double round-robin fixtures with duplicate generation protection. Manual groups must be complete, balanced and contain at least two approved teams. Assignments lock once fixtures exist.
- Grounds and availability windows; configurable kickoff grid (default 15 minutes), tournament-local daily limits, ground/referee conflicts, team rest checks and knockout dependency timing. Knockout slots reserve configurable extra-time allowance (default 20 minutes). Manual scheduling through Odoo forms/calendar uses the same checks.
- Official score confirmation, extra-time/penalty results, explicit walkovers, standings, protected corrections, immutable audit entries and knockout winner progression to a champion.
- League/hybrid/knockout competitions. Knockout fields support 2 through 32 teams using automatic byes, optional third-place matches, pre-fixture seeding and winner/loser progression. Byes advance teams without fictitious scores or matches played.
- Configurable overall or head-to-head standings. Head-to-head uses a single mini-table for teams tied on overall points after all their meetings are official, followed by overall goal difference/goals scored. Recursive subgroup reapplication is not implemented. Unresolved qualification/champion ties require a reasoned, audited administrator decision; correcting a group result invalidates its tie decision.
- Immutable competition event history for configuration, application changes, bracket generation and tie decisions, alongside result/schedule audits. Reviewed knockout corrections can unpublish not-started dependent fixtures, notify managers and reopen the affected result. Started downstream matches remain protected.
- Administrator website workspace: draft tournament creation, application review, fixture generation/scheduling/publication, score entry and correction. Detailed settings, grounds and calendar remain available in native Odoo screens.
- Public tournament listing with name/format/status filters and pagination, seven detail tabs, fixtures/results, group tables, bracket links and match scoreboards. Team/player dashboards link to their competition workspace with paginated match history.
- Published schedule changes require reasons, create audit entries and queue manager notifications.

## Main Files

New backend: `models/competition.py`, `models/competition_advanced.py`, `controllers/competition.py`, `controllers/player_discovery.py`, `controllers/lookup.py`, `security/competition_access.xml`, `security/competition_rules.xml`, `security/competition_manager_access.xml`, `data/competition_cron.xml`.

New UI: `views/competition_views.xml`, `views/competition_templates.xml`, `views/competition_admin_templates.xml`, `views/competition_advanced_views.xml`, `views/competition_advanced_templates.xml`, `static/src/js/plazy_competition.js`, `static/src/scss/plazy_competition.scss`.

Existing extensions: team/player/invitation/company models, main controller, onboarding JS, access configuration, model/controller imports and module manifest. No Odoo core files changed.

Odoo 20 in this checkout uses domain-bearing `ir.access` records, not `ir.rule` or legacy `ir.model.access`. Company restrictions are attached to the actual access records.

## Running and Upgrading

An isolated review database, `plazy_competition_review`, was initialized and upgraded for testing. Its deliberately labelled demo competition is not real community data. Preview server: `http://localhost:8094/plazy/tournaments`.

The original `plzy_testing` database has not been upgraded or seeded. A read-only preflight found zero duplicate normalized player emails and zero multi-team player memberships. Its existing running Odoo processes were left untouched.

To activate this version there, first back up the database and filestore and stop its existing Odoo processes. From `/home/hp/plazy_20`, run:

```bash
./.venv/bin/python odoo-bin -c odoo.conf -d plzy_testing -u plazy --stop-after-init --no-http
```

Then restart the normal Odoo service. Python model changes require a restart, not only a browser refresh. The upgrade adds fields/tables and backfills company ownership using the upgrade environment's company; review ownership explicitly for a multi-company deployment. No existing account or relationship is intentionally removed.

Administrator journey: Admin Dashboard -> Competition management -> Create tournament -> configure scheduling grounds/availability -> open registration -> review applications -> close registration -> generate league/knockout -> auto schedule -> review -> publish -> manage results.

Optional manual allocation: create the configured number of groups in Groups and Tie Decisions, assign each approved application to a group in its application form, then generate league fixtures. Seeds and detailed scheduling policies are edited in the native competition forms before fixture generation. Tie decisions require the complete tied set of team IDs and a reason. Assign the Competition Administrator group to trusted competition staff instead of granting system administrator rights.

## Verification

- Fresh Odoo 20 installation and repeated module upgrades on the isolated database.
- Latest full Odoo test run: **22 tests, zero failures/errors** (`/tmp/plazy-final-full.log`).
- Original five onboarding HTTP tests retained, including actual team/player registration, OTP, token onboarding and login return routing. Added a sixth HTTP test for discovery consent, data minimization, wildcard escaping, opt-out and team-member exclusion.
- Sixteen ORM tests cover single/double round robin, manual groups, idempotence, standings/corrections, duplicate applications, local-day/referee/venue scheduling, membership, seven-a-side capacity/expiry, permissions, walkovers, byes/third-place progression, head-to-head ranking, audited ties and knockout correction protection.
- Public Playwright checks cover all seven tabs and match centre at 1440/390/320 pixels, document overflow, real stylesheet loading and rendered bracket matches.
- Existing onboarding browser smoke suite checks validation, keyboard navigation, editing, draft recovery, responsiveness, reduced motion and no-JS fallback.
- Separate administrator browser smoke suite passed for dashboard, tournament management, result correction and creation screens at desktop/mobile sizes. Browser screenshots were visually inspected.

Run ORM/HTTP tests on a disposable database:

```bash
./.venv/bin/python odoo-bin -c odoo.conf -d plazy_competition_review -u plazy --test-tags /plazy --stop-after-init --http-port 8095
```

Browser scripts are in `tests/competition_smoke.cjs`, `tests/competition_admin_smoke.cjs` and the existing `tests/onboarding_smoke.cjs`. They accept `PLAZY_URL`, `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH`; administrator checks also require `PLAZY_ADMIN_PASSWORD`.

## Remaining Work Before Full Phase-2 Sign-Off

- Changes affecting already-started downstream matches need a dedicated adjudication workflow. Ordinary result corrections deliberately stop at this boundary. Event history does not yet cover every administrative edit, such as unpublished scheduling changes or standalone group renames.
- Head-to-head policy is one-pass, not recursive. Agree tournament rules before opening registration; do not assume compatibility with every competition's tie-break regulations.
- Session throttling is not a replacement for infrastructure-level anti-abuse controls. Exact-email invitation checks intentionally work without directory opt-in; prefix discovery requires consent.
- Review the intentional narrowing of prior employee-wide team/player CRUD access and assign the new competition role before deployment.
- Roster snapshots retain player IDs, not immutable historical copies of profile text. Formal transfers, roster amendments and match-specific player appearances need additional workflows.
- Ground scheduling has no optimization/backtracking or recurring availability editor. Referees are matched by normalized name, not a separate identity model. Configure sufficient knockout extra-time allowance for the rules in use.
- True parallel-transaction race/load tests, mail-delivery integration tests, accessibility tooling and production-scale performance profiling remain. The scheduler uses conservative shared transaction locks and is intended for modest local competitions.
- The administrator competition overview still caps at 100 tournaments; public listings and team/player match histories are paginated. Large brackets use horizontal scrolling rather than a draggable graphical tree.
- The original database upgrade has not been executed. The review preview is separate and must not be mistaken for deployment to the existing service.

Do not represent these remaining capabilities as shipped or use this release for a large live competition without completing the deployment and operational review.
