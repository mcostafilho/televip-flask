"""
Context processors para disponibilizar variáveis em todos os templates
"""
from flask import current_app
from flask_login import current_user

def inject_global_vars():
    """Injeta variáveis globais em todos os templates"""
    return {
        'config': {
            'BOT_USERNAME': current_app.config.get('BOT_USERNAME', 'televipbra_bot'),
            'ADMIN_EMAILS': current_app.config.get('ADMIN_EMAILS', [])
        }
    }