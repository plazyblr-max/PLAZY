from urllib.parse import urlencode

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import ValidationError

from .main import PlazyWebsite
from ..models.competition import is_competition_admin


class CompetitionWebsite(http.Controller):
    @http.route(['/plazy/admin/tournament/new', '/plazy/admin/tournament/<int:tournament_id>'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def manage_tournament(self, tournament_id=None, **post):
        if not is_competition_admin(request.env):
            return request.not_found()
        tournament = request.env['plazy.tournament'].search([('id', '=', tournament_id), ('company_id', 'in', request.env.companies.ids)], limit=1) if tournament_id else request.env['plazy.tournament']
        if tournament_id and not tournament:
            return request.not_found()
        error = False
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    if tournament:
                        actions = {'open': 'action_open', 'close': 'action_close', 'league': 'action_generate_league', 'knockout': 'action_generate_knockout', 'schedule': 'action_schedule', 'publish': 'action_publish', 'complete': 'action_complete'}
                        action = actions.get(post.get('action'))
                        if not action:
                            raise ValidationError(_('Choose a valid competition action.'))
                        getattr(tournament, action)()
                    else:
                        values = {key: post.get(key) for key in ('name', 'location', 'description', 'rules', 'football_format', 'format')}
                        for key in ('min_teams', 'max_teams', 'group_count', 'qualifiers', 'duration'):
                            values[key] = int(post.get(key, 0))
                        from datetime import datetime
                        from zoneinfo import ZoneInfo
                        from datetime import timezone
                        zone = ZoneInfo(request.env.user.tz or 'Asia/Kolkata')
                        for key in ('registration_start', 'registration_end', 'start_date', 'end_date'):
                            values[key] = datetime.fromisoformat(post.get(key, '')).replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
                        tournament = request.env['plazy.tournament'].create(values)
                return request.redirect('/plazy/admin/tournament/%s' % tournament.id)
            except (ValidationError, ValueError) as exc:
                error = str(exc)
        return request.render('plazy.competition_manage', {'tournament': tournament, 'error': error, 'form': post, 'timezone': request.env.user.tz or 'Asia/Kolkata'})

    @http.route('/plazy/admin/application/<int:registration_id>/<string:action>', type='http', auth='user', website=True, methods=['POST'])
    def review_application(self, registration_id, action, **post):
        if not is_competition_admin(request.env) or action not in ('approve', 'reject'):
            return request.not_found()
        registration = request.env['plazy.tournament.registration'].search([('id', '=', registration_id), ('tournament_id.company_id', 'in', request.env.companies.ids)], limit=1)
        if not registration:
            return request.not_found()
        try:
            with request.env.cr.savepoint():
                if action == 'reject':
                    registration.reason = post.get('reason')
                getattr(registration, 'action_' + action)()
        except ValidationError as exc:
            request.session['plazy_competition_message'] = str(exc)
        return request.redirect('/plazy/admin/tournament/%s' % registration.tournament_id.id)

    @http.route('/plazy/admin/match/<int:match_id>/result', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def manage_result(self, match_id, **post):
        if not is_competition_admin(request.env):
            return request.not_found()
        match = request.env['plazy.tournament.match'].search([('id', '=', match_id), ('tournament_id.company_id', 'in', request.env.companies.ids)], limit=1)
        if not match:
            return request.not_found()
        error = False
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    if post.get('action') in ('reopen', 'prepare_correction'):
                        match.correction_reason = post.get('reason')
                        if post.get('action') == 'prepare_correction':
                            match.action_prepare_correction()
                        else:
                            match.action_reopen()
                    else:
                        values = {key: int(post.get(key, 0)) for key in ('home_score', 'away_score', 'extra_home', 'extra_away', 'penalties_home', 'penalties_away')}
                        match.write(dict(values, result_entered=True, notes=post.get('notes')))
                        match.action_confirm()
                return request.redirect('/plazy/admin/tournament/%s' % match.tournament_id.id)
            except (ValidationError, ValueError) as exc:
                error = str(exc)
        return request.render('plazy.competition_result_editor', {'match': match, 'error': error, 'dependents': match._dependent_matches()})

    def _tournament(self, tournament_id):
        return request.env['plazy.tournament'].sudo().search([
            ('id', '=', tournament_id), ('published', '=', True),
            ('company_id', '=', request.env.company.id),
        ], limit=1)

    @http.route('/plazy/tournaments', type='http', auth='public', website=True)
    def tournaments(self, **kw):
        domain = [
            ('published', '=', True), ('company_id', '=', request.env.company.id),
        ]
        query = (kw.get('q') or '').strip()[:100]
        football_format = kw.get('format') if kw.get('format') in ('five_a_side', 'seven_a_side') else ''
        state = kw.get('state') if kw.get('state') in ('open', 'scheduled', 'live', 'completed') else ''
        if query:
            domain.append(('name', 'ilike', query))
        if football_format:
            domain.append(('football_format', '=', football_format))
        if state:
            domain.append(('state', '=', state))
        model = request.env['plazy.tournament'].sudo()
        count = model.search_count(domain)
        try:
            page = max(1, min(int(kw.get('page', 1)), max(1, (count + 11) // 12)))
        except (ValueError, TypeError):
            page = 1
        params = {'q': query, 'format': football_format, 'state': state}
        return request.render('plazy.competition_listing', {
            'tournaments': model.search(domain, limit=12, offset=(page-1)*12),
            'query': query, 'football_format': football_format, 'filter_state': state,
            'page': page, 'page_count': max(1, (count+11)//12),
            'previous_url': '/plazy/tournaments?' + urlencode(dict(params, page=page-1)) if page > 1 else False,
            'next_url': '/plazy/tournaments?' + urlencode(dict(params, page=page+1)) if page*12 < count else False,
        })

    @http.route('/plazy/tournaments/<int:tournament_id>', type='http', auth='public', website=True)
    def tournament(self, tournament_id, tab='overview', **kw):
        tournament = self._tournament(tournament_id)
        if not tournament:
            return request.not_found()
        tab = tab if tab in ('overview', 'teams', 'fixtures', 'results', 'standings', 'bracket', 'rules') else 'overview'
        team = PlazyWebsite._current_team()
        application = tournament.registration_ids.filtered(lambda r: team and r.team_id == team)
        matches = tournament.match_ids.filtered('published')
        return request.render('plazy.competition_detail', {
            'tournament': tournament, 'tab': tab, 'team': team, 'application': application,
            'matches': matches, 'message': request.session.pop('plazy_competition_message', False),
            'teams': tournament.registration_ids.filtered(lambda r: r.state == 'approved').mapped('team_id'),
            'tables': [(g, tournament.standings(g)) for g in tournament.group_ids] if matches else [],
        })

    @http.route('/plazy/tournaments/<int:tournament_id>/register', type='http', auth='user', website=True, methods=['POST'])
    def register(self, tournament_id, **kw):
        tournament = self._tournament(tournament_id)
        team = PlazyWebsite._current_team()
        if not tournament or not team:
            return request.not_found()
        try:
            with request.env.cr.savepoint():
                tournament._lock()
                if tournament.registration_ids.filtered(lambda r: r.team_id == team):
                    raise ValidationError(_('Your team already has an application for this tournament.'))
                request.env['plazy.tournament.registration'].sudo().create({'tournament_id': tournament.id, 'team_id': team.id})
            request.session['plazy_competition_message'] = _('Application submitted. An administrator will review your team.')
        except ValidationError as error:
            request.session['plazy_competition_message'] = str(error)
        return request.redirect('/plazy/tournaments/%s' % tournament_id)

    @http.route('/plazy/matches/<int:match_id>', type='http', auth='public', website=True)
    def match(self, match_id, **kw):
        match = request.env['plazy.tournament.match'].sudo().search([
            ('id', '=', match_id), ('published', '=', True), ('tournament_id.published', '=', True),
            ('tournament_id.company_id', '=', request.env.company.id),
        ], limit=1)
        if not match:
            return request.not_found()
        return request.render('plazy.competition_match', {'match': match})

    @http.route('/plazy/team/registrations/<int:registration_id>/withdraw', type='http', auth='user', website=True, methods=['POST'])
    def withdraw(self, registration_id, **kw):
        team = PlazyWebsite._current_team()
        if not team:
            return request.not_found()
        registration = request.env['plazy.tournament.registration'].sudo().search([('id', '=', registration_id), ('team_id', '=', team.id)], limit=1)
        if not registration:
            return request.not_found()
        try:
            with request.env.cr.savepoint():
                registration.tournament_id._lock()
                registration.action_withdraw()
            request.session['plazy_competition_message'] = _('Application withdrawn.')
        except ValidationError as exc:
            request.session['plazy_competition_message'] = str(exc)
        return request.redirect('/plazy/competition/dashboard')

    @http.route('/plazy/player/invitations/<int:invitation_id>/<string:action>', type='http', auth='user', website=True, methods=['POST'])
    def invitation_action(self, invitation_id, action, **kw):
        invitation = request.env['plazy.team.player.invitation'].sudo().search([
            ('id', '=', invitation_id), ('player_id.user_id', '=', request.env.user.id),
        ], limit=1)
        if not invitation or action not in ('accept', 'reject'):
            return request.not_found()
        try:
            with request.env.cr.savepoint():
                invitation.team_id._lock_roster()
                if not invitation.is_usable():
                    raise ValidationError(_('This invitation is no longer available.'))
                if action == 'accept':
                    invitation.accept()
                    invitation.mark_joined()
                else:
                    invitation.status = 'rejected'
            request.session['plazy_competition_message'] = _('Invitation updated.')
        except ValidationError as error:
            request.session['plazy_competition_message'] = str(error)
        return request.redirect('/plazy/competition/dashboard')

    @http.route('/plazy/competition/dashboard', type='http', auth='user', website=True)
    def dashboard(self, **kw):
        team = PlazyWebsite._current_team()
        player = request.env['plazy.player'].sudo().search([('user_id', '=', request.env.user.id)], limit=1)
        teams = team or player.team_ids
        admin = is_competition_admin(request.env)
        domain = [('tournament_id.company_id', '=', request.env.company.id)]
        if not admin:
            domain += [('published', '=', True), '|', ('home_id', 'in', teams.ids), ('away_id', 'in', teams.ids)]
        match_model = request.env['plazy.tournament.match'].sudo()
        count = match_model.search_count(domain)
        try:
            page = max(1, min(int(kw.get('page', 1)), max(1, (count+19)//20)))
        except (ValueError, TypeError):
            page = 1
        matches = match_model.search(domain, limit=20, offset=(page-1)*20, order='kickoff desc, id desc')
        invitations = request.env['plazy.team.player.invitation'].sudo().search([('player_id', '=', player.id), ('status', '=', 'sent')]) if player else request.env['plazy.team.player.invitation']
        invitations._expire_if_needed()
        registrations = request.env['plazy.tournament.registration'].sudo().search([('team_id', 'in', teams.ids)])
        return request.render('plazy.competition_dashboard', {
            'admin': admin, 'matches': matches, 'invitations': invitations.filtered(lambda i: i.status == 'sent'),
            'registrations': registrations, 'message': request.session.pop('plazy_competition_message', False),
            'tournament_count': request.env['plazy.tournament'].sudo().search_count([('company_id', '=', request.env.company.id), ('state', 'not in', ['completed', 'cancelled'])]) if admin else 0,
            'pending_count': request.env['plazy.tournament.registration'].sudo().search_count([('state', '=', 'pending'), ('tournament_id.company_id', '=', request.env.company.id)]) if admin else 0,
            'admin_tournaments': request.env['plazy.tournament'].search([('company_id', 'in', request.env.companies.ids)], limit=100) if admin else [],
            'page': page, 'page_count': max(1, (count+19)//20),
            'previous_url': '/plazy/competition/dashboard?page=%s' % (page-1) if page > 1 else False,
            'next_url': '/plazy/competition/dashboard?page=%s' % (page+1) if page*20 < count else False,
        })
