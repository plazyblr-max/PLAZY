from odoo import fields, models


class PlazyPlayer(models.Model):
    _name = 'plazy.player'
    _description = 'Plazy Player'
    _rec_name = 'full_name'

    name = fields.Char(string='Name', required=True)
    full_name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email', required=True, index=True)
    mobile = fields.Char(string='Mobile Number', required=True)
    age = fields.Integer(string='Age', required=True)
    locality = fields.Char(string='Bangalore Locality', required=True)
    pincode = fields.Char(string='PIN Code', required=True)
    user_id = fields.Many2one('res.users', string='User', ondelete='set null', copy=False)
