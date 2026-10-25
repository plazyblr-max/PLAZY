# PLAZY Competition Management: Review Plan

Status: Proposed, awaiting flow review. Date: 2026-10-13.

This document is an implementation plan, not a description of shipped competition features. No application code or database changes accompany it. Existing homepage and guided registration remain in place.

## 1. Existing Architecture and Findings

The existing `plazy` addon depends on `web`, `mail`, and `social_media`. It uses Python ORM models, custom HTTP/JSON-RPC controllers, QWeb portal layouts, and `web.assets_frontend` JS/SCSS. It does not declare a dependency on `website` or `auth_signup`; retain its actual custom layout and authentication architecture rather than assuming a standard website installation.

| Existing area | Implementation | Extension needed |
| --- | --- | --- |
| Team | `models/team.py`, `plazy.team` | Configurable eligibility, protected approvals, competition relationships |
| Player | `models/player.py`, `plazy.player` | Unique normalized identity, single current team, safe discovery |
| Membership | Existing shared `plazy_player_team_rel` many-to-many | Preserve relationship; enforce at most one current team |
| Invitation | `models/team_player_invitation.py` | Search, rejection, dashboard actions, concurrency and eligibility safeguards |
| Authentication | `controllers/main.py`, registration OTP model | Preserve registration, email verification, password reset and login return links |
| Guided onboarding | `views/plazy_onboarding_templates.xml`, onboarding JS/SCSS | Extend existing invitation wizard, not rebuild registration |
| Portals | `views/plazy_auth_templates.xml`, custom portal layout | Extend manager, player and administrator dashboards |
| Back office | `views/player_team_views.xml` | Preserve existing actions/XML IDs; add operational links and position field |
| Security | `security/plazy_security.xml`, `security/ir_access.xml` | Scoped competition roles, record rules and model-level authorization |
| Tests | `tests/test_onboarding.py`, browser smoke scripts | Retain regression suite and add competition tests |

### Important gaps identified

1. Email validation currently performs an exact lookup, not autocomplete. It checks same-team membership and duplicate pending invitations, but does not reject membership of another team.
2. Invitations already use hashed random tokens, seven-day expiration, and password setup for new users. Existing users must log in as the intended recipient. Preserve these mechanisms.
3. Invitation states are `sent`, `accepted`, `joined`, `expired`, `failed`, and `cancelled`. Rejection and dashboard acceptance are missing. Newly invited people can already have a player stub before completing onboarding; existence alone does not prove verified registration.
4. The ten-invitation limit is enforced in a controller, not consistently in the model. Acceptance/resend need the same eligibility checks and concurrent-request protection.
5. Team eligibility counts `joined` invitations, not distinct current verified players. Five-a-side minimum is hardcoded to six; seven-a-side minimum is eight. Invitation counting currently includes expired records.
6. Team/player membership is many-to-many, so multiple active teams are currently possible. Player email is indexed but not unique.
7. Internal users currently have CRUD access to team/player records. Administrative approval buttons/routes are restricted, but team approval model methods do not themselves enforce the role and eligible transition. Hiding buttons is insufficient.
8. Team/player models lack company ownership, while invitations have a company. Company boundaries need a migration and consistent enforcement.
9. Dashboard routing prioritizes player over manager when both groups are present. Add an explicit role switch without changing login behavior for single-role accounts.
10. No tournament, match, standings, bracket, venue, or result-audit models currently exist in this addon.

## 2. Proposed End-to-End Flow

Existing team registration and verification -> invite players -> players explicitly accept and complete onboarding -> eligible roster -> request approval -> administrator approves -> manager applies to tournament -> administrator approves registration -> freeze competition roster and allocate groups -> generate and review fixtures -> publish -> confirm league results -> calculate standings -> review qualifiers -> generate and publish knockout bracket -> confirm knockout results -> final and champion.

Rejected, expired, withdrawn, postponed and cancelled branches remain visible with clear explanations; no action silently advances another workflow.

## 3. Models and Relationships

Implement separate files inside the existing addon. Use actual Odoo 20 APIs already present locally, including `ir.access` and `models.Constraint`. Keep existing model names and external IDs.

