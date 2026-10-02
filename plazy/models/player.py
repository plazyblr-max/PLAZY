from odoo import fields, models


class PlazyPlayer(models.Model):
    _name = 'plazy.player'
    _description = 'Plazy Player'
    _rec_name = 'full_name'

    name = fields.Char(string='Name', required=True)
    full_name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email', required=True, index=True)
    mobile = fields.Char(string='Mobile Number', required=True)
    # Team managers only collect the essentials for an invitation. Players can
    # complete these profile details later through the normal player profile flow.
    age = fields.Integer(string='Age')
    locality = fields.Char(string='Bangalore Locality')
    pincode = fields.Char(string='PIN Code')
    user_id = fields.Many2one('res.users', string='User', ondelete='set null', copy=False)
    team_ids = fields.Many2many('plazy.team', 'plazy_player_team_rel', 'player_id', 'team_id', string='Teams', copy=False)
