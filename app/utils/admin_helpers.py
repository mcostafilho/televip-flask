from flask import session
from flask_login import current_user


def get_effective_creator():
    """Return the creator being viewed by admin, or current_user."""
    if current_user.is_admin and session.get('admin_viewing_id'):
        from app.models.user import Creator
        creator = Creator.query.get(session['admin_viewing_id'])
        if creator:
            return creator
    return current_user


def is_admin_viewing():
    """Return True if admin is viewing another creator's data."""
    return current_user.is_admin and bool(session.get('admin_viewing_id'))
