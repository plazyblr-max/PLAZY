from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCompetition(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.teams = cls.env['plazy.team']
        for number in range(4):
            players = cls.env['plazy.player'].create([{
                'name': 'Player %s %s' % (number, i), 'full_name': 'Player %s %s' % (number, i),
                'email': 'p%s-%s@example.invalid' % (number, i), 'mobile': '9876543210',
                'user_id': cls.env.user.id,
            } for i in range(6)])
            cls.teams |= cls.env['plazy.team'].create({
                'name': 'Team %s' % number, 'email': 'team%s@example.invalid' % number,
                'mobile': '9876543210', 'locality': 'Bengaluru', 'pincode': '560038',
                'team_type': 'five_a_side', 'registration_status': 'approved',
                'player_ids': [(6, 0, players.ids)],
            })

    def tournament(self, format='league', groups=1):
        now = fields.Datetime.now()
        t = self.env['plazy.tournament'].create({
            'name': 'Test League', 'location': 'Bengaluru', 'football_format': 'five_a_side',
            'format': format, 'group_count': groups, 'min_teams': 4, 'max_teams': len(self.teams),
            'registration_start': now - timedelta(days=1), 'registration_end': now + timedelta(days=1),
            'start_date': now + timedelta(days=2), 'end_date': now + timedelta(days=5),
        })
        t.action_open()
        for team in self.teams:
            r = self.env['plazy.tournament.registration'].create({'tournament_id': t.id, 'team_id': team.id})
            r.action_approve()
        t.action_close()
        return t

    def schedule(self, t):
        ground = self.env['plazy.tournament.venue'].create({'name': 'Test Ground', 'location': 'Bengaluru', 'slot_ids': [(0, 0, {'start': t.start_date, 'end': t.end_date})]})
        t.venue_ids = ground
        t.action_schedule()
        t.action_publish()

    def test_round_robin_idempotent_and_standings(self):
        t = self.tournament()
        t.action_generate_league()
        self.assertEqual(len(t.match_ids), 6)
        t.action_generate_league()
        self.assertEqual(len(t.match_ids), 6)
        self.schedule(t)
        m = t.match_ids[0]
        m.write({'result_entered': True, 'home_score': 3, 'away_score': 1})
        m.action_confirm()
        m.action_confirm()
        row = next(r for r in t.standings() if r['team'] == m.home_id)
        self.assertEqual((row['p'], row['pts'], row['gd']), (1, 3, 2))
        with self.assertRaises(ValidationError):
            m.write({'home_score': 8})
        m.correction_reason = 'Correct score sheet'
        m.action_reopen()
        m.write({'home_score': 0, 'away_score': 0})
        m.action_confirm()
        row = next(r for r in t.standings() if r['team'] == m.home_id)
        self.assertEqual((row['p'], row['pts'], row['gd']), (1, 1, 0))
        self.assertEqual(len(m.audit_ids), 3)
        with self.assertRaises(AccessError):
            m.audit_ids.write({'description': 'tamper'})

    def test_double_round(self):
        t = self.tournament()
        t.double_round = True
        t.action_generate_league()
        self.assertEqual(len(t.match_ids), 12)

    def test_manual_groups_and_match_membership(self):
        t = self.tournament(groups=2)
        groups = self.env['plazy.tournament.group'].create([
            {'name': name, 'tournament_id': t.id} for name in ('North', 'South')
        ])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            t.action_generate_league()
        for index, entry in enumerate(t.registration_ids):
            entry.group_id = groups[index % 2]
        t.action_generate_league()
        self.assertEqual(len(t.match_ids), 2)
        match = t.match_ids[0]
        other_team = (self.teams - match.group_id.registration_ids.team_id)[0]
        with self.assertRaises(ValidationError), self.cr.savepoint():
            match.home_id = other_team
        with self.assertRaises(ValidationError), self.cr.savepoint():
            t.registration_ids[0].group_id = groups[1]

    def test_local_day_and_referee_conflict(self):
        t = self.tournament()
        self.assertEqual(str(t._local_day(fields.Datetime.to_datetime('2026-10-13 20:00:00'))), '2026-10-14')
        t.action_generate_league()
        grounds = self.env['plazy.tournament.venue'].create([
            {'name': name, 'location': 'Bengaluru', 'slot_ids': [(0, 0, {'start': t.start_date, 'end': t.end_date})]}
            for name in ('East', 'West')
        ])
        first = t.match_ids[0]
        second = t.match_ids.filtered(lambda m: not (m.home_id | m.away_id) & (first.home_id | first.away_id))[0]
        first.write({'kickoff': t.start_date, 'venue_id': grounds[0].id, 'referee': 'Referee One'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            second.write({'kickoff': t.start_date, 'venue_id': grounds[1].id, 'referee': ' referee one '})
        second.write({'kickoff': t.start_date, 'venue_id': grounds[1].id, 'referee': 'Referee Two'})

    def test_byes_third_place_and_champion(self):
        players = self.env['plazy.player'].create([{'name': 'Extra %s' % i, 'full_name': 'Extra %s' % i, 'email': 'extra-%s@example.invalid' % i, 'mobile': '9876543210', 'user_id': self.env.user.id} for i in range(6)])
        extra = self.env['plazy.team'].create({'name': 'Fifth team', 'email': 'fifth@example.invalid', 'mobile': '9876543210', 'locality': 'Bengaluru', 'pincode': '560038', 'registration_status': 'approved', 'player_ids': [(6, 0, players.ids)]})
        self.teams |= extra
        t = self.tournament('knockout')
        t.third_place = True
        t.action_generate_knockout()
        self.assertEqual(len(t.match_ids), 8)
        self.assertEqual(len(t.match_ids.filtered(lambda m: m.state == 'bye')), 3)
        self.assertTrue(all(not m.kickoff and not m.completed_at for m in t.match_ids.filtered('is_bye')))
        self.schedule(t)
        for match in t.match_ids.filtered(lambda m: not m.is_bye).sorted(lambda m: (m.round_number, m.id)):
            self.assertTrue(match.home_id and match.away_id)
            match.write({'result_entered': True, 'home_score': 2, 'away_score': 0})
            match.action_confirm()
        final = t.match_ids.filtered(lambda m: m.stage == 'knockout' and not m.next_match_id and not m.is_third_place)
        self.assertEqual(final.round_label, 'Final')
        self.assertEqual(t.champion_id, final.winner_id)
        third = t.match_ids.filtered('is_third_place')
        self.assertEqual(third.state, 'completed')
        self.assertFalse(third.winner_id == t.champion_id)
        t.action_complete()

    def test_head_to_head_precedes_overall_goal_difference(self):
        t = self.tournament()
        t.tie_breaker = 'h2h'
        t.action_generate_league()
        self.schedule(t)
        a, b, c, d = self.teams.ids
        scores = {(a, b): (1, 0), (a, c): (0, 5), (a, d): (1, 0), (b, c): (4, 0), (b, d): (4, 0), (c, d): (0, 1)}
        for m in t.match_ids:
            pair = (m.home_id.id, m.away_id.id)
            home, away = scores[pair] if pair in scores else tuple(reversed(scores[tuple(reversed(pair))]))
            m.write({'result_entered': True, 'home_score': home, 'away_score': away})
            m.action_confirm()
        table = t.standings(t.group_ids)
        self.assertEqual([r['team'].id for r in table], [a, b, d, c])
        self.assertLess(table[0]['gd'], table[1]['gd'])

    def test_audited_tie_resolution_and_invalidation(self):
        t = self.tournament('hybrid')
        t.action_generate_league()
        self.schedule(t)
        t.match_ids.write({'result_entered': True})
        t.match_ids.action_confirm()
        with self.assertRaises(ValidationError):
            t.action_generate_knockout()
        group = t.group_ids
        order = list(reversed(self.teams.ids))
        group.write({'decision_reason': 'Recorded drawing of lots approved by the competition committee.', 'decision_order': ','.join(map(str, order))})
        group.action_resolve_tie()
        self.assertEqual([r['team'].id for r in t.standings(group)], order)
        m = t.match_ids[0]
        m.correction_reason = 'Verify the score sheet'
        m.action_reopen()
        self.assertFalse(any(group.registration_ids.mapped('tie_order')))
        m.action_confirm()
        group.action_resolve_tie()
        t.action_generate_knockout()
        self.assertEqual(set(t.match_ids.filtered(lambda m: m.stage == 'knockout').mapped('home_id').ids + t.match_ids.filtered(lambda m: m.stage == 'knockout').mapped('away_id').ids), set(order[:2]))
        with self.assertRaises(AccessError):
            t.event_ids.write({'details': 'Changed history'})

    def test_competition_manager_role(self):
        manager = self.env['res.users'].with_context(no_reset_password=True).create({'name': 'Competition Manager', 'login': 'competition-manager@example.invalid', 'group_ids': [(6, 0, [self.env.ref('plazy.competition_admin').id])]})
        self.assertFalse(manager.has_group('base.group_system'))
        t = self.tournament()
        t.with_user(manager).action_generate_league()
        self.assertEqual(len(t.match_ids), 6)
        with self.assertRaises(AccessError):
            self.env['plazy.competition.event'].with_user(manager).create({'tournament_id': t.id, 'action': 'fake', 'details': 'fake'})

    def test_reviewed_knockout_correction(self):
        t = self.tournament('knockout')
        t.action_generate_knockout()
        self.schedule(t)
        semifinal = t.match_ids.filtered(lambda m: m.round_number == 1)[0]
        semifinal.write({'result_entered': True, 'home_score': 2, 'away_score': 0})
        semifinal.action_confirm()
        semifinal.correction_reason = 'Correct the confirmed score after reviewing the match sheet.'
        final = semifinal.next_match_id
        self.assertTrue(final.published)
        semifinal.action_prepare_correction()
        self.assertFalse(final.published)
        self.assertFalse(final.home_id)
        self.assertEqual(semifinal.state, 'scheduled')
        semifinal.write({'home_score': 0, 'away_score': 2})
        semifinal.action_confirm()
        self.assertEqual(final.home_id, semifinal.away_id)
        self.assertFalse(final.published)

    def test_hybrid_groups_to_champion(self):
        t = self.tournament('hybrid', groups=2)
        t.qualifiers = 1
        t.action_generate_league()
        self.assertEqual(len(t.group_ids), 2)
        self.assertEqual(len(t.match_ids), 2)
        self.schedule(t)
        for m in t.match_ids:
            m.write({'result_entered': True, 'home_score': 2, 'away_score': 0})
            m.action_confirm()
        t.action_generate_knockout()
        t.action_schedule()
        t.action_publish()
        final = t.match_ids.filtered(lambda m: m.stage == 'knockout')
        final.write({'result_entered': True, 'home_score': 1, 'away_score': 0})
        final.action_confirm()
        t.action_complete()
        self.assertEqual(t.champion_id, final.home_id)
        self.assertEqual(t.state, 'completed')

    def test_portal_cannot_change_official_records(self):
        user = self.env['res.users'].with_context(no_reset_password=True).create({'name': 'Competition Player', 'login': 'competition-portal@example.invalid', 'group_ids': [(6, 0, [self.env.ref('plazy.player').id])]})
        t = self.tournament()
        with self.assertRaises(AccessError):
            t.with_user(user).action_generate_league()
        with self.assertRaises(AccessError):
            self.teams[0].with_user(user).action_approve()

    def test_walkover(self):
        t = self.tournament()
        t.action_generate_league()
        self.schedule(t)
        m = t.match_ids[0]
        m.write({'result_entered': True, 'result_kind': 'walkover', 'home_score': 3, 'away_score': 0, 'notes': 'Away team did not attend.'})
        m.action_confirm()
        self.assertEqual(m.state, 'walkover')
        self.assertEqual(next(r for r in t.standings() if r['team'] == m.home_id)['pts'], 3)

    def test_knockout_progression_and_correction_guard(self):
        t = self.tournament('knockout')
        t.action_generate_knockout()
        self.assertEqual(len(t.match_ids), 3)
        self.schedule(t)
        semifinal = t.match_ids.filtered(lambda m: m.round_number == 1)[0]
        semifinal.write({'result_entered': True, 'home_score': 1, 'away_score': 1})
        with self.assertRaises(ValidationError):
            semifinal.action_confirm()
        semifinal.write({'penalties_home': 4, 'penalties_away': 3})
        semifinal.action_confirm()
        self.assertEqual(semifinal.next_match_id.home_id, semifinal.home_id)
        semifinal.correction_reason = 'Needs review'
        with self.assertRaises(ValidationError):
            semifinal.action_reopen()

    def test_membership_and_existing_player_validation(self):
        player = self.teams[0].player_ids[0]
        result = self.env['plazy.team.player.invitation'].validate_email_for_team(self.env, self.teams[1], player.email)
        self.assertFalse(result['valid'])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            player.write({'team_ids': [(4, self.teams[1].id)]})

    def test_seven_side_limits_and_expiry(self):
        team = self.teams[0]
        team.write({'team_type': 'seven_a_side', 'registration_status': 'inviting'})
        self.assertEqual(team.required_player_count, 8)
        self.assertEqual(team.maximum_player_count, 10)
        self.assertFalse(team.can_request_approval)
        invitations = self.env['plazy.team.player.invitation'].create([{
            'team_id': team.id, 'player_name': 'Invited %s' % i, 'email': 'limit-%s@example.invalid' % i,
            'mobile': '9876543210', 'token_hash': 'limit-token-%s' % i,
            'expires_at': fields.Datetime.now() + timedelta(days=1),
        } for i in range(4)])
        with self.assertRaises(ValidationError):
            team._check_roster_space()
        validation = self.env['plazy.team.player.invitation'].validate_email_for_team(self.env, team, invitations[0].email)
        self.assertFalse(validation['valid'])
        invitations[0].expires_at = fields.Datetime.now() - timedelta(seconds=1)
        self.env['plazy.team.player.invitation']._cron_expire()
        self.assertEqual(invitations[0].status, 'expired')
        team._check_roster_space()

    def test_duplicate_application_and_schedule_conflict(self):
        t = self.tournament()
        t.action_generate_league()
        self.schedule(t)
        first, second = t.match_ids[:2]
        with self.assertRaises(ValidationError), self.cr.savepoint():
            second.kickoff = first.kickoff
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['plazy.tournament.registration'].create({'tournament_id': t.id, 'team_id': self.teams[0].id})