| Model | Main fields and relationships |
| --- | --- |
| `plazy.team` (extend) | Company, existing players/invitations, verified roster count, eligibility reasons, configured limits, registration/match links; retain existing approval data |
| `plazy.player` (extend) | Normalized email, explicit onboarding completion, optional discovery consent, company, existing current-team relation |
| `plazy.team.player.invitation` (extend) | Rejected state/date/reason, normalized email, delivery status separate from consent, action audit and recipient identity |
| `res.company` / `res.config.settings` (extend) | Five-a-side minimum/maximum roster, scheduling defaults; seven-a-side minimum eight and capacity ten remain fixed |
| `plazy.tournament` | Name/logo/description/rules, company, football and tournament formats, city/location, registration window, start/end, min/max teams, groups, qualifiers per group, single/double round robin, duration/rest, points and ordered tie-breakers, lifecycle/publication state, champion |
| `plazy.tournament.registration` | Tournament + existing team, manager, state, submitted/reviewed dates, reviewer/reason, group assignment and seed; unique tournament/team |
| `plazy.tournament.roster` | Registration + existing player, snapshot name/position and eligibility at roster lock; unique registration/player; participation history, not a duplicate player account |
| `plazy.tournament.group` | Tournament, name/order and registration members; no redundant group-team model because registration already owns group assignment |
| `plazy.tournament.stage` | Tournament, league/knockout/third-place type, round/order, draft/published state and qualification configuration |
| `plazy.tournament.venue` | Venue or ground name, location, timezone, company, active flag; each independently bookable ground is a resource |
| `plazy.tournament.venue.slot` | Ground, available UTC start/end, optional tournament reservation; explicit date availability and blackouts |
| `plazy.tournament.match` | Tournament/stage/group/round, number, home/away registrations, kickoff/end, ground, referee, duration, state, publication, all scores, winner, notes/completion, dependency slots and change reason |
| `plazy.match.result.audit` | Match, old/new result snapshot, action/reason, actor/time, revision; append-only for application users |
| `plazy.competition.event` | Append-only approval, seeding, publication, schedule, roster and manual-override events; old/new values and actor/reason |

Tournament rules are versioned fields/configuration on the tournament, not a separate rules entity until reusable rule sets are actually needed. Standings are derived from official results, not editable cumulative counters. A read-only standings projection can be added if query volume requires it.

### Membership and history

- Keep `team_ids`/`player_ids` as the source of truth for current membership, constrained to one team per player. Do not introduce a competing `active_team_id` source of truth.
- Every membership mutation, including back-office writes on either side, goes through guarded validation. Serialize relevant player/team updates and use a database uniqueness safeguard on the current membership relation after cleaning legacy conflicts.
- Tournament roster snapshots preserve historical participation when current membership later changes. They do not prove individual match appearances. Actual appearance statistics require a later lineup/substitution model.
- Detect existing multiple-team memberships and duplicate normalized emails before migration. Report for administrator resolution; never silently remove a team or merge accounts.

## 4. Invitations and Approval Rules

### Search and invitation journey

1. Extend the existing invitation wizard with email first, debounced lookup, loading/empty/error states and keyboard-accessible results. Abort stale requests so old results cannot replace a newer email.
2. Proposed privacy default: exact complete-email lookup for registered players. Prefix suggestions only for players who explicitly opt into discovery. Apply minimum query length, bounded results, rate limits, manager authentication and company scope.
3. Return only display name, position and availability, plus the email the manager supplied or consented discovery email. Never return phone, age, address, credentials or token hashes. Do not return a browsable player directory.
4. Selecting an existing player fills safe fields; do not expose or require re-entry of their stored mobile. Server resolves identity again on submission and does not trust client-provided profile details.
5. No match shows "Invite New Player" and uses existing required-information steps. Unverified player stubs are not advertised as registered profiles.
6. Reject other-team membership with the requested message. Reject same-team membership, duplicate pending invitation, full capacity or unavailable player with specific actionable errors.
7. Preserve email-token onboarding. Existing registered players additionally see pending invitations in their dashboard and may accept/reject using authenticated POST actions.
8. Acceptance atomically checks identity, token/state, expiry, capacity and current membership, then connects the player and completes the invitation. Concurrent invitations from different teams cannot both succeed. Remaining incompatible invitations are cancelled with an audit reason.
9. Expiry checks run both at action time and through a scheduled job. Resend rotates tokens, preserves history, respects capacity/rate limits, and never revives an accepted/rejected invitation accidentally.
10. Send mail through the queue after successful workflow writes; delivery failures are retryable and do not masquerade as consent or duplicate the invitation.

