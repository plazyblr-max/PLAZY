from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    plazy_five_min = fields.Integer(string='5-a-side minimum roster', default=6, required=True)
    plazy_five_max = fields.Integer(string='5-a-side maximum roster', default=10, required=True)

    @api.constrains('plazy_five_min', 'plazy_five_max')
    def _check_plazy_roster(self):
        for company in self:
            if not 5 <= company.plazy_five_min <= company.plazy_five_max:
                raise ValidationError(_('The five-a-side roster minimum must be at least five and not exceed the maximum.'))

    social_whatsapp = fields.Char(
        string='WhatsApp Account',
        help='Full WhatsApp URL or a phone number including the country code.',
    )
