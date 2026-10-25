from odoo import http, _
from odoo.tools.sql import escape_like_value
from odoo.http import request

from .main import PlazyWebsite
from .lookup import allow_player_lookup


class PlayerDiscovery(http.Controller):
    @http.route('/plazy/team/players/search', type='jsonrpc', auth='user', methods=['POST'])
    def search(self, email=''):
        team = PlazyWebsite._current_team()
        if not team or not allow_player_lookup(request.session):
            return {'players': [], 'message': _('Player search is unavailable. Please try again later.')}
        prefix = (email or '').strip().lower()
        if not 3 <= len(prefix) <= 254:
            return {'players': []}
        pattern = escape_like_value(prefix) + '%'
        players = request.env['plazy.player'].sudo().search([
            ('company_id', '=', team.company_id.id), ('discoverable', '=', True),
            ('user_id', '!=', False), ('user_id.active', '=', True), ('team_ids', '=', False),
            ('email_normalized', '=like', pattern),
        ], limit=5, order='full_name, id')
        return {'players': [{'name': p.full_name, 'email': p.email_normalized, 'position': p.position or ''} for p in players]}

    @http.route('/plazy/player/discovery', type='http', auth='user', website=True, methods=['POST'])
    def consent(self, discoverable=None, **kw):
        if not request.env.user.has_group('plazy.player'):
            return request.not_found()
        player = request.env['plazy.player'].sudo().search([('user_id', '=', request.env.user.id), ('company_id', '=', request.env.company.id)], limit=1)
        if not player:
            return request.not_found()
        player.write({'discoverable': discoverable == 'yes'})
        return request.redirect('/plazy/player/dashboard')