Retain legacy stored states during rollout. UI maps `sent` to Pending and `joined` to Accepted; transitional `accepted` must not count as fully onboarded. Add Rejected. Separate delivery failure from invitation lifecycle through a compatible migration so existing links continue working.

### Roster and approval

- Seven-a-side: at least eight distinct verified current players; maximum ten occupied invitation/roster places. Proposed interpretation: joined players plus unexpired pending invitations consume places; cancelled, rejected and expired invitations release places. Resend rechecks capacity. This interpretation needs review because current code counts expired invitations.
- Five-a-side: administrator-configurable minimum and maximum with `5 <= minimum <= maximum`; proposed initial values six/ten preserve current behavior.
- Count actual verified current membership, not historical invitation rows. Receiving an invitation or creating a player stub is not completion.
- Preserve stored team states: `onboarding` = Draft, `inviting` = Awaiting Players, `eligible` = Ready to Request, `waiting` = Pending Approval, then Approved/Rejected. Keep Ready to Request as a useful intermediate state rather than destructively rewriting history.
- Request and approval both validate eligibility on the server. Rejected teams retain their reason until explicit correction/resubmission; automatic roster refresh must not erase a rejection.
- Approval status and current eligibility are distinct. A roster change may make an approved team ineligible; it cannot use an old approval to bypass registration checks.
- Proposed roster policy: re-review approval after material roster changes; lock competition rosters at fixture preparation. Later changes require administrator review and an audited amendment, never an automatic rewrite of past participation.

## 5. Tournament Registration and Lifecycle

- Validate date ordering, football format, positive duration, min/max team counts, group capacity and possible qualifier count. Store registration boundaries as datetimes and display their timezone.
- A manager may apply only for their own approved, currently eligible team, matching football format, inside the registration window. Check again when the administrator approves and before fixtures are generated.
- Unique tournament/team constraint prevents duplicate applications, including concurrent submissions. A rejected/withdrawn team may resubmit the same record before deadline if allowed; preserve events rather than creating a second row.
- States: Pending, Approved, Rejected, Waitlisted, Withdrawn. Capacity counts approved registrations and is enforced under a tournament lock. Full competitions offer waitlist; promotion is explicit and eligibility is rechecked.
- Withdrawal before scheduling releases capacity. After publication it requires an administrator decision about remaining fixtures/results; do not delete historical matches or recalculate as if the team never existed.
- Lifecycle: Draft -> Registration Open -> Registration Closed -> Scheduled -> In Progress -> Completed. Each transition has prerequisites. Scheduled requires a valid published schedule; completion requires all required matches resolved and a champion/winner determined.
- Cancellation and postponement are separate audited actions with reasons. Postponement records the previous lifecycle state for resumption and does not silently move fixture dates. Cancellation is terminal absent an explicit privileged recovery procedure.
- Lock scoring, tie-break and qualification rules at fixture publication. Exceptional amendments require a preview of affected results and explicit audited confirmation.

## 6. League, Scheduling and Standings

### League preparation

- Allocate approved registrations into balanced groups using deterministic seeds; allow administrator adjustments before publication. Every team belongs to exactly one group in that league stage.
- Generate round-robin pairings with the circle algorithm and byes for odd group sizes. Four teams yield six matches for single round robin and twelve for double.
- Give every fixture a canonical generation key: tournament/stage/group/round/leg/pair. Repeating generation returns existing fixtures without duplicates. Regeneration is allowed only for explicitly replaceable unpublished/unplayed drafts.
- Generation and scheduling are separate: a valid pairing may remain unscheduled with a clear conflict, rather than inventing an available venue/time.

### Scheduling

- Administrator selects actual available dates, kickoff slots, grounds, maximum daily matches, duration, turnaround buffer and team rest period. Preview allocations and unscheduled conflicts before publication.
- Serialize resource allocation; validate overlaps and team rest against all relevant tournaments sharing teams/grounds, not only the current tournament. Manual changes use the same checks.
- Use half-open time intervals; allow exact adjacency only when required buffer/rest is satisfied. Include reserved extra-time allowance for knockout fixtures.
- Convert venue-local input to UTC using timezone-aware conversion; ORM datetimes remain UTC as Odoo expects. Reject ambiguous/nonexistent local times instead of silently shifting them.
- Match states: Scheduled, Live, Completed, Postponed, Cancelled, Abandoned, Walkover. Publication is independent of match state.
- Published schedule changes require a reason, create an event, and queue deduplicated notifications to affected managers/players. Mail failure must not roll back the schedule or create duplicate matches.
- Manual creation validates different teams, valid stage/group membership, format, time/resource constraints and allowed pairings. No manager can schedule or alter official results.

