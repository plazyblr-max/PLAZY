"""Development-only sample data. Run with Odoo shell on the isolated review DB."""
from datetime import timedelta
from odoo import fields

assert env.cr.dbname == 'plazy_competition_review', 'Never seed a customer database.'
if not env['plazy.tournament'].search_count([]):
    now = fields.Datetime.now()
    tournament = env['plazy.tournament'].create({
        'name': 'PLAZY Review League (Demo)', 'location': 'Bengaluru',
        'description': 'Development preview competition. These teams and fixtures are illustrative test data.',
        'rules': 'Single round robin. Three points for a win, one for a draw. Top two advance to the knockout final.',
        'football_format': 'five_a_side', 'format': 'hybrid', 'group_count': 1,
        'min_teams': 4, 'max_teams': 4, 'registration_start': now - timedelta(days=1),
        'registration_end': now + timedelta(days=1), 'start_date': now + timedelta(days=2),
        'end_date': now + timedelta(days=5),
    })
    tournament.action_open()
    for number, name in enumerate(['Indiranagar FC', 'Koramangala United', 'Whitefield Athletic', 'HSR Rovers']):
        players = env['plazy.player'].create([{'name': 'Demo Player %s-%s' % (number, i), 'full_name': 'Demo Player %s-%s' % (number, i), 'email': 'demo-%s-%s@example.invalid' % (number, i), 'mobile': '9876543210', 'user_id': env.user.id} for i in range(6)])
        team = env['plazy.team'].create({'name': name + ' (Demo)', 'email': 'demo-team%s@example.invalid' % number, 'mobile': '9876543210', 'locality': 'Bengaluru', 'pincode': '560038', 'team_type': 'five_a_side', 'registration_status': 'approved', 'player_ids': [(6, 0, players.ids)]})
        env['plazy.tournament.registration'].create({'tournament_id': tournament.id, 'team_id': team.id}).action_approve()
    tournament.action_close()
    tournament.action_generate_league()
    ground = env['plazy.tournament.venue'].create({'name': 'Review Ground (Demo)', 'location': 'Bengaluru', 'slot_ids': [(0, 0, {'start': tournament.start_date, 'end': tournament.end_date})]})
    tournament.venue_ids = ground
    tournament.action_schedule()
    tournament.action_publish()
    for match in tournament.match_ids:
        match.write({'home_score': 3 if match.home_id.id < match.away_id.id else 0, 'away_score': 3 if match.away_id.id < match.home_id.id else 0, 'result_entered': True})
        match.action_confirm()
    tournament.action_generate_knockout()
    tournament.action_schedule()
    tournament.match_ids.filtered(lambda m: m.stage == 'knockout').write({'published': True})
    env.cr.commit()
print('Review competition data ready.')
