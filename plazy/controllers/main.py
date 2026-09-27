import re

from odoo import _, fields, http, tools
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.web.controllers.home import ensure_db
from odoo.http.session import authenticate


class PlazyWebsite(http.Controller):

    @http.route('/', type='http', auth='public', website=True, sitemap=False)
    def plazy_public_home(self):
        ensure_db()
        return request.render('plazy.home')

    @http.route('/plazy/join', type='http', auth='public', website=True, sitemap=False)
    def join(self):
        ensure_db()
        return request.render('plazy.join_choice')

    @http.route('/plazy/player/join', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def player_join(self, **post):
        ensure_db()
        values = dict(post)
        if request.httprequest.method == 'POST':
            try:
                pending = self._pending_registration('player', self._player_values(post), post)
                self._start_email_verification(pending)
                return request.redirect('/plazy/verify-email')
            except ValidationError as error:
                values['error'] = error.args[0]
        return request.render('plazy.player_join', values)

    @http.route('/plazy/team/join', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def team_join(self, **post):
        ensure_db()
        values = dict(post)
        if request.httprequest.method == 'POST':
            try:
                pending = self._pending_registration('team', self._team_values(post), post)
                self._start_email_verification(pending)
                return request.redirect('/plazy/verify-email')
            except ValidationError as error:
                values['error'] = error.args[0]
        return request.render('plazy.team_join', values)

    @http.route('/plazy/verify-email', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def verify_email(self, **post):
        ensure_db()
        pending = request.session.get('plazy_registration_pending')
        if not pending:
            return request.redirect('/web/login')
        values = {'email': pending['email'], 'account_type': pending['account_type']}
        if request.httprequest.method == 'POST':
            try:
                otp = request.env['plazy.registration.otp'].sudo().browse(pending['otp_id']).exists()
                if not otp:
                    raise ValidationError(_('Your verification request is no longer available. Register again to continue.'))
                if post.get('action') == 'resend':
                    otp = otp.resend()
                    pending['otp_id'] = otp.id
                    request.session['plazy_registration_pending'] = pending
                    values['message'] = _('A new verification code has been sent.')
                else:
                    otp.verify(post.get('otp_code'))
                    with request.env.cr.savepoint():
                        if pending['account_type'] == 'player':
                            profile = request.env['plazy.player'].sudo().create(pending['values'])
                            profile.user_id = self._create_portal_user(
                                profile.full_name, profile.email, pending['password'], 'plazy.player',
                            )
                        else:
                            profile = request.env['plazy.team'].sudo().create(pending['values'])
                            profile.user_id = self._create_portal_user(
                                profile.name, profile.email, pending['password'], 'plazy.team',
                            )
                    otp.unlink()
                    request.session.pop('plazy_registration_pending', None)
                    authenticate(request.session, request.env, {
                        'login': pending['email'], 'password': pending['password'], 'type': 'password',
                    })
                    return request.redirect('/plazy/dashboard')
            except ValidationError as error:
                values['error'] = error.args[0]
        return request.render('plazy.otp_verify', values)

    @http.route('/plazy/forgot-password', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def forgot_password(self, **post):
        """Start a password reset without exposing the Odoo reset-password flow."""
        ensure_db()
        values = {'email': (post.get('email') or '').strip()}
        if request.httprequest.method == 'POST':
            try:
                email = values['email'].lower()
                if not tools.single_email_re.match(email):
                    raise ValidationError(_('Enter a valid registered email address.'))
                user = request.env['res.users'].sudo().search([
                    ('login', '=ilike', email), ('active', '=', True),
                ], limit=1)
                if not user:
                    raise ValidationError(_('No active account is registered with this email address.'))
                otp = request.env['plazy.registration.otp'].create_and_send(
                    request.env, email, 'password_reset',
                    'plazy.mail_template_password_reset_otp',
                    user.id,
                )
                request.session['plazy_password_reset'] = {
                    'email': email,
                    'otp_id': otp.id,
                    'user_id': user.id,
                    'verified': False,
                }
                return request.redirect('/plazy/forgot-password/verify')
            except ValidationError as error:
                values['error'] = error.args[0]
        return request.render('plazy.forgot_password', values)

    @http.route('/plazy/forgot-password/verify', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def verify_password_reset_otp(self, **post):
        ensure_db()
        pending = request.session.get('plazy_password_reset')
        if not pending:
            return request.redirect('/plazy/forgot-password')
        values = {'email': pending['email']}
        if request.httprequest.method == 'POST':
            try:
                otp = request.env['plazy.registration.otp'].sudo().browse(pending['otp_id']).exists()
                if not otp or otp.account_type != 'password_reset':
                    raise ValidationError(_('Your reset request is no longer available. Request a new code to continue.'))
                if post.get('action') == 'resend':
                    otp = otp.resend('plazy.mail_template_password_reset_otp')
                    pending['otp_id'] = otp.id
                    request.session['plazy_password_reset'] = pending
                    values['message'] = _('A new verification code has been sent.')
                else:
                    otp.verify(post.get('otp_code'))
                    otp.is_verified = True
                    pending['verified'] = True
                    request.session['plazy_password_reset'] = pending
                    return request.render('plazy.reset_password', {
                        'message': _('Email verified successfully. Choose your new password.'),
                        'reset_token': otp.access_token,
                    })
            except ValidationError as error:
                values['error'] = error.args[0]
        return request.render('plazy.password_reset_otp_verify', values)

    @http.route('/plazy/reset-password', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def reset_password(self, **post):
        ensure_db()
        reset_token = (post.get('reset_token') or '').strip()
        otp = request.env['plazy.registration.otp'].sudo().search([
            ('access_token', '=', reset_token),
            ('account_type', '=', 'password_reset'),
            ('is_verified', '=', True),
            ('expires_at', '>', fields.Datetime.now()),
        ], limit=1)
        if not otp:
            return request.redirect('/plazy/forgot-password')
        values = {'reset_token': reset_token}
        if request.httprequest.method == 'POST':
            try:
                password = self._registration_password(post)
                user = otp.user_id.exists()
                if not user or not user.active:
                    raise ValidationError(_('This account is no longer available. Request a new reset code.'))
                user.with_context(no_reset_password=True).write({'password': password})
                otp.unlink()
                request.session.pop('plazy_password_reset', None)
                return request.redirect('/web/login?reset_success=1')
            except ValidationError as error:
                values['error'] = error.args[0]
        return request.render('plazy.reset_password', values)

    @http.route('/plazy/password-reset-success', type='http', auth='public', website=True, sitemap=False)
    def password_reset_success(self):
        ensure_db()
        return request.redirect('/web/login?reset_success=1')

    @http.route('/plazy/dashboard', type='http', auth='user', website=True, sitemap=False)
    def dashboard(self):
        if request.env.user.has_group('base.group_system'):
            return request.redirect('/plazy/admin/choose')
        if request.env.user._is_internal():
            return request.redirect('/odoo')
        if request.env.user.has_group('plazy.player'):
            return request.redirect('/plazy/player/dashboard')
        if request.env.user.has_group('plazy.team'):
            return request.redirect('/plazy/team/dashboard')
        return request.redirect('/web/login_successful')

    @http.route('/plazy/login/redirect', type='http', auth='user', website=True, sitemap=False)
    def login_redirect(self):
        """Send every authenticated Odoo user to the right Plazy or Odoo area."""
        return self.dashboard()

    @http.route('/plazy/admin/choose', type='http', auth='user', website=True, sitemap=False)
    def admin_destination(self):
        if not request.env.user.has_group('base.group_system'):
            return request.not_found()
        return request.render('plazy.admin_destination', self._portal_values(request.env.user, 'admin'))

    @http.route('/plazy/admin/dashboard', type='http', auth='user', website=True, sitemap=False)
    def admin_dashboard(self):
        if not request.env.user.has_group('base.group_system'):
            return request.not_found()
        values = self._portal_values(request.env.user, 'admin')
        player_group = request.env.ref('plazy.player')
        team_group = request.env.ref('plazy.team')
        users = request.env['res.users'].sudo()
        values.update({
            'player_count': request.env['plazy.player'].sudo().search_count([]),
            'team_count': request.env['plazy.team'].sudo().search_count([]),
            'registered_user_count': users.search_count([
                '|', ('group_ids', 'in', player_group.ids), ('group_ids', 'in', team_group.ids),
            ]),
        })
        return request.render('plazy.admin_dashboard', values)

    @http.route('/plazy/player/dashboard', type='http', auth='user', website=True, sitemap=False)
    def player_dashboard(self):
        ensure_db()
        if not request.env.user.has_group('plazy.player'):
            return request.redirect('/plazy/dashboard')
        player = request.env['plazy.player'].sudo().search([('user_id', '=', request.env.user.id)], limit=1)
        if not player:
            return request.not_found()
        return request.render('plazy.player_dashboard', self._portal_values(player, 'player'))

    @http.route('/plazy/team/dashboard', type='http', auth='user', website=True, sitemap=False)
    def team_dashboard(self):
        ensure_db()
        if not request.env.user.has_group('plazy.team'):
            return request.redirect('/plazy/dashboard')
        team = request.env['plazy.team'].sudo().search([('user_id', '=', request.env.user.id)], limit=1)
        if not team:
            return request.not_found()
        return request.render('plazy.team_dashboard', self._portal_values(team, 'team'))

    @http.route('/plazy/signup', type='http', auth='public', website=True, sitemap=False)
    def legacy_signup(self, **_kwargs):
        return request.redirect('/')

    @http.route('/plazy', type='http', auth='public', website=True, sitemap=False)
    def plazy_home(self):
        return self.plazy_public_home()

    @staticmethod
    def _create_portal_user(name, email, password, group_xmlid):
        users = request.env['res.users'].sudo()
        if users.search_count([('login', '=ilike', email)]):
            raise ValidationError(_('An account already exists for this email address.'))
        group = request.env.ref(group_xmlid).sudo()
        company = request.env.company
        return users.with_context(no_reset_password=True).create({
            'name': name,
            'login': email,
            'email': email,
            'password': password,
            'group_ids': [(6, 0, [group.id])],
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
        })

    @staticmethod
    def _pending_registration(account_type, values, post):
        email = values.get('email') or ''
        if not tools.single_email_re.match(email):
            raise ValidationError(_('Enter a valid email address before requesting a verification code.'))
        if request.env['res.users'].sudo().search_count([('login', '=ilike', email)]):
            raise ValidationError(_('An account already exists for this email address.'))
        return {
            'account_type': account_type,
            'email': email,
            'values': values,
            'password': PlazyWebsite._registration_password(post),
        }

    @staticmethod
    def _start_email_verification(pending):
        otp = request.env['plazy.registration.otp'].create_and_send(
            request.env, pending['email'], pending['account_type'],
        )
        pending['otp_id'] = otp.id
        request.session['plazy_registration_pending'] = pending

    @staticmethod
    def _portal_values(profile, portal_type):
        company = request.env.company
        whatsapp_value = (company.social_whatsapp or company.phone or '').strip()
        if whatsapp_value and not whatsapp_value.startswith(('http://', 'https://')):
            whatsapp_value = re.sub(r'[^0-9]', '', whatsapp_value)
            whatsapp_value = f'https://wa.me/{whatsapp_value}' if whatsapp_value else ''
        user_name = (request.env.user.name or '').strip()
        return {
            portal_type: profile,
            'portal_type': portal_type,
            'company': company,
            'instagram_url': company.social_instagram or '',
            'whatsapp_url': whatsapp_value,
            'user_first_name': user_name.split()[0] if user_name else _('Player'),
        }

    @staticmethod
    def _registration_password(post):
        password = post.get('password') or ''
        if len(password) < 8:
            raise ValidationError(_('Password must contain at least 8 characters.'))
        if password != (post.get('confirm_password') or ''):
            raise ValidationError(_('Passwords do not match.'))
        return password

    @staticmethod
    def _player_values(post):
        return {
            'name': (post.get('name') or '').strip(),
            'full_name': (post.get('full_name') or '').strip(),
            'email': (post.get('email') or '').strip().lower(),
            'mobile': (post.get('mobile') or '').strip(),
            'age': int(post['age']) if (post.get('age') or '').isdigit() else 0,
            'locality': (post.get('locality') or '').strip(),
            'pincode': (post.get('pincode') or '').strip(),
        }

    @staticmethod
    def _team_values(post):
        return {
            'name': (post.get('name') or '').strip(),
            'email': (post.get('email') or '').strip().lower(),
            'mobile': (post.get('mobile') or '').strip(),
            'locality': (post.get('locality') or '').strip(),
            'pincode': (post.get('pincode') or '').strip(),
        }