### Results and table calculation

- Distinguish an unentered score from 0-0. Validate nonnegative integer regulation, extra-time and penalty scores. Store completion time, duration and notes.
- For knockout games, regulation plus extra time determines the score; penalties decide the winner but do not count as goals for/against. Unresolved draws cannot be finalized.
- In one transaction: lock match and relevant dependencies, validate actor/state/revision, finalize result, append audit, update the derived standings view and advance a knockout winner if applicable. Repeated confirmation is idempotent.
- League table includes P/W/D/L/GF/GA/GD/Pts from finalized league results only. Never increment counters on every save. Default points 3/1/0 are configurable before rules lock.
- Walkover winner and awarded score follow an explicit tournament policy (proposed default 3-0, pending review). Cancelled/postponed/abandoned games do not count unless an administrator formally resolves them.
- Ordered tie-breakers: points, goal difference, goals scored, optional head-to-head mini-table among tied teams. Specify whether head-to-head is reapplied after a subgroup separates; use one tested rule consistently. Require all relevant head-to-head games to be final before using it for qualification.
- If configured tie-breakers cannot resolve a qualification/champion tie, show "Decision required" and require an audited sporting decision. Never silently qualify by record ID or alphabetical name.

## 7. Knockout and Corrections

- League-only tournaments end with finalized standings. Knockout-only tournaments seed approved teams. Hybrid tournaments require finalized league matches and resolved qualification ties before deriving qualifiers.
- Generate rounds up to Round of 32, Round of 16, Quarterfinal, Semifinal and Final, with optional third-place match from semifinal losers.
- Proposed standard hybrid seeding: paired groups A1-B2/B1-A2, C1-D2/D1-C2, arranged into the reviewed bracket. Different group/qualifier configurations use an explicit seed-slot editor with validation and a preview.
- For non-power-of-two fields, show explicit seeded byes in a next-power-of-two bracket. Byes advance a team without inventing a played match, goals or points. Review this policy before implementation.
- Model winner/loser source dependencies as a directed acyclic graph. Validate no duplicate participant, impossible source, cross-tournament link or cycle. Publish only after review.
- Result finalization fills downstream participant slots. It does not overwrite a started/finalized or conflicting match. Resolve the final before assigning champion; third place must also finish if required for tournament completion.
- Corrections require a reason and record immutable before/after snapshots, actor, timestamp and version. League standings recompute from results, so correction cannot double-count.
- Before correction, calculate affected qualifiers, bracket participants and downstream results. If publication/progression would change, block ordinary correction and show a dependency impact review.
- An explicit administrator recovery workflow may unpublish/reset only unplayed dependent fixtures, with audit and notifications. Started or completed downstream matches require separate formal adjudication; no silent cascade or score deletion.
- Manual winner/seed overrides are distinct privileged actions with reason and the same dependency checks, not editable winner fields in ordinary forms.

## 8. Pages and Controllers

Keep existing URLs and layout IDs. Add small controller modules (`competition.py`, `competition_admin.py`) and a shared guarded service layer in model methods; do not grow `main.py` into the competition engine.

| Route family | Access and behavior |
| --- | --- |
| Existing `/plazy/team/player-email-validation` | Keep response compatibility; safe exact lookup |
| `/plazy/team/players/search` | Authenticated manager, bounded consent-aware autocomplete |
| Existing invitation/send/resend/cancel URLs | Preserve, route through strengthened model actions |
| `/plazy/player/invitations/<id>/accept` and `/reject` | POST, authenticated intended recipient, no token required for own dashboard record |
| `/plazy/tournaments` | Public published competitions, filters/pagination |
| `/plazy/tournaments/<id>` | Public published overview, teams, fixtures, results, standings, bracket and rules tabs |
| `/plazy/tournaments/<id>/register` | Manager review GET and CSRF-protected confirmation POST |
| `/plazy/team/registrations/<id>/withdraw` | Owner POST, lifecycle safeguards |
| `/plazy/matches/<id>` | Published match centre; no unpublished participant/result leakage |
| Existing team/player dashboards | Add competitions, fixtures/results, pending invitations and role switch |
| `/plazy/admin/tournaments/...` | Competition administrator: create/edit, registrations, groups, scheduling, qualification/publication |
| `/plazy/admin/matches/...` | Competition administrator: schedule, result confirmation/correction and recovery |
| Existing `/plazy/admin/dashboard` | Real counts, pending work and links to new management screens |

