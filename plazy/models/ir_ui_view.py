from odoo import fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    # The upgraded Plazy database already has this required legacy column.
    # Keep its type aligned with Website's page visibility field.
    visibility = fields.Selection(
        [
            ('public', 'Public'),
            ('connected', 'Signed In'),
            ('restricted_group', 'Restricted Group'),
            ('password', 'With Password'),
        ],
        default='public',
        required=True,
    )
