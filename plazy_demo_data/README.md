# Plazy Demo Data

Installing `plazy_demo_data` creates an isolated, realistic data set in the current Odoo company. It depends on `plazy` and contains no changes to that module.

## Demo accounts

All created portal accounts use the password `plazy-demo-2026`.

- Team manager: `aurora.manager@demo.plazy.test`
- Player: `aurora.1@demo.plazy.test`
- Available player (discovery enabled): `diya.fernandes@demo.plazy.test`

## Included workflows

- Approved, waiting-for-approval, rejected, inviting, and onboarding teams.
- Six-player eligible five-a-side rosters, plus an incomplete inviting roster.
- Sent, expired, rejected, and joined invitations. The live sent invitation URL is `/plazy/player/invitation?token=plazy-demo-pending-invitation-token`.
- Pending/expired player and team OTP examples, plus a verified password-reset OTP. Successful registration OTPs are deliberately not retained because the Plazy workflow deletes them on successful verification.
- Draft, open, live, completed, and cancelled tournaments.
- Pending, rejected, waitlisted, and approved tournament applications.
- Published scheduled, live, and completed fixtures, including official scores, winner, champion, and result audit entries.

The records are created in the post-install hook and receive external IDs. The hook is run on installation only; upgrades do not create a second data set. The helper is also idempotent if manually invoked in the same database.