Use POST for all mutations with CSRF validation, field allowlists and ownership checks. Read-only JSON-RPC search still requires session authorization and anti-enumeration controls. Never accept actor/company/manager ownership from browser data. Return structured validation errors without stack traces.

## 9. Permissions and Privacy

- Introduce a dedicated competition administrator role; retain system-administrator access. Ordinary internal users must not acquire competition mutation rights just because they are employees.
- Public visitors receive only explicitly published, sanitized competition data. No general public read ACL on players, invitations, rosters or private registration records.
- Managers may read their own team, roster and application/invitation status, and request allowed actions. They cannot approve teams/registrations, change official scores, configure points or edit standings.
- Players may read their own profile, intended invitations and permitted participation data, and accept/reject only their own invitations.
- Add company-scoped record rules and read ACLs for intended portal data. Avoid overly broad portal model CRUD; use validated workflow actions for mutations. Group-rule unions and direct RPC access must be tested explicitly.
- Any necessary `sudo()` follows authorization with the original actor and a scoped record lookup. Never trust a context flag from the caller to bypass checks. Public token flows use private, narrowly scoped token-validated helpers.
- Guard sensitive field writes and model actions as well as controller routes; include imports, backend edits and direct RPC in the threat model. Audit models prohibit ordinary write/delete after creation.
- Avoid logging token URLs or private email search payloads. Keep email, phone and roster contact details out of public tournament APIs and templates.

## 10. UI Integration

- Reuse current PLAZY colors, typography, icons, portal header/footer, guided steps and reduced-motion behavior. No homepage redesign, new SPA framework or heavyweight animation dependency.
- Tournament listing uses compact individual cards; details use accessible tabs and full-width tables/lists. No decorative nested cards or public Odoo-style back-office forms.
- Match centre includes team logos with initials fallback, names, score/status, timezone-labelled kickoff, venue and stage. Distinguish live data from finalized results.
- Bracket offers clickable matches on desktop, horizontally scrollable rounds with clear labels and a linear accessible list on mobile. Never hide progression information behind hover only.
- Manager dashboard: verified roster progress, approval reasons, pending invites, available competitions, registrations, next fixtures, results, group position and knockout progress.
- Player dashboard: pending invitations with explicit consent, current team, tournament roster participation and team fixture history. Do not call team matches individual appearances.
- Admin portal: compact overview, approval queues, tournament editor, registration table, group/seed editor, schedule preview/calendar, score entry/review and correction impact screen. Existing back-office views remain available as operational support.
- Include empty/loading/error states, preserved drafts for non-sensitive admin edits, focus management, keyboard operation, 44px touch targets, reduced motion and responsive checks at 320/390/768/1440px.

## 11. Files Expected to Change After Review

Existing extensions: `models/team.py`, `models/player.py`, `models/team_player_invitation.py`, `models/res_company.py`, model/controller imports, `controllers/main.py`, security XML, manifest, email templates, `views/player_team_views.xml`, guided invitation templates/JS, dashboard templates.

New model files: tournament, registration/roster, group/stage, venue/slot, match, result audit and competition event. New controller files: competition and competition administrator. New views: competition backend, competition settings, public competition, administrator competition and dashboard extensions. New scoped frontend JS/SCSS plus mail/cron data. Add versioned migration/preflight logic and tests.

Do not modify Odoo core `addons/auth_signup/views/auth_signup_login_templates.xml`. Preserve original registration/login routes, field names, XML IDs, token links, OTP flow and user relationships.

## 12. Delivery Order and Acceptance Gates

