# app/routes/public.py
import os
from flask import Blueprint, render_template, abort
from app import db
from app.models import Group, Subscription, PricingPlan
from app.models.user import Creator
from sqlalchemy import func

bp = Blueprint('public', __name__, url_prefix='/c')


@bp.route('/<username>')
def creator_page(username):
    """Pagina publica do criador — perfil + grid de grupos"""
    creator = Creator.query.filter_by(
        username=username, is_active=True, is_blocked=False
    ).first_or_404()

    groups = Group.query.filter_by(
        creator_id=creator.id, is_active=True
    ).all()

    # Para cada grupo: menor preco e contagem de assinantes ativos
    for group in groups:
        group.subscriber_count = Subscription.query.filter_by(
            group_id=group.id, status='active'
        ).count()

        min_price = db.session.query(func.min(PricingPlan.price)).filter(
            PricingPlan.group_id == group.id,
            PricingPlan.is_active == True
        ).scalar()
        group.min_price = float(min_price) if min_price else None

    return render_template('public/creator_page.html',
                           creator=creator, groups=groups)


@bp.route('/<username>/<invite_slug>')
def group_landing(username, invite_slug):
    """Landing page de venda individual do grupo"""
    creator = Creator.query.filter_by(
        username=username, is_active=True, is_blocked=False
    ).first_or_404()

    group = Group.query.filter_by(
        invite_slug=invite_slug, creator_id=creator.id, is_active=True
    ).first_or_404()

    plans = PricingPlan.query.filter_by(
        group_id=group.id, is_active=True
    ).order_by(PricingPlan.price.asc()).all()

    subscriber_count = Subscription.query.filter_by(
        group_id=group.id, status='active'
    ).count()

    bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME', 'televipbra_bot')
    bot_link = f"https://t.me/{bot_username}?start=g_{invite_slug}"

    return render_template('public/group_landing.html',
                           creator=creator,
                           group=group,
                           plans=plans,
                           bot_link=bot_link,
                           subscriber_count=subscriber_count)
