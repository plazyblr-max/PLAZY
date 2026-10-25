from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PlazyPlayer(models.Model):
    _name = 'plazy.player'
    _description = 'Plazy Player'
    _rec_name = 'full_name'

    name = fields.Char(string='Name', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    full_name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email', required=True, index=True)
    email_normalized = fields.Char(compute='_compute_normalized_email', store=True, index=True)
    discoverable = fields.Boolean(default=False, string='Allow email-prefix discovery')
    mobile = fields.Char(string='Mobile Number', required=True)
    position = fields.Selection([
        ('GK', 'Goalkeeper'), ('ST', 'Striker'), ('Winger', 'Winger'),
        ('LB', 'Left back'), ('RB', 'Right back'), ('MID', 'Midfielder'),
    ], string='Preferred Position')
    # Team managers only collect the essentials for an invitation. Players can
    # complete these profile details later through the normal player profile flow.
    age = fields.Integer(string='Age')
    locality = fields.Char(string='Bangalore Locality')
    pincode = fields.Char(string='PIN Code')
    user_id = fields.Many2one('res.users', string='User', ondelete='set null', copy=False)
    team_ids = fields.Many2many('plazy.team', 'plazy_player_team_rel', 'player_id', 'team_id', string='Teams', copy=False)

    @api.depends('email')
    def _compute_normalized_email(self):
        for player in self:
            player.email_normalized = (player.email or '').strip().lower()

    @api.constrains('team_ids')
    def _check_single_team(self):
        for player in self:
            if len(player.team_ids) > 1:
                raise ValidationError(_('This player is already registered with another team.'))

    def write(self, vals):
        if 'team_ids' in vals:
            self.env.cr.execute('SELECT pg_advisory_xact_lock(72419022)')
            self.invalidate_recordset(['team_ids'])
            teams = self.mapped('team_ids')
            if teams and self.env['plazy.tournament.registration'].sudo().search_count([('team_id', 'in', teams.ids), ('state', '=', 'approved'), ('tournament_id.state', 'not in', ['completed', 'cancelled'])]):
                raise ValidationError(_('A registered competition roster is locked. Contact the administrator.'))
        return super().write(vals)
