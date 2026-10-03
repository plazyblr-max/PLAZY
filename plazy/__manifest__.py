{
    'name': 'Plazy',
    'summary': 'Player and team registration for Plazy',
    'version': '20.0.3.0.2',
    'category': 'Authentication',
    'license': 'LGPL-3',
    'author': 'Plazy',
    'depends': ['web', 'mail', 'social_media'],
    'data': [
        'security/plazy_security.xml',
        'security/ir_access.xml',
        'data/plazy_otp_email_template.xml',
        'views/player_team_views.xml',
        'views/plazy_branding_templates.xml',
        'views/plazy_auth_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'plazy/static/src/js/plazy_auth.js',
            'plazy/static/src/scss/plazy_auth.scss',
        ],
    },
    'application': True,
    'installable': True,
}
