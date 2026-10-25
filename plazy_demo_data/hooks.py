import hashlib
from datetime import timedelta

from odoo import fields

MODULE = 'plazy_demo_data'
PASSWORD = 'plazy-demo-2026'


def _external_id(env, record, name):
    """Give hook-created records stable IDs and make a repeated hook harmless."""
    env['ir.model.data'].sudo().create({
        'module': MODULE,
        'name': name,
        'model': record._name,
        'res_id': record.id,
        'noupdate': True,
    })
    return record


def _ensure(env, model, name, values):
    record = env.ref('%s.%s' % (MODULE, name), raise_if_not_found=False)
    if record:
        return record.sudo()
    return _external_id(env, env[model].sudo().create(values), name)


def _demo_user(env, name, email, group_xmlid):
    group = env.ref(group_xmlid)
    return _ensure(env, 'res.users',
                   'user_%s' % email.split('@')[0].replace('.', '_'), {
                       'name': name,
                       'login': email,
                       'email': email,
                       'password': PASSWORD,
                       'company_id': env.company.id,
                       'company_ids': [(6, 0, [env.company.id])],
                       'group_ids': [(6, 0, [group.id])],
                   })


def _demo_player(env, key, full_name, email, position, user=False,
                 discoverable=False):
    return _ensure(env, 'plazy.player', 'player_%s' % key, {
        'name': full_name,
        'full_name': full_name,
        'email': email,
        'mobile': '9%09d' % (100000000 + len(key) * 1000),
        'age': 20 + (len(key) % 12),
        'position': position,
        'locality': 'Koramangala',
        'pincode': '560034',
        'company_id': env.company.id,
        'user_id': user.id if user else False,
        'discoverable': discoverable,
    })


def _roster(env, prefix, names):
    positions = ['GK', 'RB', 'LB', 'MID', 'Winger', 'ST']
    players = env['plazy.player']
    for index, full_name in enumerate(names):
        email = '%s.%s@demo.plazy.test' % (prefix, index + 1)
        user = _demo_user(env, full_name, email, 'plazy.player')
        players |= _demo_player(env, '%s_%s' % (prefix, index + 1), full_name,
                                email, positions[index], user)
    return players


def _demo_team(env, key, name, manager_name, status, players,
               rejection_reason=False):
    manager_email = '%s.manager@demo.plazy.test' % key
    manager = _demo_user(env, manager_name, manager_email, 'plazy.team')
    team = _ensure(env, 'plazy.team', 'team_%s' % key, {
        'name': name,
        'manager_name': manager_name,
        'email': manager_email,
        'mobile': '98765%05d' % (len(key) * 1111),
        'locality': 'Bengaluru',
        'pincode': '560001',
        'team_type': 'five_a_side',
        'company_id': env.company.id,
        'user_id': manager.id,
        'registration_status': status,
        'rejection_reason': rejection_reason,
        'approval_requested_at': fields.Datetime.now() if status in ('waiting',
                                                                     'approved',
                                                                     'rejected') else False,
        'approved_at': fields.Datetime.now() if status == 'approved' else False,
    })
    if players and not team.player_ids:
        team.write({'player_ids': [(6, 0, players.ids)]})
    return team


def _application(env, key, tournament, team, group=False, state='approved',
                 reason=False):
    registration = _ensure(env, 'plazy.tournament.registration',
                           'registration_%s' % key, {
                               'tournament_id': tournament.id,
                               'team_id': team.id,
                           })
    if state == 'approved' and registration.state != 'approved':
        registration.action_approve()
    elif state != registration.state:
        registration.write({
            'state': state,
            'reason': reason,
            'roster_ids': [
                (6, 0, team.player_ids.ids)] if state == 'approved' else [],
        })
    if group and registration.group_id != group:
        registration.write({'group_id': group.id})
    return registration


def _fixture(env, key, tournament, home, away, kickoff, venue, group=False):
    return _ensure(env, 'plazy.tournament.match', 'match_%s' % key, {
        'tournament_id': tournament.id,
        'fixture_key': 'DEMO:%s' % key,
        'stage': 'league' if group else 'knockout',
        'group_id': group.id if group else False,
        'round_number': 1,
        'home_id': home.id,
        'away_id': away.id,
        'kickoff': kickoff,
        'venue_id': venue.id,
        'duration': 40,
        'published': True,
    })


