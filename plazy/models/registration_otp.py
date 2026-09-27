import hashlib
import secrets
from datetime import timedelta

from odoo import _, fields, models, tools
from odoo.exceptions import ValidationError


class PlazyRegistrationOtp(models.Model):
    _name = 'plazy.registration.otp'
    _description = 'Plazy Registration Email OTP'
    _rec_name = 'email'

    email = fields.Char(required=True, index=True)
    account_type = fields.Selection([
        ('player', 'Player'),
        ('team', 'Team'),
        ('password_reset', 'Password Reset'),
    ], required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', ondelete='cascade', copy=False)
    code_hash = fields.Char(required=True, copy=False)
    otp_code = fields.Char(copy=False)
    access_token = fields.Char(copy=False, index=True)
    expires_at = fields.Datetime(required=True, copy=False)
    attempts = fields.Integer(default=0, copy=False)
    is_verified = fields.Boolean(default=False, copy=False)

    @classmethod
    def _sender_address(cls, env):
        """Use the administrator address for public registration messages."""
        administrator = env.ref('base.user_admin', raise_if_not_found=False).sudo()
        company = env.company.sudo()
        candidates = [
            administrator.email_formatted if administrator else False,
            administrator.email if administrator else False,
        ]

        # A public request runs as the public user, whose email is normally empty.
        # Fall back to the configured SMTP account when the administrator has not
        # yet been given an email address.
        mail_server = env['ir.mail_server'].sudo().search(
            [('active', '=', True)], order='sequence, id', limit=1,
        )
        candidates += [
            mail_server.smtp_user if mail_server else False,
            company.email_formatted,
            company.email,
        ]
        sender = next((value for value in candidates if tools.email_normalize(value)), False)
        if not sender:
            raise ValidationError(_(
                'Unable to send the verification code. Set an email address on the '
                'Administrator user or configure an outgoing mail server with an SMTP username.'
            ))
        return sender

    @classmethod
    def create_and_send(cls, env, email, account_type,
                        template_xmlid='plazy.mail_template_registration_otp', user_id=False):
        code = f'{secrets.randbelow(1_000_000):06d}'
        otp = env['plazy.registration.otp'].sudo().create({
            'email': email,
            'account_type': account_type,
            'user_id': user_id,
            'code_hash': hashlib.sha256(code.encode()).hexdigest(),
            'otp_code': code,
            'access_token': secrets.token_urlsafe(32),
            'expires_at': fields.Datetime.now() + timedelta(minutes=10),
        })
        sender = cls._sender_address(env)
        env.ref(template_xmlid).sudo().send_mail(
            otp.id,
            force_send=True,
            raise_exception=True,
            email_values={
                'email_from': sender,
                'reply_to': sender,
            },
        )
        otp.otp_code = False
        return otp

    def resend(self, template_xmlid='plazy.mail_template_registration_otp'):
        self.ensure_one()
        return self.create_and_send(
            self.env, self.email, self.account_type, template_xmlid, self.user_id.id,
        )

    def verify(self, code):
        self.ensure_one()
        if self.expires_at <= fields.Datetime.now():
            raise ValidationError('This verification code has expired. Request a new code to continue.')
        if self.attempts >= 5:
            raise ValidationError('Too many incorrect attempts. Request a new code to continue.')
        self.attempts += 1
        if hashlib.sha256((code or '').strip().encode()).hexdigest() != self.code_hash:
            raise ValidationError('The verification code is incorrect.')
        return True