1. **Player lookup and invitations:** private autocomplete, existing/new branching, dashboard accept/reject, expiry, anti-duplicate and concurrency guarantees. Existing onboarding tests remain green.
2. **Eligibility and approval:** distinct verified roster, seven-a-side eight/ten boundary, configurable five-a-side policy, migration report, model permissions and rejection/resubmission behavior.
3. **Tournament creation/registration:** admin model/views and portal entry points, date/format checks, unique applications, capacity/waitlist locks and lifecycle guards.
4. **Groups and league fixtures:** balanced assignment, deterministic single/double round robin, odd-team byes, idempotent regeneration and draft review.
5. **Venue scheduling:** availability slots, timezone conversion, team/ground conflict checks, rest buffers, manual overrides only where valid, publication/change notifications.
6. **Results and standings:** validated official results, point configuration, derived tables, correction audits and tie-break tests.
7. **Knockout:** qualification, seeded draft bracket, explicit byes, winner/loser dependencies, penalties, champion and protected corrections.
8. **Complete admin portal:** integrate all operations, real counts, calendar and correction impact review. Minimal operational screens ship with each earlier backend phase so they are testable.
9. **Manager/player dashboards and public match centre:** integrate real data and approved public visibility; preserve existing onboarding design.
10. **Regression and rollout:** automated/browser/security/concurrency checks, migration rehearsal, performance review, staged activation and documentation.

Each phase should be reviewable and functional before enabling links to unfinished capabilities. Do not expose placeholder actions as implemented features.

## 13. Validation and Rollout

- ORM tests: state transitions, direct method/field access, one-current-team enforcement, invitation expiry/replay/wrong-user/reject/resend, duplicate identity handling and roster boundaries.
- Real concurrent transaction tests: duplicate invite/application, two-team acceptance race, registration capacity, venue reservation and double result confirmation. Ordinary sequential tests alone do not establish race safety.
- League tests: four teams six/twelve fixtures, odd groups, generation repeats, 0-0 draws, points/ties/head-to-head, walkovers and corrections without double counting.
- Scheduling tests: cross-tournament conflicts, rest/day limits, unavailable venues, adjacency, timezone/DST edges and published-change notifications.
- Knockout tests: 2/4/8/16/32 qualifiers, non-power-of-two byes, unresolved ties/draws, extra time/penalties, third place, winner progression and correction with published/started dependents.
- HTTP/security tests: CSRF, forged team/player/tournament IDs, direct RPC attempts, cross-company access, unpublished data, email enumeration and audit immutability.
- Browser tests: existing login/OTP/team/player flows, invitation branching, all dashboard roles, tabs/bracket/table accessibility, mobile layouts and errors/loading states. Verify no real emails are sent from automated tests.
- Performance: bounded search, pagination, batch counts/standings, indexes on normalized email/status/dates/foreign keys, no per-row ORM searches in templates; profile representative 32-team competitions.
- Migration: backup first; inventory duplicate emails, multiple memberships, incomplete invite stubs, inconsistent approvals and missing company ownership. Resolve conflicts explicitly, preserve IDs/links, then enable uniqueness/permission changes. Reconcile old invitation states/counts without bulk invalidating existing tokens.
- Rehearse addon upgrade on a disposable database with the local Odoo 20 executable. Roll back through tested backup restoration/code version alignment, not by uninstalling the addon and deleting competition history.

No tests were executed for this planning-only change. Existing tests were inspected; their presence is not proof that proposed functionality is implemented or tested.

## 14. Review Decisions Before Implementation

Recommended defaults requiring confirmation:

1. **Discovery privacy:** exact-email lookup by default, prefix autocomplete only for opted-in discoverable players. Unrestricted prefix email search would expose the registered-player directory.
2. **Capacity:** seven-a-side uses ten occupied places (joined + pending), with expiry/rejection/cancellation releasing a place; five-a-side starts at minimum six/maximum ten, configurable by administrators. Clarify if ten means a lifetime invitation limit instead.
3. **Roster changes:** re-review materially changed approved teams; freeze competition rosters at fixture preparation and require audited amendments afterward. No self-service transfers while a competition roster is locked.
4. **Competition defaults:** seed explicit byes for non-power-of-two knockout fields; use administrator-reviewed unresolved sporting ties; proposed walkover score 3-0. Confirm desired sporting rules before enabling these outcomes.
5. **Admin scope:** dedicated competition administrator role plus existing system administrators, with company-scoped data. Existing employee-wide team/player edit rights will be narrowed deliberately and must be checked against operational users during migration.

Once this flow is approved, implementation starts with invitations and eligibility, not with rebuilding registration or the homepage.
