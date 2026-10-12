from unittest.mock import patch
from urllib.parse import urlencode

from lxml import html

from odoo import tools
from odoo.tests import HttpCase, tagged


@tagged('-at_install', 'post_install')
class TestOnboarding(HttpCase):
    """Exercise the real POST routes with mail delivery mocked, never external SMTP."""

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)
        self.startPatcher(patch.object(self.env.registry['mail.template'], 'send_mail', return_value=False))
        self.startPatcher(patch.object(
            self.env.registry['plazy.registration.otp'], '_sender_address',
            return_value='onboarding@example.invalid',
        ))
        self.startPatcher(patch(
            'odoo.addons.plazy.models.registration_otp.secrets.randbelow', return_value=123456,
        ))

    def post_form(self, path, data, page=None, files=None):
        page = page or self.url_open(path)
        self.assertEqual(page.status_code, 200)
        token = html.fromstring(page.content).xpath('//input[@name="csrf_token"]/@value')[0]
        response = self.url_open(path, data={**data, 'csrf_token': token}, files=files)
        self.assertEqual(response.status_code, 200)
        return response

    def register(self, role, logo=None, **extra):
        data = {
            'name': 'Onboarding Test Squad', 'full_name': 'Onboarding Test Player',
            'manager_name': 'Test Manager', 'mobile': '9876543210',
            'email': role + '-onboarding@example.invalid', 'locality': 'Indiranagar',
            'pincode': '560038', 'age': '24', 'position': 'MID',
            'team_type': 'five_a_side', 'password': 'Onboarding-test-123',
            'confirm_password': 'Onboarding-test-123', **extra,
        }
        page = self.post_form('/plazy/' + role + '/join', data, files={'logo': logo} if logo else None)
        self.assertIn('/plazy/verify-email', page.url)
        model = 'plazy.team' if role == 'team' else 'plazy.player'
        self.assertFalse(self.env[model].search([('email', '=', data['email'])]))
        page = self.post_form('/plazy/verify-email', {'otp_code': '123456', 'action': 'verify'}, page)
        self.assertIn('/plazy/' + role + '/dashboard', page.url)
        self.assertIn('WELCOME TO PLAZY', page.text)
        profile = self.env[model].search([('email', '=', data['email'])])
        self.assertTrue(profile.user_id)
        return profile, page

    def test_team_registration_invitation_and_join(self):
        with tools.file_open('plazy/static/src/img/plazy-touch-icon.png', 'rb') as image:
            team, dashboard = self.register('team', logo=('team.png', image.read(), 'image/png'))
        self.assertTrue(team.logo)
        self.assertIn('data-onboarding="invite"', dashboard.text)
        self.assertFalse(team.can_request_approval)
        tokens = []

        def capture_invitation(invitation, token):
            tokens.append(token)

        with patch.object(self.env.registry['plazy.team.player.invitation'], '_send', capture_invitation):
            dashboard = self.post_form('/plazy/team/players/invite', {
                'player_name': 'Invited Player', 'email': 'invited-onboarding@example.invalid',
                'mobile': '9876543211', 'position': 'GK',
            }, dashboard)
        self.assertIn('Invitation sent', dashboard.text)
        invitation = self.env['plazy.team.player.invitation'].search([('team_id', '=', team.id)])
        self.assertEqual(invitation.position, 'GK')
        self.assertEqual(invitation.status, 'sent')
        self.assertNotIn(team, invitation.player_id.team_ids)
        self.authenticate(None, None)
        url = '/plazy/player/invitation?' + urlencode({'token': tokens[0]})
        page = self.url_open(url)
        self.assertIn('data-onboarding="accept"', page.text)
        page = self.post_form('/plazy/player/invitation', {'token': tokens[0], 'action': 'continue'}, page)
        self.assertIn('/plazy/player/invitation/set-password', page.url)
        page = self.post_form('/plazy/player/invitation/set-password', {
            'token': tokens[0], 'password': 'Invited-player-123', 'confirm_password': 'Invited-player-123',
        }, page)
        self.assertIn('/plazy/player/dashboard', page.url)
        self.assertIn('Invitation accepted', page.text)
        invitation.invalidate_recordset()
        team.invalidate_recordset()
        self.assertEqual(invitation.status, 'joined')
        self.assertIn(team, invitation.player_id.team_ids)
        self.assertEqual(team.joined_player_count, 1)
        self.assertFalse(team.can_request_approval)
        self.assertIn('Invalid or Expired', self.url_open(url).text)

    def test_player_registration_position_and_no_js_name(self):
        player, _page = self.register('player', name='', full_name='Full Name Player', position='Winger')
        self.assertEqual(player.name, 'Full Name Player')
        self.assertEqual(player.position, 'Winger')
        self.assertTrue(player.user_id.has_group('plazy.player'))

    def test_password_error_and_resend(self):
        page = self.post_form('/plazy/player/join', {
            'name': 'Mismatch', 'full_name': 'Mismatch', 'email': 'mismatch@example.invalid',
            'password': 'Strong-pass-123', 'confirm_password': 'Different-pass-123',
        })
        self.assertIn('Passwords do not match', page.text)
        self.assertNotIn('/plazy/verify-email', page.url)
        page = self.post_form('/plazy/player/join', {
            'name': 'Resend', 'full_name': 'Resend', 'email': 'resend@example.invalid',
            'mobile': '9876543210', 'password': 'Strong-pass-123', 'confirm_password': 'Strong-pass-123',
        })
        self.assertIn('/plazy/verify-email', page.url)
        page = self.post_form('/plazy/verify-email', {'action': 'resend'}, page)
        self.assertIn('A new verification code has been sent', page.text)

    def test_login_preserves_invitation_redirect(self):
        destination = '/plazy/player/invitation?token=example-test-token'
        page = self.url_open('/web/login?' + urlencode({'redirect': destination}))
        redirect = html.fromstring(page.content).xpath('//input[@name="redirect"]/@value')
        self.assertEqual(redirect, [destination])

    def test_invalid_logo_is_reported_before_verification(self):
        page = self.post_form('/plazy/team/join', {
            'name': 'Invalid Logo Team', 'email': 'bad-logo@example.invalid',
            'password': 'Strong-pass-123', 'confirm_password': 'Strong-pass-123',
        }, files={'logo': ('team.png', b'not an image', 'image/png')})
        self.assertIn('This logo could not be opened', page.text)
        self.assertNotIn('/plazy/verify-email', page.url)
