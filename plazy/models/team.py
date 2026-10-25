import re

from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError, ValidationError


class PlazyTeam(models.Model):
    _name = 'plazy.team'
    _description = 'Plazy Team'

    name = fields.Char(string='Team Name', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    manager_name = fields.Char(string='Manager Name')
    email = fields.Char(string='Email', required=True, index=True)
    mobile = fields.Char(string='Mobile Number', required=True)
    locality = fields.Char(string='Bangalore Locality', required=True)
    pincode = fields.Char(string='PIN Code', required=True)
    team_type = fields.Selection([
        ('five_a_side', '5-a-side'),
        ('seven_a_side', '7-a-side'),
    ], string='Team Type', default='five_a_side', required=True)
    logo = fields.Image(string='Team Logo', max_width=512, max_height=512)
    registration_status = fields.Selection([
        ('onboarding', 'Onboarding'),
        ('inviting', 'Inviting Players'),
        ('eligible', 'Eligible for Approval'),
        ('waiting', 'Waiting for Plazy Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='onboarding', required=True, copy=False, index=True)
    rejection_reason = fields.Text(string='Rejection Reason', copy=False)
    approval_requested_at = fields.Datetime(string='Approval Request Date',
                                            copy=False)
    approved_at = fields.Datetime(string='Approved At', copy=False)
    user_id = fields.Many2one('res.users', string='User', ondelete='set null',
                              copy=False)
    player_ids = fields.Many2many('plazy.player', 'plazy_player_team_rel',
                                  'team_id', 'player_id', string='Players',
                                  copy=False)
    invitation_ids = fields.One2many('plazy.team.player.invitation', 'team_id',
                                     string='Player Invitations')
    joined_player_count = fields.Integer(compute='_compute_player_progress',
                                         string='Joined Players')
    required_player_count = fields.Integer(compute='_compute_player_progress',
                                           string='Required Players')
    player_invitation_count = fields.Integer(compute='_compute_player_progress',
                                             string='Invitations Sent')
    can_request_approval = fields.Boolean(compute='_compute_player_progress')
    maximum_player_count = fields.Integer(compute='_compute_player_progress')

    @api.depends('team_type', 'invitation_ids.status', 'player_ids.user_id', 'registration_status')
    def _compute_player_progress(self):
        for team in self:
            team.required_player_count = 8 if team.team_type == 'seven_a_side' else team.company_id.plazy_five_min
            team.maximum_player_count = 10 if team.team_type == 'seven_a_side' else team.company_id.plazy_five_max
            team.joined_player_count = len(team.player_ids.filtered('user_id'))
            team.player_invitation_count = len(team.player_ids) + len(team.invitation_ids.filtered(
                lambda invite: invite.status == 'sent' and invite.expires_at > fields.Datetime.now()))
            team.can_request_approval = (
                    team.joined_player_count >= team.required_player_count
                    and team.registration_status not in ('waiting', 'approved')
            )

    def _mail_sender(self):
        return self.env['plazy.registration.otp']._sender_address(self.env)

    def _send_template(self, template_xmlid):
        self.ensure_one()
        sender = self._mail_sender()
        self.env.ref(template_xmlid).sudo().send_mail(
            self.id, force_send=True, raise_exception=True,
            email_values={'email_from': sender, 'reply_to': sender,
                          'email_to': self.email},
        )

    def _refresh_registration_status(self):
        for team in self:
            if team.registration_status in ('waiting', 'approved', 'rejected'):
                continue
            team.registration_status = 'eligible' if team.joined_player_count >= team.required_player_count else 'inviting'

    def action_request_approval(self):
        for team in self:
            team._refresh_registration_status()
            if not team.can_request_approval:
                raise ValidationError(_(
                    'You need %(required)s joined players before requesting approval. You currently have %(joined)s.'
                ) % {'required': team.required_player_count,
                     'joined': team.joined_player_count})
            team.write({'registration_status': 'waiting',
                        'approval_requested_at': fields.Datetime.now(),
                        'rejection_reason': False})
            team._send_template('plazy.mail_template_team_approval_requested')
        return True

    def action_approve(self):
        if not self.env.su and not (self.env.user.has_group('base.group_system') or self.env.user.has_group('plazy.competition_admin')):
            raise AccessError(_('Only administrators can approve teams.'))
        for team in self:
            if team.registration_status != 'waiting' or team.joined_player_count < team.required_player_count:
                raise ValidationError(_('The team must be pending approval with an eligible roster.'))
            team.write({'registration_status': 'approved',
                        'approved_at': fields.Datetime.now(),
                        'rejection_reason': False})
            team._send_template('plazy.mail_template_team_approved')
        return True

    def action_reject(self):
        if not self.env.su and not (self.env.user.has_group('base.group_system') or self.env.user.has_group('plazy.competition_admin')):
            raise AccessError(_('Only administrators can reject teams.'))
        for team in self:
            if not (team.rejection_reason or '').strip():
                raise ValidationError(
                    _('Enter a rejection reason before rejecting this team.'))
            team.registration_status = 'rejected'
            team._send_template('plazy.mail_template_team_rejected')
        return True

    def _lock_roster(self):
        self.ensure_one()
        self.env.cr.execute('SELECT pg_advisory_xact_lock(72419022)')
        self.invalidate_recordset()

    @api.constrains('player_ids', 'team_type')
    def _check_membership(self):
        for team in self:
            team.player_ids._check_single_team()
            if len(team.player_ids) > team.maximum_player_count:
                raise ValidationError(_('This roster exceeds the team size limit.'))
            if any(p.company_id != team.company_id for p in team.player_ids):
                raise ValidationError(_('Team and players must belong to the same company.'))

    def _check_roster_space(self, invitation=False):
        self._lock_roster()
        if self.env['plazy.tournament.registration'].sudo().search_count([('team_id', '=', self.id), ('state', '=', 'approved'), ('tournament_id.state', 'not in', ['completed', 'cancelled'])]):
            raise ValidationError(_('This team has a locked competition roster.'))
        occupied = self.player_invitation_count
        if invitation and invitation.status == 'sent' and invitation.expires_at > fields.Datetime.now():
            occupied -= 1
        if occupied >= self.maximum_player_count:
            raise ValidationError(_('Your team has reached its player invitation limit.'))

    def write(self, vals):
        if {'registration_status', 'approved_at'}.intersection(vals) and not self.env.su and not (self.env.user.has_group('base.group_system') or self.env.user.has_group('plazy.competition_admin')):
            raise AccessError(_('Team approval is managed by administrators.'))
        if 'player_ids' in vals:
            for team in self:
                team._lock_roster()
                if self.env['plazy.tournament.registration'].sudo().search_count([('team_id', '=', team.id), ('state', '=', 'approved'), ('tournament_id.state', 'not in', ['completed', 'cancelled'])]):
                    raise ValidationError(_('The competition roster is locked. Contact the administrator.'))
        result = super().write(vals)
        if 'player_ids' in vals:
            self.mapped('player_ids')._check_single_team()
        return result

    @api.constrains('email', 'mobile', 'pincode')
    def _check_team_details(self):
        for team in self:
            if not tools.single_email_re.match(team.email or ''):
                raise ValidationError(_('Enter a valid email address.'))
            if not re.fullmatch(r'[6-9][0-9]{9}', team.mobile or ''):
                raise ValidationError(
                    _('Enter a valid 10-digit Indian mobile number.'))
            if not re.fullmatch(r'[0-9]{6}', team.pincode or ''):
                raise ValidationError(_('Enter a valid 6-digit PIN code.'))
