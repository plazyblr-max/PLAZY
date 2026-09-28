from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    social_whatsapp = fields.Char(
        string='WhatsApp Account',
        help='Full WhatsApp URL or a phone number including the country code.',
    )
