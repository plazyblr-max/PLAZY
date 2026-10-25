from odoo import _, fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from ..models.competition import is_competition_admin


class PlazyAdminPortal(http.Controller):
    def _check_admin(self):
        if not is_competition_admin(request.env):
            raise AccessError(_('Only a PLAZY administrator can use this portal.'))

    @staticmethod
    def _datetime(value):
        return fields.Datetime.to_string(value) if value else False

    def _team(self, team):
        return {
            'id': team.id, 'name': team.name, 'manager_name': team.manager_name or '',
            'email': team.email, 'mobile': team.mobile, 'locality': team.locality,
            'team_type': team.team_type, 'status': team.registration_status,
            'joined_players': team.joined_player_count,
            'required_players': team.required_player_count,
            'maximum_players': team.maximum_player_count,
            'rejection_reason': team.rejection_reason or '',
            'logo_url': '/web/image/plazy.team/%s/logo' % team.id if team.logo else False,
            'created_at': self._datetime(team.create_date),
        }

    def _player(self, player):
        return {
            'id': player.id, 'name': player.full_name, 'email': player.email,
            'mobile': player.mobile, 'position': player.position or '',
            'locality': player.locality or '', 'age': player.age or False,
            'discoverable': player.discoverable, 'active': bool(player.user_id),
            'teams': [{'id': team.id, 'name': team.name} for team in player.team_ids],
            'created_at': self._datetime(player.create_date),
        }

    def _tournament(self, tournament):
        return {
            'id': tournament.id, 'name': tournament.name, 'location': tournament.location,
            'state': tournament.state, 'format': tournament.format,
            'football_format': tournament.football_format, 'approved_count': tournament.approved_count,
            'max_teams': tournament.max_teams, 'champion': tournament.champion_id.name or '',
            'start_date': self._datetime(tournament.start_date),
            'end_date': self._datetime(tournament.end_date),
            'registration_end': self._datetime(tournament.registration_end),
            'description': tournament.description or '', 'rules': tournament.rules or '',
        }

    def _match(self, match):
        return {
            'id': match.id, 'tournament_id': match.tournament_id.id,
            'tournament': match.tournament_id.name, 'round': match.round_label,
            'home': match.home_id.name or 'To be decided',
            'away': match.away_id.name or 'To be decided', 'state': match.state,
            'published': match.published, 'kickoff': self._datetime(match.kickoff),
            'venue': match.venue_id.name or '', 'score': '%s – %s' % (
                match.home_score + match.extra_home, match.away_score + match.extra_away),
            'winner': match.winner_id.name or '', 'notes': match.notes or '',
        }

    @http.route('/plazy/admin/portal', type='http', auth='user', website=True, sitemap=False)
    def portal(self):
        self._check_admin()
        return request.render('plazy.admin_portal', {
            'csrf_token': request.csrf_token(),
            'admin_name': (request.env.user.name or _('Administrator')).split()[0],
        })

    @http.route('/plazy/admin/portal/summary', type='jsonrpc', auth='user', website=True, methods=['POST'])
    def summary(self):
        self._check_admin()
        company = request.env.company
        teams = request.env['plazy.team'].sudo()
        tournaments = request.env['plazy.tournament'].sudo()
        matches = request.env['plazy.tournament.match'].sudo()
        team_domain = [('company_id', '=', company.id)]
        tournament_domain = [('company_id', '=', company.id)]
        fixture_domain = [('tournament_id.company_id', '=', company.id)]
        return {
            'players': request.env['plazy.player'].sudo().search_count(team_domain),
            'teams': teams.search_count(team_domain),
            'pending_approvals': teams.search_count(team_domain + [('registration_status', '=', 'waiting')]),
            'approved_teams': teams.search_count(team_domain + [('registration_status', '=', 'approved')]),
            'rejected_teams': teams.search_count(team_domain + [('registration_status', '=', 'rejected')]),
            'tournaments': tournaments.search_count(tournament_domain),
            'active_tournaments': tournaments.search_count(tournament_domain + [('state', 'in', ('open', 'closed', 'scheduled', 'live', 'postponed'))]),
            'completed_tournaments': tournaments.search_count(tournament_domain + [('state', '=', 'completed')]),
            'fixtures': matches.search_count(fixture_domain),
            'live_fixtures': matches.search_count(fixture_domain + [('state', '=', 'live')]),
            'recent_fixtures': [self._match(match) for match in matches.search(fixture_domain, order='kickoff desc, id desc', limit=6)],
        }

    @http.route('/plazy/admin/portal/records', type='jsonrpc', auth='user', website=True, methods=['POST'])
    def records(self, entity='teams', query='', status='', sort='recent', page=1):
        self._check_admin()
        company = request.env.company
        page = max(int(page or 1), 1)
        query = (query or '').strip()[:100]
        status = (status or '').strip()
        config = {
            'players': ('plazy.player', [('company_id', '=', company.id)], 'full_name', self._player, 'full_name asc, id desc'),
            'teams': ('plazy.team', [('company_id', '=', company.id)], 'name', self._team, 'name asc, id desc'),
            'approvals': ('plazy.team', [('company_id', '=', company.id), ('registration_status', '=', 'waiting')], 'name', self._team, 'approval_requested_at desc, id desc'),
            'tournaments': ('plazy.tournament', [('company_id', '=', company.id)], 'name', self._tournament, 'start_date desc, id desc'),
            'fixtures': ('plazy.tournament.match', [('tournament_id.company_id', '=', company.id)], 'fixture_key', self._match, 'kickoff desc, id desc'),
        }
        if entity not in config:
            raise ValidationError(_('Unknown portal collection.'))
        model_name, domain, name_field, serializer, default_order = config[entity]
        if query:
            domain.append((name_field, 'ilike', query))
        if status:
            domain.append(('registration_status' if entity in ('teams', 'approvals') else 'state', '=', status))
        order = default_order if sort != 'name' else '%s asc, id desc' % name_field
        model = request.env[model_name].sudo()
        total = model.search_count(domain)
        limit = 12
        return {
            'records': [serializer(record) for record in model.search(domain, order=order, limit=limit, offset=(page - 1) * limit)],
            'total': total, 'page': page, 'pages': max((total + limit - 1) // limit, 1),
        }

    @http.route('/plazy/admin/portal/detail', type='jsonrpc', auth='user', website=True, methods=['POST'])
    def detail(self, entity, record_id):
        self._check_admin()
        company = request.env.company
        models = {
            'players': ('plazy.player', [('company_id', '=', company.id)], self._player),
            'teams': ('plazy.team', [('company_id', '=', company.id)], self._team),
            'approvals': ('plazy.team', [('company_id', '=', company.id)], self._team),
            'tournaments': ('plazy.tournament', [('company_id', '=', company.id)], self._tournament),
            'fixtures': ('plazy.tournament.match', [('tournament_id.company_id', '=', company.id)], self._match),
        }
        if entity not in models:
            raise ValidationError(_('Unknown portal record.'))
        model_name, domain, serializer = models[entity]
        record = request.env[model_name].sudo().search([('id', '=', int(record_id))] + domain, limit=1)
        if not record:
            raise ValidationError(_('This record is unavailable.'))
        result = serializer(record)
        if entity in ('teams', 'approvals'):
            result['players'] = [self._player(player) for player in record.player_ids]
            result['invitations'] = [{'name': invitation.player_name, 'email': invitation.email, 'status': invitation.status} for invitation in record.invitation_ids]
        elif entity == 'tournaments':
            result['registrations'] = [{
                'id': item.id,
                'team': item.team_id.name,
                'state': item.state,
                'group': item.group_id.name or '',
            } for item in record.registration_ids]
            result['fixtures'] = [self._match(match) for match in record.match_ids]
        elif entity == 'fixtures':
            result['audit'] = [{'date': self._datetime(item.create_date), 'description': item.description} for item in record.audit_ids]
        return result

    @http.route('/plazy/admin/portal/team-action', type='jsonrpc', auth='user', website=True, methods=['POST'])
    def team_action(self, team_id, action, reason=''):
        self._check_admin()
        team = request.env['plazy.team'].sudo().search([
            ('id', '=', int(team_id)), ('company_id', '=', request.env.company.id),
        ], limit=1)
        if not team or action not in ('approve', 'reject'):
            raise ValidationError(_('Invalid team action.'))
        try:
            with request.env.cr.savepoint():
                if action == 'approve':
                    team.action_approve()
                else:
                    team.write({'rejection_reason': (reason or '').strip()})
                    team.action_reject()
            return {'ok': True, 'message': _('Team updated successfully.')}
        except ValidationError as error:
            return {'ok': False, 'message': str(error)}

    @http.route('/plazy/admin/portal/tournament-action', type='jsonrpc', auth='user', website=True, methods=['POST'])
    def tournament_action(self, tournament_id, action, reason=''):
        self._check_admin()
        tournament = request.env['plazy.tournament'].sudo().search([
            ('id', '=', int(tournament_id)), ('company_id', '=', request.env.company.id),
        ], limit=1)
        actions = {
            'open': 'action_open', 'close': 'action_close', 'league': 'action_generate_league',
            'knockout': 'action_generate_knockout', 'schedule': 'action_schedule',
            'publish': 'action_publish', 'complete': 'action_complete', 'resume': 'action_resume',
            'postpone': 'action_postpone', 'cancel': 'action_cancel',
        }
        if not tournament or action not in actions:
            raise ValidationError(_('Invalid tournament action.'))
        try:
            with request.env.cr.savepoint():
                if action in ('postpone', 'cancel'):
                    tournament.write({'change_reason': (reason or '').strip()})
                getattr(tournament, actions[action])()
            return {'ok': True, 'message': _('Tournament updated successfully.')}
        except ValidationError as error:
            return {'ok': False, 'message': str(error)}
