import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError


class PlazyTeamPlayerInvitation(models.Model):
    _name = 'plazy.team.player.invitation'
    _description = 'Plazy Team Player Invitation'
    _rec_name = 'email'
    _order = 'create_date desc, id desc'

    team_id = fields.Many2one('plazy.team', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, ondelete='cascade')
    player_id = fields.Many2one('plazy.player', ondelete='set null', copy=False)
    existing_user_id = fields.Many2one('res.users', ondelete='set null', copy=False)
    player_name = fields.Char(required=True)
    email = fields.Char(required=True, index=True)
    mobile = fields.Char(required=True)
    position = fields.Char()
    status = fields.Selection([
        ('sent', 'Invitation Sent'),
        ('accepted', 'Accepted'),
        ('joined', 'Joined'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], required=True, default='sent', index=True, copy=False)
    token_hash = fields.Char(required=True, index=True, copy=False)
    email_token = fields.Char(copy=False, groups='base.group_system')
    expires_at = fields.Datetime(required=True, copy=False)
    accepted_at = fields.Datetime(copy=False)

    _token_hash_unique = models.Constraint(
        'unique(token_hash)', 'Invitation token must be unique.',
    )

    @api.constrains('email')
    def _check_email(self):
        for invitation in self:
            if not tools.single_email_re.match((invitation.email or '').strip()):
                raise ValidationError(_('Enter a valid email address.'))

    @classmethod
    def _token_hash(cls, token):
        return hashlib.sha256((token or '').encode()).hexdigest()

    @classmethod
    def _sender_address(cls, env):
        # Reuse the registration sender resolution so public and team mail share configuration.
        return env['plazy.registration.otp']._sender_address(env)

    @classmethod
    def validate_email_for_team(cls, env, team, email):
        email = (email or '').strip().lower()
        result = {'valid': False, 'email': email, 'existing_player': False, 'message': ''}
        if not tools.single_email_re.match(email):
            result['message'] = _('Enter a valid email address.')
            return result
        player = env['plazy.player'].sudo().search([('email', '=ilike', email)], limit=1)
        user = env['res.users'].sudo().search([('login', '=ilike', email)], limit=1)
        if player and team in player.team_ids:
            result['message'] = _('This player already belongs to your team.')
            return result
        invitation = env['plazy.team.player.invitation'].sudo().search([
            ('team_id', '=', team.id), ('email', '=ilike', email), ('status', '=', 'sent'),
        ], limit=1)
        if invitation:
            invitation._expire_if_needed()
            if invitation.status == 'sent':
                result['message'] = _('There is already a pending invitation for this email.')
                return result
        result.update({
            'valid': True,
            'existing_player': bool(player or user),
            'message': _(
                'Existing Plazy player found. They will be asked to log in and accept the invitation.'
            ) if (player or user) else _('Email is available for a new player invitation.'),
        })
        return result

    @classmethod
    def create_and_send(cls, env, team, values):
        validation = cls.validate_email_for_team(env, team, values.get('email'))
        if not validation['valid']:
            raise ValidationError(validation['message'])
        email = validation['email']
        player = env['plazy.player'].sudo().search([('email', '=ilike', email)], limit=1)
        user = env['res.users'].sudo().search([('login', '=ilike', email)], limit=1)
        if not player:
            # Keep the manager-entered details as a pending player profile. It is
            # deliberately not linked to the team until the invitation is accepted.
            player = env['plazy.player'].sudo().create({
                'name': (values.get('player_name') or '').strip(),
                'full_name': (values.get('player_name') or '').strip(),
                'email': email,
                'mobile': (values.get('mobile') or '').strip(),
                'user_id': user.id,
            })
        token = secrets.token_urlsafe(32)
        invitation = env['plazy.team.player.invitation'].sudo().create({
            'team_id': team.id,
            'player_id': player.id,
            'existing_user_id': user.id,
            'player_name': (values.get('player_name') or '').strip(),
            'email': email,
            'mobile': (values.get('mobile') or '').strip(),
            'position': (values.get('position') or '').strip(),
            'token_hash': cls._token_hash(token),
            'email_token': token,
            'expires_at': fields.Datetime.now() + timedelta(days=7),
        })
        try:
            invitation._send(token)
        except Exception:
            invitation.status = 'failed'
            raise
        team._refresh_registration_status()
        return invitation

    def _send(self, token):
        self.ensure_one()
        sender = self._sender_address(self.env)
        self.env.ref('plazy.mail_template_team_player_invitation').sudo().with_context(invitation_token=token).send_mail(
            self.id, force_send=True, raise_exception=True,
            # Explicitly set the recipient: the Plazy administrator is the sender,
            # never the person receiving the team invitation.
            email_values={'email_from': sender, 'reply_to': sender, 'email_to': self.email},
        )
        # Odoo renders mail records in a fresh environment, so context alone is
        # insufficient. Clear this transient token immediately after rendering;
        # server validation always uses token_hash.
        self.email_token = False
        return token

    def invitation_url(self, token):
        self.ensure_one()
        # Odoo 20 exposes typed system-parameter accessors; get_param was removed.
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url')
        return '%s/plazy/player/invitation?token=%s' % (base_url.rstrip('/'), token)

    def get_invitation_url(self):
        """Expose the ephemeral token to the mail template, never as a stored field."""
        return self.invitation_url(self.env.context.get('invitation_token') or self.email_token)

    def _expire_if_needed(self):
        for invitation in self.filtered(lambda item: item.status == 'sent' and item.expires_at <= fields.Datetime.now()):
            invitation.status = 'expired'

    @classmethod
    def from_token(cls, env, token):
        invitation = env['plazy.team.player.invitation'].sudo().search([
            ('token_hash', '=', cls._token_hash(token)),
        ], limit=1)
        if invitation:
            invitation._expire_if_needed()
        return invitation

    def is_usable(self):
        self.ensure_one()
        self._expire_if_needed()
        return self.status == 'sent' and bool(self.team_id) and bool(self.email)

    def resend(self):
        self.ensure_one()
        if self.status not in ('sent', 'expired', 'failed'):
            raise ValidationError(_('Only sent, expired, or failed invitations can be resent.'))
        token = secrets.token_urlsafe(32)
        self.write({
            'status': 'sent',
            'token_hash': self._token_hash(token),
            'email_token': token,
            'expires_at': fields.Datetime.now() + timedelta(days=7),
            'accepted_at': False,
        })
        self._send(token)

    def accept(self, password=False):
        self.ensure_one()
        if not self.is_usable():
            raise ValidationError(_('This invitation is invalid, expired, cancelled, or has already been used.'))
        users = self.env['res.users'].sudo()
        user = self.existing_user_id.exists() or users.search([('login', '=ilike', self.email)], limit=1)
        player = self.player_id.exists() or self.env['plazy.player'].sudo().search([('email', '=ilike', self.email)], limit=1)
        if not user:
            if not password:
                raise ValidationError(_('Choose a password to finish registration.'))
            user = users.with_context(no_reset_password=True).create({
                'name': self.player_name,
                'login': self.email,
                'email': self.email,
                'password': password,
                'group_ids': [(6, 0, [self.env.ref('plazy.player').id])],
                'company_id': self.env.company.id,
                'company_ids': [(6, 0, [self.env.company.id])],
            })
        if not player:
            player = self.env['plazy.player'].sudo().create({
                'name': self.player_name,
                'full_name': self.player_name,
                'email': self.email,
                'mobile': self.mobile,
                'age': 0,
                'locality': '',
                'pincode': '',
                'user_id': user.id,
            })
        elif not player.user_id:
            player.user_id = user
        if not user.has_group('plazy.player'):
            user.write({'group_ids': [(4, self.env.ref('plazy.player').id)]})
        player.write({'team_ids': [(4, self.team_id.id)]})
        self.write({
            'player_id': player.id,
            'existing_user_id': user.id,
            'status': 'accepted',
            'accepted_at': fields.Datetime.now(),
        })
        return user

    def mark_joined(self):
        for invitation in self:
            if invitation.status == 'accepted':
                invitation.status = 'joined'
                invitation.team_id._refresh_registration_status()
        return True
