import re

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class PlazyTeam(models.Model):
    _name = 'plazy.team'
    _description = 'Plazy Team'

    name = fields.Char(string='Team Name', required=True)
    email = fields.Char(string='Email', required=True, index=True)
    mobile = fields.Char(string='Mobile Number', required=True)
    locality = fields.Char(string='Bangalore Locality', required=True)
    pincode = fields.Char(string='PIN Code', required=True)
    user_id = fields.Many2one('res.users', string='User', ondelete='set null', copy=False)

    @api.constrains('email', 'mobile', 'pincode')
    def _check_team_details(self):
        for team in self:
            if not tools.single_email_re.match(team.email or ''):
                raise ValidationError(_('Enter a valid email address.'))
            if not re.fullmatch(r'[6-9][0-9]{9}', team.mobile or ''):
                raise ValidationError(_('Enter a valid 10-digit Indian mobile number.'))
            if not re.fullmatch(r'[0-9]{6}', team.pincode or ''):
                raise ValidationError(_('Enter a valid 6-digit PIN code.'))
