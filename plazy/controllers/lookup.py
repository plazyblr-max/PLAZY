from time import time


def allow_player_lookup(session):
    now = time()
    checks = [stamp for stamp in session.get('plazy_email_checks', []) if stamp > now - 60]
    if len(checks) >= 30:
        return False
    session['plazy_email_checks'] = checks + [now]
    return True