def _otp(env, key, email, account_type, expires_at, verified=False, attempts=0,
         user=False):
    return _ensure(env, 'plazy.registration.otp', 'otp_%s' % key, {
        'email': email,
        'account_type': account_type,
        'company_id': env.company.id,
        'user_id': user.id if user else False,
        'code_hash': hashlib.sha256(('demo-%s' % key).encode()).hexdigest(),
        'access_token': 'plazy-demo-reset-%s' % key,
        'expires_at': expires_at,
        'attempts': attempts,
        'is_verified': verified,
    })


def post_init_hook(env):
    """Seed a self-contained, idempotent Plazy workflow demonstration."""
    now = fields.Datetime.now()

    venue = _ensure(env, 'plazy.tournament.venue', 'venue_bengaluru_arena', {
        'name': 'Bengaluru Demo Arena',
        'location': 'Koramangala, Bengaluru',
    })
    _ensure(env, 'plazy.tournament.slot', 'venue_bengaluru_arena_opening', {
        'venue_id': venue.id,
        'start': now - timedelta(days=90),
        'end': now + timedelta(days=180),
    })

    aurora = _demo_team(env, 'aurora', 'Aurora FC', 'Aditi Rao', 'approved',
                        _roster(env, 'aurora', [
                            'Arjun Mehta', 'Dev Nair', 'Ishaan Shah',
                            'Kabir Khan', 'Neil Thomas', 'Rohan Das',
                        ]))
    falcons = _demo_team(env, 'falcons', 'Koramangala Falcons', 'Farah Ali',
                         'approved', _roster(env, 'falcons', [
            'Aman Gupta', 'Bharat Iyer', 'Chetan Roy', 'Danish Paul',
            'Eshan Bose', 'Faisal Khan',
        ]))
    united = _demo_team(env, 'united', 'Whitefield United', 'Meera Nair',
                        'approved', _roster(env, 'united', [
            'Gautam Jain', 'Harish Rao', 'Imran Sheikh', 'Jatin Kapoor',
            'Kiran Kumar', 'Lalit Verma',
        ]))
    strikers = _demo_team(env, 'strikers', 'Indiranagar Strikers',
                          'Nikhil Bhat', 'approved', _roster(env, 'strikers', [
            'Manu Menon', 'Naveen Pillai', 'Om Prakash', 'Pranav Sethi',
            'Qasim Ali', 'Ravi Soni',
        ]))
    _demo_team(env, 'pending', 'HSR Rangers', 'Pooja Shah', 'waiting',
               _roster(env, 'pending', [
                   'Sanjay Rao', 'Tushar Jain', 'Uday Kumar', 'Varun Malik',
                   'Wasim Akhtar', 'Yash Patil',
               ]))
    _demo_team(env, 'rejected', 'BTM Blazers', 'Rahul Menon', 'rejected',
               _roster(env, 'rejected', [
                   'Zaid Ahmed', 'Anil Mathew', 'Binu George', 'Charan Reddy',
                   'Deepak Singh', 'Ejaz Khan',
               ]),
               'Please upload a recognisable team crest and confirm the manager contact number.')
    inviting_players = _roster(env, 'inviting',
                               ['Aarav Kapoor', 'Bhavesh Patel', 'Chirag Nair'])
    inviting = _demo_team(env, 'inviting', 'Jayanagar Jaguars', 'Sana Mirza',
                          'inviting', inviting_players)
    _demo_team(env, 'onboarding', 'Electronic City Eleven', 'Vikram Joshi',
               'onboarding', env['plazy.player'])

    available_user = _demo_user(env, 'Diya Fernandes',
                                'diya.fernandes@demo.plazy.test',
                                'plazy.player')
    _demo_player(env, 'available', 'Diya Fernandes',
                 'diya.fernandes@demo.plazy.test', 'MID', available_user, True)
    pending_invitee = _demo_player(env, 'pending_invitee', 'Gauri Kulkarni',
                                   'gauri.kulkarni@demo.plazy.test', 'Winger')
    expired_invitee = _demo_player(env, 'expired_invitee', 'Himanshu Arora',
                                   'himanshu.arora@demo.plazy.test', 'ST')
    rejected_invitee = _demo_player(env, 'rejected_invitee', 'Ira Banerjee',
                                    'ira.banerjee@demo.plazy.test', 'GK')

    sent_token = 'plazy-demo-pending-invitation-token'
    _ensure(env, 'plazy.team.player.invitation', 'invitation_sent', {
        'team_id': inviting.id,
        'company_id': env.company.id,
        'player_id': pending_invitee.id,
        'player_name': pending_invitee.full_name,
        'email': pending_invitee.email,
        'mobile': pending_invitee.mobile,
        'position': pending_invitee.position,
        'status': 'sent',
        'token_hash': hashlib.sha256(sent_token.encode()).hexdigest(),
        'expires_at': now + timedelta(days=7),
    })
    _ensure(env, 'plazy.team.player.invitation', 'invitation_expired', {
        'team_id': inviting.id,
        'company_id': env.company.id,
        'player_id': expired_invitee.id,
        'player_name': expired_invitee.full_name,
        'email': expired_invitee.email,
        'mobile': expired_invitee.mobile,
        'position': expired_invitee.position,
        'status': 'expired',
        'token_hash': hashlib.sha256(
            b'plazy-demo-expired-invitation-token').hexdigest(),
        'expires_at': now - timedelta(days=1),
    })
    _ensure(env, 'plazy.team.player.invitation', 'invitation_rejected', {
        'team_id': inviting.id,
        'company_id': env.company.id,
        'player_id': rejected_invitee.id,
        'player_name': rejected_invitee.full_name,
        'email': rejected_invitee.email,
        'mobile': rejected_invitee.mobile,
        'position': rejected_invitee.position,
        'status': 'rejected',
        'token_hash': hashlib.sha256(
            b'plazy-demo-rejected-invitation-token').hexdigest(),
        'expires_at': now + timedelta(days=5),
    })
    _ensure(env, 'plazy.team.player.invitation', 'invitation_joined', {
        'team_id': aurora.id,
        'company_id': env.company.id,
        'player_id': aurora.player_ids[0].id,
        'existing_user_id': aurora.player_ids[0].user_id.id,
        'player_name': aurora.player_ids[0].full_name,
        'email': aurora.player_ids[0].email,
        'mobile': aurora.player_ids[0].mobile,
        'position': aurora.player_ids[0].position,
        'status': 'joined',
        'token_hash': hashlib.sha256(
            b'plazy-demo-joined-invitation-token').hexdigest(),
        'expires_at': now - timedelta(days=10),
        'accepted_at': now - timedelta(days=12),
    })

    _otp(env, 'pending_player', 'new.player@demo.plazy.test', 'player',
         now + timedelta(minutes=8))
    _otp(env, 'expired_team', 'old.manager@demo.plazy.test', 'team',
         now - timedelta(minutes=5), attempts=2)
    _otp(env, 'verified_reset', aurora.user_id.email, 'password_reset',
         now + timedelta(minutes=5), verified=True, user=aurora.user_id)

    _ensure(env, 'plazy.tournament', 'tournament_draft', {
        'name': 'Bengaluru Future Cup', 'company_id': env.company.id,
        'football_format': 'five_a_side',
        'format': 'hybrid', 'location': 'Sarjapur Road',
        'registration_start': now + timedelta(days=14),
        'registration_end': now + timedelta(days=28),
        'start_date': now + timedelta(days=35),
        'end_date': now + timedelta(days=38), 'min_teams': 4, 'max_teams': 8,
        'group_count': 2,
        'qualifiers': 2, 'duration': 40, 'rest_minutes': 20, 'state': 'draft',
        'description': 'A future draft competition for configuration testing.',
    })
    open_tournament = _ensure(env, 'plazy.tournament', 'tournament_open', {
        'name': 'Monsoon 5s Open', 'company_id': env.company.id,
        'football_format': 'five_a_side',
        'format': 'league', 'location': 'HSR Layout',
        'registration_start': now - timedelta(days=2),
        'registration_end': now + timedelta(days=5),
        'start_date': now + timedelta(days=10),
        'end_date': now + timedelta(days=13), 'min_teams': 4, 'max_teams': 4,
        'group_count': 1,
        'qualifiers': 1, 'duration': 40, 'rest_minutes': 20, 'state': 'open',
        'published': True,
        'description': 'An open competition with pending, rejected, and waitlisted applications.',
    })
    _application(env, 'open_aurora_pending', open_tournament, aurora,
                 state='pending')
    _application(env, 'open_falcons_rejected', open_tournament, falcons,
                 state='rejected',
                 reason='Demo rejection: incomplete insurance document.')
    _application(env, 'open_united_waitlisted', open_tournament, united,
                 state='waitlisted',
                 reason='Demo waitlist: registration capacity reserved.')

    live_tournament = _ensure(env, 'plazy.tournament', 'tournament_live', {
        'name': 'Koramangala League Night', 'company_id': env.company.id,
        'football_format': 'five_a_side',
        'format': 'league', 'location': venue.location,
        'registration_start': now - timedelta(days=20),
        'registration_end': now + timedelta(days=2),
        'start_date': now + timedelta(days=5),
        'end_date': now + timedelta(days=10), 'min_teams': 4, 'max_teams': 4,
        'group_count': 1,
        'qualifiers': 1, 'duration': 40, 'rest_minutes': 20, 'state': 'open',
        'published': True,
        'venue_ids': [(6, 0, [venue.id])],
        'description': 'Live demo league with scheduled, live, and completed matches.',
    })
    for key, team in (
        ('aurora', aurora), ('falcons', falcons), ('united', united),
        ('strikers', strikers),
    ):
        _application(env, 'live_%s' % key, live_tournament, team)
    if live_tournament.state == 'open':
        live_tournament.write({
            'registration_start': now - timedelta(days=14),
            'registration_end': now - timedelta(days=7),
            'start_date': now - timedelta(hours=2),
            'end_date': now + timedelta(days=5),
        })
        live_tournament.action_close()
    if not live_tournament.match_ids:
        live_tournament.action_generate_league()
        live_tournament.action_schedule()
        live_tournament.action_publish()
    matches = live_tournament.match_ids.sorted(
        lambda match: (match.kickoff, match.id))
    completed_match = matches[0]
    if completed_match.state == 'scheduled':
        completed_match.write({
            'home_score': 3,
            'away_score': 1,
            'result_entered': True,
            'notes': 'Demo completed league match.',
        })
        completed_match.action_confirm()
    live_match = matches[1]
    if live_match.state == 'scheduled':
        live_match.action_live()

    completed_tournament = _ensure(env, 'plazy.tournament',
                                   'tournament_completed', {
                                       'name': 'Summer Knockout Champions',
                                       'company_id': env.company.id,
                                       'football_format': 'five_a_side',
                                       'format': 'knockout',
                                       'location': venue.location,
                                       'registration_start': now - timedelta(
                                           days=10),
                                       'registration_end': now + timedelta(
                                           days=2),
                                       'start_date': now + timedelta(days=4),
                                       'end_date': now + timedelta(days=8),
                                       'min_teams': 2, 'max_teams': 2,
                                       'group_count': 1,
                                       'qualifiers': 1, 'duration': 40,
                                       'rest_minutes': 20, 'state': 'open',
                                       'published': True,
                                       'venue_ids': [(6, 0, [venue.id])],
                                       'description': 'Completed two-team knockout, including an official final result.',
                                   })
    _application(env, 'completed_aurora', completed_tournament, aurora)
    _application(env, 'completed_strikers', completed_tournament, strikers)
    completed_tournament.write({
        'registration_start': now - timedelta(days=30),
        'registration_end': now - timedelta(days=20),
        'start_date': now - timedelta(days=10),
        'end_date': now - timedelta(days=2),
    })
    if completed_tournament.state == 'open':
        completed_tournament.action_close()
    if not completed_tournament.match_ids:
        completed_tournament.action_generate_knockout()
        completed_tournament.action_schedule()
        completed_tournament.action_publish()
    final = completed_tournament.match_ids.sorted(
        lambda match: (match.kickoff, match.id))[0]
    if final.state == 'scheduled':
        final.write({'home_score': 2, 'away_score': 0, 'result_entered': True,
                     'notes': 'Aurora FC won the demo final.'})
        final.action_confirm()
    if completed_tournament.state != 'completed':
        completed_tournament.action_complete()

    cancelled = _ensure(env, 'plazy.tournament', 'tournament_cancelled', {
        'name': 'Rainout Weekend Cup', 'company_id': env.company.id,
        'football_format': 'five_a_side',
        'format': 'knockout', 'location': 'Whitefield',
        'registration_start': now - timedelta(days=1),
        'registration_end': now + timedelta(days=3),
        'start_date': now + timedelta(days=6),
        'end_date': now + timedelta(days=8), 'min_teams': 4, 'max_teams': 8,
        'group_count': 1,
        'qualifiers': 1, 'duration': 40, 'rest_minutes': 20, 'state': 'open',
        'published': True,
        'change_reason': 'Demo cancellation: severe weather warning.',
    })
    if cancelled.state != 'cancelled':
        cancelled.action_cancel()
