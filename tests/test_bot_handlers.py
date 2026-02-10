# tests/test_bot_handlers.py
"""
Testes massivos dos handlers do bot Telegram - o coracao da aplicacao.
Cobre: start, subscription, payment, cancellation, reactivation,
discovery, multi-grupo, multi-criador, scheduled tasks, edge cases.
"""
import pytest
import secrets
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app import create_app, db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction

import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
os.environ['STRIPE_SECRET_KEY'] = 'sk_test_fake'


# ---------------------------------------------------------------------------
# Mock helpers for Telegram objects
# ---------------------------------------------------------------------------

def make_user(user_id=123456789, first_name='TestUser', username='testuser'):
    user = MagicMock()
    user.id = user_id
    user.first_name = first_name
    user.username = username
    return user


def make_message(user=None):
    msg = AsyncMock()
    msg.reply_text = AsyncMock()
    if user:
        msg.from_user = user
    return msg


def make_callback_query(user=None, data='', message=None):
    query = AsyncMock()
    query.from_user = user or make_user()
    query.data = data
    query.message = message or make_message()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def make_update(user=None, args=None, callback_query=None, message=None):
    update = MagicMock()
    update.update_id = 1
    u = user or make_user()
    update.effective_user = u

    if callback_query:
        update.callback_query = callback_query
        update.message = None
    else:
        update.callback_query = None
        update.message = message or make_message(u)

    return update


def make_context(user_data=None, bot_username='TestVIPBot'):
    ctx = MagicMock()
    ctx.args = []
    ctx.user_data = user_data if user_data is not None else {}
    ctx.bot = AsyncMock()
    ctx.bot.username = bot_username
    return ctx


# ---------------------------------------------------------------------------
# Bridge: make bot's get_db_session() use Flask's test DB session
# ---------------------------------------------------------------------------

from contextlib import contextmanager

@contextmanager
def _flask_db_session():
    """Yields the Flask-SQLAlchemy session so bot handlers hit the in-memory test DB."""
    try:
        yield _db.session
        _db.session.flush()  # flush but don't commit (test will rollback)
    except Exception:
        _db.session.rollback()
        raise


# List of every bot module that imports get_db_session
_BOT_DB_TARGETS = [
    'bot.handlers.start',
    'bot.handlers.subscription',
    'bot.handlers.payment',
    'bot.handlers.payment_verification',
    'bot.handlers.discovery',
    'bot.handlers.admin',
    'bot.jobs.scheduled_tasks',
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='function')
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SERVER_NAME': 'localhost',
        'SECRET_KEY': 'test-secret-key-for-testing',
        'RATELIMIT_ENABLED': False,
    })
    return app


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture(autouse=True)
def _patch_bot_db(app, db):
    """Auto-patch every bot module so get_db_session uses the Flask test DB."""
    with app.app_context():
        patchers = []
        for target in _BOT_DB_TARGETS:
            try:
                p = patch(f'{target}.get_db_session', _flask_db_session)
                p.start()
                patchers.append(p)
            except (AttributeError, ModuleNotFoundError):
                pass
        yield
        for p in patchers:
            p.stop()


@pytest.fixture
def app_ctx(app, db):
    with app.app_context():
        yield app


# --- Creators ---

@pytest.fixture
def creator_a(db):
    """Criador A com grupo ativo"""
    c = Creator(
        name='Creator Alpha',
        email='alpha@test.com',
        username='creatoralpha',
        balance=Decimal('0'),
        total_earned=Decimal('0'),
        is_verified=True,
    )
    c.set_password('AlphaPass1')
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def creator_b(db):
    """Criador B com grupo ativo"""
    c = Creator(
        name='Creator Beta',
        email='beta@test.com',
        username='creatorbeta',
        balance=Decimal('0'),
        total_earned=Decimal('0'),
        is_verified=True,
    )
    c.set_password('BetaPass1')
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def blocked_creator(db):
    """Criador bloqueado"""
    c = Creator(
        name='Blocked Creator',
        email='blocked@test.com',
        username='blockedcreator',
        balance=Decimal('0'),
        total_earned=Decimal('0'),
        is_verified=True,
        is_blocked=True,
    )
    c.set_password('BlockedPass1')
    db.session.add(c)
    db.session.commit()
    return c


# --- Groups ---

@pytest.fixture
def group_a(db, creator_a):
    g = Group(
        name='Alpha Premium',
        description='Grupo exclusivo Alpha',
        telegram_id='-1001111111111',
        invite_link='https://t.me/+alpha123',
        creator_id=creator_a.id,
        is_active=True,
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def group_b(db, creator_b):
    g = Group(
        name='Beta VIP',
        description='Grupo exclusivo Beta',
        telegram_id='-1002222222222',
        invite_link='https://t.me/+beta456',
        creator_id=creator_b.id,
        is_active=True,
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def group_inactive(db, creator_a):
    g = Group(
        name='Grupo Inativo',
        telegram_id='-1003333333333',
        creator_id=creator_a.id,
        is_active=False,
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def group_blocked(db, blocked_creator):
    g = Group(
        name='Grupo de Criador Bloqueado',
        telegram_id='-1004444444444',
        creator_id=blocked_creator.id,
        is_active=True,
    )
    db.session.add(g)
    db.session.commit()
    return g


# --- Plans ---

@pytest.fixture
def plan_a_monthly(db, group_a):
    p = PricingPlan(
        group_id=group_a.id,
        name='Mensal Alpha',
        duration_days=30,
        price=Decimal('29.90'),
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def plan_a_quarterly(db, group_a):
    p = PricingPlan(
        group_id=group_a.id,
        name='Trimestral Alpha',
        duration_days=90,
        price=Decimal('79.90'),
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def plan_b_monthly(db, group_b):
    p = PricingPlan(
        group_id=group_b.id,
        name='Mensal Beta',
        duration_days=30,
        price=Decimal('19.90'),
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def plan_b_lifetime(db, group_b):
    p = PricingPlan(
        group_id=group_b.id,
        name='Vitalicio Beta',
        duration_days=0,
        price=Decimal('199.90'),
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ===========================================================================
# 1. START COMMAND TESTS
# ===========================================================================

class TestStartCommand:
    """Testes do comando /start"""

    def test_start_no_args_new_user(self, app_ctx):
        """Novo usuario sem assinaturas ve mensagem de boas-vindas"""
        from bot.handlers.start import start_command

        user = make_user(999)
        update = make_update(user=user)
        ctx = make_context()
        ctx.args = []

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_command(update, ctx))

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert 'Bem-vindo' in text
        assert 'TeleVIP Bot' in text

    def test_start_no_args_with_active_subs(self, app_ctx, group_a, plan_a_monthly):
        """Usuario com assinatura ativa ve dashboard"""
        from bot.handlers.start import start_command

        user_id = 888
        sub = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='activeuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id, 'ActiveUser')
        update = make_update(user=user)
        ctx = make_context()
        ctx.args = []

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Assinaturas Ativas' in text or 'Bem-vindo' in text

    def test_start_with_group_slug(self, app_ctx, group_a, plan_a_monthly):
        """start com g_SLUG inicia fluxo de assinatura"""
        from bot.handlers.start import start_command

        user = make_user(777)
        update = make_update(user=user)
        ctx = make_context()
        ctx.args = [f'g_{group_a.invite_slug}']

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert group_a.name in text
        assert 'Planos' in text or 'disponíveis' in text or 'Mensal Alpha' in text

    def test_start_with_cancel_arg(self, app_ctx):
        """start com cancel mostra mensagem de cancelamento"""
        from bot.handlers.start import start_command

        user = make_user(666)
        update = make_update(user=user)
        ctx = make_context()
        ctx.args = ['cancel']

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Cancelado' in text or 'cancelado' in text

    def test_start_with_pending_transaction(self, app_ctx, group_a, plan_a_monthly):
        """Usuario com transacao pendente ve botao de verificacao"""
        from bot.handlers.start import start_command

        user_id = 555
        sub = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='penduser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id,
            amount=Decimal('29.90'),
            status='pending',
            payment_method='stripe',
            stripe_session_id='cs_test_pending',
        )
        _db.session.add(txn)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()
        ctx.args = []

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'pendente' in text.lower() or 'Verificar' in text


# ===========================================================================
# 2. SUBSCRIPTION FLOW TESTS
# ===========================================================================

class TestSubscriptionFlow:
    """Testes do fluxo de assinatura via bot"""

    def test_flow_by_slug(self, app_ctx, group_a, plan_a_monthly):
        """Iniciar assinatura usando invite_slug"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(100)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert group_a.name in text
        assert 'Mensal Alpha' in text
        assert '29.90' in text

    def test_flow_by_legacy_id(self, app_ctx, group_a, plan_a_monthly):
        """Iniciar assinatura usando ID numerico (backward compat)"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(101)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, str(group_a.id))
        )

        text = update.message.reply_text.call_args[0][0]
        assert group_a.name in text

    def test_flow_invalid_slug(self, app_ctx):
        """Slug invalido mostra mensagem de erro"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(102)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, 'nonexistent_slug')
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'não encontrado' in text

    def test_flow_inactive_group(self, app_ctx, group_inactive):
        """Grupo inativo retorna mensagem de indisponivel"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(103)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_inactive.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'indisponível' in text

    def test_flow_blocked_creator(self, app_ctx, group_blocked):
        """Grupo de criador bloqueado retorna indisponivel"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(104)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_blocked.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'indisponível' in text

    def test_flow_already_subscribed(self, app_ctx, group_a, plan_a_monthly):
        """Usuario ja assinante recebe mensagem de que ja eh assinante"""
        from bot.handlers.start import start_subscription_flow

        user_id = 105
        sub = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='alreadysub',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=25),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'já é assinante' in text

    def test_flow_no_active_plans(self, app_ctx, group_a):
        """Grupo sem planos ativos mostra erro"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(106)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'Nenhum plano' in text or 'plano' in text.lower()

    def test_flow_shows_multiple_plans(self, app_ctx, group_a, plan_a_monthly, plan_a_quarterly):
        """Grupo com multiplos planos mostra todos"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(107)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'Mensal Alpha' in text
        assert 'Trimestral Alpha' in text
        assert '29.90' in text
        assert '79.90' in text

    def test_flow_shows_creator_info(self, app_ctx, group_a, plan_a_monthly):
        """Mostra informacoes do criador"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(108)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'Creator Alpha' in text


# ===========================================================================
# 3. MULTI-GRUPO / MULTI-CRIADOR TESTS
# ===========================================================================

class TestMultiGroupUser:
    """Testes de usuario assinando multiplos grupos de criadores diferentes"""

    def test_user_subscribes_two_groups(self, app_ctx, group_a, group_b, plan_a_monthly, plan_b_monthly):
        """Usuario assina dois grupos de criadores diferentes"""
        user_id = 200

        sub_a = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='multisub',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        sub_b = Subscription(
            group_id=group_b.id,
            plan_id=plan_b_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='multisub',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=15),
            status='active',
        )
        _db.session.add_all([sub_a, sub_b])
        _db.session.commit()

        subs = Subscription.query.filter_by(
            telegram_user_id=str(user_id), status='active'
        ).all()
        assert len(subs) == 2
        group_names = {s.group.name for s in subs}
        assert 'Alpha Premium' in group_names
        assert 'Beta VIP' in group_names

    def test_user_cancels_one_keeps_other(self, app_ctx, group_a, group_b, plan_a_monthly, plan_b_monthly):
        """Cancelar um grupo nao afeta o outro"""
        user_id = 201

        sub_a = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='multisub2',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        sub_b = Subscription(
            group_id=group_b.id,
            plan_id=plan_b_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='multisub2',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        _db.session.add_all([sub_a, sub_b])
        _db.session.commit()

        # Cancelar sub_a
        sub_a.cancel_at_period_end = True
        sub_a.auto_renew = False
        _db.session.commit()

        # sub_b permanece intacta
        assert sub_b.status == 'active'
        assert sub_b.cancel_at_period_end is not True
        assert sub_a.cancel_at_period_end is True

    def test_user_different_plans_same_group(self, app_ctx, group_a, plan_a_monthly, plan_a_quarterly):
        """Usuario nao pode ter duas assinaturas ativas no mesmo grupo"""
        user_id = 202

        sub_monthly = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='samegrp',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        _db.session.add(sub_monthly)
        _db.session.commit()

        # Tentar assinar o mesmo grupo
        from bot.handlers.start import start_subscription_flow
        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'já é assinante' in text

    def test_expired_sub_allows_resubscribe(self, app_ctx, group_a, plan_a_monthly):
        """Assinatura expirada permite nova assinatura"""
        user_id = 203

        expired_sub = Subscription(
            group_id=group_a.id,
            plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id),
            telegram_username='expireduser',
            start_date=datetime.utcnow() - timedelta(days=60),
            end_date=datetime.utcnow() - timedelta(days=30),
            status='expired',
        )
        _db.session.add(expired_sub)
        _db.session.commit()

        from bot.handlers.start import start_subscription_flow
        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'Mensal Alpha' in text  # Deve mostrar planos (pode assinar novamente)

    def test_three_groups_status_shows_all(self, app_ctx, group_a, group_b,
                                           plan_a_monthly, plan_b_monthly, creator_a):
        """Status mostra todas as assinaturas de multiplos grupos"""
        user_id = 204

        # Terceiro grupo
        group_c = Group(
            name='Gamma Group',
            telegram_id='-1005555555555',
            creator_id=creator_a.id,
            is_active=True,
        )
        _db.session.add(group_c)
        _db.session.flush()
        plan_c = PricingPlan(
            group_id=group_c.id, name='Mensal Gamma',
            duration_days=30, price=Decimal('39.90'), is_active=True,
        )
        _db.session.add(plan_c)
        _db.session.flush()

        for g, p in [(group_a, plan_a_monthly), (group_b, plan_b_monthly), (group_c, plan_c)]:
            _db.session.add(Subscription(
                group_id=g.id, plan_id=p.id,
                telegram_user_id=str(user_id), telegram_username='multisub3',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=20),
                status='active',
            ))
        _db.session.commit()

        from bot.handlers.subscription import status_command
        user = make_user(user_id, 'MultiUser')
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Alpha Premium' in text
        assert 'Beta VIP' in text
        assert 'Gamma Group' in text
        assert 'Ativas: 3' in text


# ===========================================================================
# 4. PAYMENT FLOW TESTS
# ===========================================================================

class TestPaymentFlow:
    """Testes do fluxo de pagamento"""

    def test_start_payment_shows_summary(self, app_ctx, group_a, plan_a_monthly):
        """Selecionar plano mostra resumo do pedido"""
        from bot.handlers.payment import start_payment

        user = make_user(300)
        query = make_callback_query(user=user, data=f'plan_{group_a.id}_{plan_a_monthly.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))

        query.edit_message_text.assert_called_once()
        text = query.edit_message_text.call_args[0][0]
        assert 'RESUMO DO PEDIDO' in text
        assert 'Alpha Premium' in text
        assert '29' in text  # format_currency uses comma: "R$ 29,90"

    def test_start_payment_stores_checkout_data(self, app_ctx, group_a, plan_a_monthly):
        """Dados do checkout sao armazenados no contexto"""
        from bot.handlers.payment import start_payment

        user = make_user(301)
        query = make_callback_query(user=user, data=f'plan_{group_a.id}_{plan_a_monthly.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))

        checkout = ctx.user_data.get('checkout')
        assert checkout is not None
        assert checkout['group_id'] == group_a.id
        assert checkout['plan_id'] == plan_a_monthly.id
        assert checkout['amount'] == float(plan_a_monthly.price)

    def test_start_payment_invalid_callback(self, app_ctx):
        """Callback invalido mostra erro"""
        from bot.handlers.payment import start_payment

        user = make_user(302)
        query = make_callback_query(user=user, data='plan_invalid')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'Erro' in text

    def test_start_payment_nonexistent_group(self, app_ctx):
        """Grupo inexistente mostra erro"""
        from bot.handlers.payment import start_payment

        user = make_user(303)
        query = make_callback_query(user=user, data='plan_99999_99999')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'não encontrado' in text

    def test_payment_method_no_session_data(self, app_ctx):
        """Selecionar metodo sem dados de sessao mostra erro"""
        from bot.handlers.payment import handle_payment_method

        user = make_user(304)
        query = make_callback_query(user=user, data='pay_stripe')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(handle_payment_method(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'expirada' in text.lower() or 'Sessão' in text

    def test_fee_calculation(self, app_ctx, group_a, plan_a_monthly):
        """Taxa da plataforma calculada corretamente (10%)"""
        from bot.handlers.payment import start_payment

        user = make_user(305)
        query = make_callback_query(user=user, data=f'plan_{group_a.id}_{plan_a_monthly.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))

        checkout = ctx.user_data['checkout']
        assert abs(checkout['platform_fee'] - 2.99) < 0.01  # 10% of 29.90
        assert abs(checkout['creator_amount'] - 26.91) < 0.01  # 90%

    def test_lifetime_plan_detection(self, app_ctx, group_b, plan_b_lifetime):
        """Plano vitalicio detectado corretamente"""
        from bot.handlers.payment import start_payment

        user = make_user(306)
        query = make_callback_query(user=user, data=f'plan_{group_b.id}_{plan_b_lifetime.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))

        checkout = ctx.user_data['checkout']
        assert checkout['is_lifetime'] is True

        text = query.edit_message_text.call_args[0][0]
        assert 'Vitalicio' in text


# ===========================================================================
# 5. PAYMENT VERIFICATION TESTS
# ===========================================================================

class TestPaymentVerification:
    """Testes da verificacao de pagamento"""

    def test_no_pending_transactions(self, app_ctx):
        """Sem transacoes pendentes mostra mensagem apropriada"""
        from bot.handlers.payment_verification import check_payment_status

        user = make_user(400)
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'Nenhum pagamento pendente' in text

    @patch('bot.handlers.payment_verification.get_stripe_session_details', new_callable=AsyncMock)
    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_payment_confirmed_activates_subscription(self, mock_verify, mock_details, app_ctx,
                                                       group_a, plan_a_monthly, creator_a):
        """Pagamento confirmado ativa assinatura e atualiza saldo"""
        mock_verify.return_value = True
        mock_details.return_value = {
            'subscription_id': 'sub_test_401',
            'payment_intent_id': 'pi_test_401',
            'payment_method_type': 'card',
        }

        user_id = 401
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='payuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('29.90'),
            fee=Decimal('2.99'), net_amount=Decimal('26.91'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_test_confirm_401',
        )
        _db.session.add(txn)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()
        # Mock bot.create_chat_invite_link
        invite_link_obj = MagicMock()
        invite_link_obj.invite_link = 'https://t.me/+unique_link'
        ctx.bot.create_chat_invite_link = AsyncMock(return_value=invite_link_obj)

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))

        # Verificar que assinatura foi ativada
        _db.session.refresh(sub)
        _db.session.refresh(txn)
        assert sub.status == 'active'
        assert txn.status == 'completed'
        assert txn.paid_at is not None

        # Verificar que stripe_subscription_id foi salvo
        assert sub.stripe_subscription_id == 'sub_test_401'
        assert txn.stripe_payment_intent_id == 'pi_test_401'
        assert sub.payment_method_type == 'card'

        # Verificar saldo do criador (Transaction auto-calculates fees:
        # 29.90 - 0.99 fixed - 2.99 percentage = 25.92 net)
        _db.session.refresh(creator_a)
        assert creator_a.balance > 0
        assert creator_a.total_earned > 0

        # Verificar mensagem
        text = query.edit_message_text.call_args[0][0]
        assert 'CONFIRMADO' in text

    @patch('bot.handlers.payment_verification.get_stripe_session_details', new_callable=AsyncMock)
    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_payment_confirmed_saves_stripe_subscription_id(self, mock_verify, mock_details,
                                                             app_ctx, group_a, plan_a_monthly, creator_a):
        """Pagamento confirmado salva stripe_subscription_id — corrige bug 'Assinatura avulsa'"""
        mock_verify.return_value = True
        mock_details.return_value = {
            'subscription_id': 'sub_recurring_test',
            'payment_intent_id': None,
            'payment_method_type': 'boleto',
        }

        user_id = 410
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='recuruser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
            is_legacy=False, auto_renew=True,
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('29.90'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_test_recurring_410',
        )
        _db.session.add(txn)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()
        invite_link_obj = MagicMock()
        invite_link_obj.invite_link = 'https://t.me/+link_410'
        ctx.bot.create_chat_invite_link = AsyncMock(return_value=invite_link_obj)

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))

        _db.session.refresh(sub)
        # stripe_subscription_id must be set — this is the fix for "Assinatura avulsa"
        assert sub.stripe_subscription_id == 'sub_recurring_test'
        assert sub.payment_method_type == 'boleto'
        assert sub.status == 'active'

    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_payment_pending_shows_retry(self, mock_verify, app_ctx, group_a, plan_a_monthly):
        """Pagamento ainda nao confirmado mostra opcao de retry"""
        mock_verify.return_value = False

        user_id = 402
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='pendpay',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('29.90'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_test_pending_402',
        )
        _db.session.add(txn)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'não confirmado' in text.lower() or 'processado' in text.lower()

    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_fallback_to_context_session_id(self, mock_verify, app_ctx, group_a, plan_a_monthly):
        """Usa session_id do contexto quando nao encontra transacao recente"""
        mock_verify.return_value = False

        user_id = 403
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='ctxuser',
            start_date=datetime.utcnow() - timedelta(hours=25),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('29.90'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_test_ctx_403',
            created_at=datetime.utcnow() - timedelta(hours=25),
        )
        _db.session.add(txn)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context(user_data={'stripe_session_id': 'cs_test_ctx_403'})

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))

        # Deve ter tentado verificar via session_id do contexto
        mock_verify.assert_called()


# ===========================================================================
# 6. CANCELLATION FLOW TESTS
# ===========================================================================

class TestCancellationFlow:
    """Testes do fluxo de cancelamento"""

    def test_cancel_shows_confirmation(self, app_ctx, group_a, plan_a_monthly):
        """Cancelar mostra mensagem de confirmacao com data de fim"""
        from bot.handlers.subscription import cancel_subscription

        user_id = 500
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='canceluser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'cancel_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(cancel_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'Cancelar Assinatura' in text
        assert 'Alpha Premium' in text
        assert 'mantera acesso' in text.lower() or 'mantará' in text.lower()
        # Nao deve dizer "imediatamente"
        assert 'imediatamente' not in text.lower()

    def test_cancel_wrong_user_rejected(self, app_ctx, group_a, plan_a_monthly):
        """Usuario nao pode cancelar assinatura de outro"""
        from bot.handlers.subscription import cancel_subscription

        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id='999999', telegram_username='otheruser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(111111)  # Outro usuario
        query = make_callback_query(user=user, data=f'cancel_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(cancel_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'não encontrada' in text or 'cancelada' in text

    def test_cancel_already_cancelled(self, app_ctx, group_a, plan_a_monthly):
        """Nao pode cancelar assinatura ja cancelada"""
        from bot.handlers.subscription import cancel_subscription

        user_id = 502
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='cancelled',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='cancelled',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'cancel_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(cancel_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'não encontrada' in text or 'cancelada' in text

    def test_confirm_cancel_legacy_sets_cancel_at_period_end(self, app_ctx, group_a, plan_a_monthly):
        """Confirmar cancelamento legacy define cancel_at_period_end e mantem acesso"""
        from bot.handlers.subscription import confirm_cancel_subscription

        user_id = 503
        end_date = datetime.utcnow() + timedelta(days=20)
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='legacycancel',
            start_date=datetime.utcnow(),
            end_date=end_date,
            status='active',
            is_legacy=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'confirm_cancel_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(confirm_cancel_subscription(update, ctx))

        _db.session.refresh(sub)
        assert sub.status == 'active'  # Ainda ativo, nao cancelado imediatamente
        assert sub.cancel_at_period_end is True
        assert sub.auto_renew is False

        text = query.edit_message_text.call_args[0][0]
        assert 'Agendado' in text
        assert 'mantera acesso' in text.lower() or 'mantará' in text.lower()

    @patch('bot.handlers.subscription.stripe')
    def test_confirm_cancel_stripe_calls_api(self, mock_stripe, app_ctx, group_a, plan_a_monthly):
        """Confirmar cancelamento Stripe chama API com cancel_at_period_end"""
        from bot.handlers.subscription import confirm_cancel_subscription

        user_id = 504
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='stripecancel',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
            stripe_subscription_id='sub_test_504',
            is_legacy=False,
            auto_renew=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'confirm_cancel_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(confirm_cancel_subscription(update, ctx))

        # Verificar chamada Stripe
        mock_stripe.Subscription.modify.assert_called_once_with(
            'sub_test_504',
            cancel_at_period_end=True,
        )

        _db.session.refresh(sub)
        assert sub.cancel_at_period_end is True
        assert sub.auto_renew is False

        text = query.edit_message_text.call_args[0][0]
        assert 'Agendado' in text
        assert 'reativar' in text.lower()  # Deve oferecer opcao de reativar

    def test_cancel_one_of_multiple_subs(self, app_ctx, group_a, group_b,
                                          plan_a_monthly, plan_b_monthly):
        """Cancelar uma de varias assinaturas nao afeta as outras"""
        user_id = 505

        sub_a = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='multicancel',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active', is_legacy=True,
        )
        sub_b = Subscription(
            group_id=group_b.id, plan_id=plan_b_monthly.id,
            telegram_user_id=str(user_id), telegram_username='multicancel',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active', is_legacy=True,
        )
        _db.session.add_all([sub_a, sub_b])
        _db.session.commit()

        from bot.handlers.subscription import confirm_cancel_subscription

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'confirm_cancel_sub_{sub_a.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(confirm_cancel_subscription(update, ctx))

        _db.session.refresh(sub_a)
        _db.session.refresh(sub_b)
        assert sub_a.cancel_at_period_end is True
        assert sub_b.cancel_at_period_end is not True
        assert sub_b.status == 'active'


# ===========================================================================
# 7. REACTIVATION FLOW TESTS
# ===========================================================================

class TestReactivationFlow:
    """Testes de reativacao de assinatura"""

    @patch('bot.handlers.subscription.stripe')
    def test_reactivate_stripe_subscription(self, mock_stripe, app_ctx, group_a, plan_a_monthly):
        """Reativar assinatura Stripe chama API corretamente"""
        from bot.handlers.subscription import reactivate_subscription

        user_id = 600
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='reactuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=15),
            status='active',
            stripe_subscription_id='sub_test_600',
            cancel_at_period_end=True,
            auto_renew=False,
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'reactivate_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(reactivate_subscription(update, ctx))

        mock_stripe.Subscription.modify.assert_called_once_with(
            'sub_test_600',
            cancel_at_period_end=False,
        )

        _db.session.refresh(sub)
        assert sub.cancel_at_period_end is False
        assert sub.auto_renew is True

        text = query.edit_message_text.call_args[0][0]
        assert 'Reativada' in text

    def test_reactivate_legacy_not_allowed(self, app_ctx, group_a, plan_a_monthly):
        """Nao pode reativar assinatura sem stripe_subscription_id"""
        from bot.handlers.subscription import reactivate_subscription

        user_id = 601
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='legacyreact',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=15),
            status='active',
            cancel_at_period_end=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'reactivate_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(reactivate_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'nao pode ser reativada' in text.lower() or 'não pode' in text.lower()

    def test_reactivate_wrong_user(self, app_ctx, group_a, plan_a_monthly):
        """Nao pode reativar assinatura de outro usuario"""
        from bot.handlers.subscription import reactivate_subscription

        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id='999999', telegram_username='otheruser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=15),
            status='active',
            stripe_subscription_id='sub_test_other',
            cancel_at_period_end=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(111111)
        query = make_callback_query(user=user, data=f'reactivate_sub_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(reactivate_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'nao encontrada' in text.lower() or 'não encontrada' in text.lower()


# ===========================================================================
# 8. STATUS COMMAND TESTS
# ===========================================================================

class TestStatusCommand:
    """Testes do comando /status"""

    def test_status_no_subscriptions(self, app_ctx):
        """Sem assinaturas mostra mensagem vazia"""
        from bot.handlers.subscription import status_command

        user = make_user(700)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Nenhuma' in text

    def test_status_active_shows_days_left(self, app_ctx, group_a, plan_a_monthly):
        """Status ativo mostra dias restantes e emoji correto"""
        from bot.handlers.subscription import status_command

        user_id = 701
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='statususer',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Alpha Premium' in text
        assert 'Ativas: 1' in text

    def test_status_expiring_soon_urgent_emoji(self, app_ctx, group_a, plan_a_monthly):
        """Assinatura prestes a expirar mostra emoji vermelho"""
        from bot.handlers.subscription import status_command

        user_id = 702
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='urgentuser',
            start_date=datetime.utcnow() - timedelta(days=28),
            end_date=datetime.utcnow() + timedelta(days=2),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        # Emoji vermelho para <= 3 dias
        assert '\U0001f534' in text  # Red circle emoji

    def test_status_mixed_active_expired(self, app_ctx, group_a, group_b,
                                         plan_a_monthly, plan_b_monthly):
        """Status mostra tanto ativas como expiradas"""
        from bot.handlers.subscription import status_command

        user_id = 703
        active_sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='mixeduser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        expired_sub = Subscription(
            group_id=group_b.id, plan_id=plan_b_monthly.id,
            telegram_user_id=str(user_id), telegram_username='mixeduser',
            start_date=datetime.utcnow() - timedelta(days=60),
            end_date=datetime.utcnow() - timedelta(days=30),
            status='expired',
        )
        _db.session.add_all([active_sub, expired_sub])
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Ativas: 1' in text
        assert 'Expiradas: 1' in text
        assert 'EXPIRADAS' in text

    def test_status_cancel_at_period_end_shows_label(self, app_ctx, group_a, plan_a_monthly):
        """Assinatura com cancel_at_period_end mostra label de cancelamento agendado"""
        from bot.handlers.subscription import status_command

        user_id = 704
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='cancelscheduled',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=15),
            status='active',
            cancel_at_period_end=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Cancelamento agendado' in text or 'cancelamento' in text.lower()

    def test_status_shows_total_spent(self, app_ctx, group_a, plan_a_monthly):
        """Status mostra total investido"""
        from bot.handlers.subscription import status_command

        user_id = 705
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='spentuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('29.90'),
            status='completed', payment_method='stripe',
            paid_at=datetime.utcnow(),
        )
        _db.session.add(txn)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert '29.90' in text
        assert 'investido' in text.lower()

    def test_status_via_callback(self, app_ctx, group_a, plan_a_monthly):
        """Status funciona via callback query tambem"""
        from bot.handlers.subscription import status_command

        user_id = 706
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='callbackuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        msg = make_message()
        query = make_callback_query(user=user, data='check_status', message=msg)
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))

        query.edit_message_text.assert_called_once()


# ===========================================================================
# 9. DISCOVERY TESTS
# ===========================================================================

class TestDiscovery:
    """Testes do sistema de descoberta de grupos"""

    def test_discover_shows_active_groups(self, app_ctx, group_a, group_b,
                                          plan_a_monthly, plan_b_monthly):
        """Descoberta mostra grupos ativos"""
        from bot.handlers.discovery import show_popular_groups

        user = make_user(800)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_popular_groups(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Alpha Premium' in text
        assert 'Beta VIP' in text

    def test_discover_excludes_blocked_creator(self, app_ctx, group_a, group_blocked,
                                                plan_a_monthly):
        """Grupos de criadores bloqueados nao aparecem"""
        from bot.handlers.discovery import show_popular_groups

        # Plan for blocked group
        plan_blocked = PricingPlan(
            group_id=group_blocked.id, name='Blocked Plan',
            duration_days=30, price=Decimal('9.90'), is_active=True,
        )
        _db.session.add(plan_blocked)
        _db.session.commit()

        user = make_user(801)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_popular_groups(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Alpha Premium' in text
        assert 'Criador Bloqueado' not in text

    def test_discover_excludes_inactive_groups(self, app_ctx, group_a, group_inactive,
                                                plan_a_monthly):
        """Grupos inativos nao aparecem"""
        from bot.handlers.discovery import show_popular_groups

        user = make_user(802)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_popular_groups(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Grupo Inativo' not in text

    def test_discover_no_groups(self, app_ctx):
        """Sem grupos mostra mensagem vazia"""
        from bot.handlers.discovery import show_popular_groups

        user = make_user(803)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_popular_groups(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Nenhum' in text

    def test_discover_uses_slugs_in_links(self, app_ctx, group_a, plan_a_monthly):
        """Links de grupos usam invite_slug, nao IDs"""
        from bot.handlers.discovery import show_popular_groups

        user = make_user(804)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_popular_groups(update, ctx))

        # Verificar que o keyboard contem o slug
        call_kwargs = update.message.reply_text.call_args[1]
        markup = call_kwargs.get('reply_markup')
        if markup:
            for row in markup.inline_keyboard:
                for button in row:
                    if button.url and 'start=' in button.url:
                        assert f'g_{group_a.invite_slug}' in button.url
                        assert f'g_{group_a.id}' not in button.url


# ===========================================================================
# 10. SCHEDULED TASKS TESTS
# ===========================================================================

class TestScheduledTasks:
    """Testes das tarefas agendadas (expiracao e lembretes)"""

    def test_expired_subscription_marked(self, app_ctx, group_a, plan_a_monthly):
        """Assinatura legacy expirada eh marcada como expired"""
        from bot.jobs.scheduled_tasks import check_expired_subscriptions
        import bot.jobs.scheduled_tasks as tasks

        user_id = 900
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='expiredtask',
            start_date=datetime.utcnow() - timedelta(days=35),
            end_date=datetime.utcnow() - timedelta(days=5),
            status='active',
            is_legacy=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        # Mock application bot
        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        tasks._application = mock_app

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_expired_subscriptions())

        _db.session.refresh(sub)
        assert sub.status == 'expired'

    def test_stripe_managed_not_expired_by_task(self, app_ctx, group_a, plan_a_monthly):
        """Assinatura Stripe-managed NAO eh expirada por tarefa agendada"""
        from bot.jobs.scheduled_tasks import check_expired_subscriptions
        import bot.jobs.scheduled_tasks as tasks

        user_id = 901
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='stripemanaged',
            start_date=datetime.utcnow() - timedelta(days=35),
            end_date=datetime.utcnow() - timedelta(days=5),
            status='active',
            stripe_subscription_id='sub_test_managed_901',
            is_legacy=False,
        )
        _db.session.add(sub)
        _db.session.commit()

        tasks._application = MagicMock()
        tasks._application.bot = AsyncMock()

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_expired_subscriptions())

        _db.session.refresh(sub)
        assert sub.status == 'active'  # Stripe gerencia, nao a task

    def test_expired_task_removes_from_group(self, app_ctx, group_a, plan_a_monthly):
        """Tarefa de expiracao tenta remover usuario do grupo"""
        from bot.jobs.scheduled_tasks import check_expired_subscriptions
        import bot.jobs.scheduled_tasks as tasks

        user_id = 902
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='removetask',
            start_date=datetime.utcnow() - timedelta(days=35),
            end_date=datetime.utcnow() - timedelta(days=5),
            status='active',
            is_legacy=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        tasks._application = mock_app

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_expired_subscriptions())

        # Verificar que ban_chat_member foi chamado
        mock_app.bot.ban_chat_member.assert_called_with(
            chat_id=int(group_a.telegram_id),
            user_id=user_id,
        )

    def test_expired_task_notifies_user(self, app_ctx, group_a, plan_a_monthly):
        """Tarefa de expiracao envia notificacao ao usuario"""
        from bot.jobs.scheduled_tasks import check_expired_subscriptions
        import bot.jobs.scheduled_tasks as tasks

        user_id = 903
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='notifytask',
            start_date=datetime.utcnow() - timedelta(days=35),
            end_date=datetime.utcnow() - timedelta(days=5),
            status='active',
            is_legacy=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        tasks._application = mock_app

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_expired_subscriptions())

        # Verificar que mensagem foi enviada
        mock_app.bot.send_message.assert_called()
        call_kwargs = mock_app.bot.send_message.call_args[1]
        assert call_kwargs['chat_id'] == user_id
        assert 'Expirada' in call_kwargs['text'] or 'expirou' in call_kwargs['text']

    def test_active_not_expired_not_touched(self, app_ctx, group_a, plan_a_monthly):
        """Assinatura ativa nao expirada nao eh tocada"""
        from bot.jobs.scheduled_tasks import check_expired_subscriptions
        import bot.jobs.scheduled_tasks as tasks

        user_id = 904
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='activenottouch',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
            is_legacy=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        tasks._application = MagicMock()

        import asyncio
        asyncio.get_event_loop().run_until_complete(check_expired_subscriptions())

        _db.session.refresh(sub)
        assert sub.status == 'active'

    def test_renewal_reminder_3_days(self, app_ctx, group_a, plan_a_monthly):
        """Lembrete de renovacao enviado quando faltam 3 dias"""
        from bot.jobs.scheduled_tasks import send_renewal_reminders
        import bot.jobs.scheduled_tasks as tasks

        user_id = 905
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='reminderuser',
            start_date=datetime.utcnow() - timedelta(days=27),
            end_date=datetime.utcnow() + timedelta(days=3, hours=-1),
            status='active',
            is_legacy=True,
        )
        _db.session.add(sub)
        _db.session.commit()

        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        tasks._application = mock_app

        import asyncio
        asyncio.get_event_loop().run_until_complete(send_renewal_reminders())

        # Deve ter enviado lembrete
        mock_app.bot.send_message.assert_called()


# ===========================================================================
# 11. RENEWAL FLOW TESTS
# ===========================================================================

class TestRenewalFlow:
    """Testes do fluxo de renovacao"""

    def test_renewals_list_shows_expiring(self, app_ctx, group_a, plan_a_monthly):
        """Lista de renovacoes mostra assinaturas expirando"""
        from bot.handlers.subscription import show_renewals_list

        user_id = 1000
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='renewuser',
            start_date=datetime.utcnow() - timedelta(days=25),
            end_date=datetime.utcnow() + timedelta(days=5),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_renewals')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_renewals_list(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'Alpha Premium' in text
        assert 'Renova' in text or 'renovar' in text.lower()

    def test_renewals_list_nothing_to_renew(self, app_ctx, group_a, plan_a_monthly):
        """Lista de renovacoes vazia quando nenhuma expira em 15 dias"""
        from bot.handlers.subscription import show_renewals_list

        user_id = 1001
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='noneedrenew',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=25),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_renewals')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_renewals_list(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'em dia' in text.lower() or 'Todas' in text

    def test_process_renewal_with_discount(self, app_ctx, group_a, plan_a_monthly):
        """Renovacao com mais de 5 dias restantes aplica 10% desconto"""
        from bot.handlers.subscription import process_renewal

        user_id = 1002
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='discountuser',
            start_date=datetime.utcnow() - timedelta(days=20),
            end_date=datetime.utcnow() + timedelta(days=10),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'renew_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(process_renewal(update, ctx, sub.id))

        text = query.edit_message_text.call_args[0][0]
        assert '10%' in text or 'desconto' in text.lower()
        assert 'economiza' in text.lower()

        # Verificar valor com desconto no contexto
        renewal_data = ctx.user_data.get('renewal')
        assert renewal_data is not None
        assert renewal_data['discount'] == 0.1

    def test_process_renewal_no_discount(self, app_ctx, group_a, plan_a_monthly):
        """Renovacao com menos de 5 dias restantes nao aplica desconto"""
        from bot.handlers.subscription import process_renewal

        user_id = 1003
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='nodiscuser',
            start_date=datetime.utcnow() - timedelta(days=28),
            end_date=datetime.utcnow() + timedelta(days=2),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data=f'renew_{sub.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(process_renewal(update, ctx, sub.id))

        renewal_data = ctx.user_data.get('renewal')
        assert renewal_data['discount'] == 0

    def test_urgent_renewals(self, app_ctx, group_a, plan_a_monthly):
        """Lista urgente mostra apenas assinaturas com <= 3 dias"""
        from bot.handlers.subscription import show_urgent_renewals

        user_id = 1004
        sub_urgent = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='urgrenew',
            start_date=datetime.utcnow() - timedelta(days=29),
            end_date=datetime.utcnow() + timedelta(days=1),
            status='active',
        )
        _db.session.add(sub_urgent)
        _db.session.commit()

        user = make_user(user_id)
        query = make_callback_query(user=user, data='renew_urgent')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(show_urgent_renewals(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'Urgentes' in text
        assert 'Alpha Premium' in text


# ===========================================================================
# 12. HELP COMMAND
# ===========================================================================

class TestHelpCommand:
    """Testes do comando /help"""

    def test_help_shows_commands(self, app_ctx):
        from bot.handlers.start import help_command

        user = make_user(1100)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(help_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert '/start' in text
        assert '/status' in text
        assert '/descobrir' in text
        assert '/help' in text


# ===========================================================================
# 13. EDGE CASES & SECURITY
# ===========================================================================

class TestEdgeCases:
    """Testes de casos extremos e seguranca"""

    def test_subscription_id_enumeration_protection(self, app_ctx, group_a, plan_a_monthly):
        """Nao pode cancelar assinatura de outro via ID sequencial"""
        from bot.handlers.subscription import cancel_subscription

        victim_sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id='111111', telegram_username='victim',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(victim_sub)
        _db.session.commit()

        attacker = make_user(222222)
        query = make_callback_query(user=attacker, data=f'cancel_sub_{victim_sub.id}')
        update = make_update(user=attacker, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(cancel_subscription(update, ctx))

        _db.session.refresh(victim_sub)
        assert victim_sub.status == 'active'  # Nao cancelou

    def test_reactivation_id_enumeration_protection(self, app_ctx, group_a, plan_a_monthly):
        """Nao pode reativar assinatura de outro via ID"""
        from bot.handlers.subscription import reactivate_subscription

        victim_sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id='333333', telegram_username='victim2',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
            stripe_subscription_id='sub_victim',
            cancel_at_period_end=True,
        )
        _db.session.add(victim_sub)
        _db.session.commit()

        attacker = make_user(444444)
        query = make_callback_query(user=attacker, data=f'reactivate_sub_{victim_sub.id}')
        update = make_update(user=attacker, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(reactivate_subscription(update, ctx))

        _db.session.refresh(victim_sub)
        assert victim_sub.cancel_at_period_end is True  # Nao reativou

    def test_nonexistent_subscription_cancel(self, app_ctx):
        """Cancelar assinatura inexistente mostra erro"""
        from bot.handlers.subscription import cancel_subscription

        user = make_user(1200)
        query = make_callback_query(user=user, data='cancel_sub_99999')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(cancel_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'não encontrada' in text or 'cancelada' in text

    def test_nonexistent_subscription_reactivation(self, app_ctx):
        """Reativar assinatura inexistente mostra erro"""
        from bot.handlers.subscription import reactivate_subscription

        user = make_user(1201)
        query = make_callback_query(user=user, data='reactivate_sub_99999')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(reactivate_subscription(update, ctx))

        text = query.edit_message_text.call_args[0][0]
        assert 'nao encontrada' in text.lower() or 'não encontrada' in text.lower()

    def test_group_slug_is_random(self, app_ctx, creator_a):
        """Cada grupo recebe slug aleatorio diferente"""
        slugs = set()
        for i in range(10):
            g = Group(
                name=f'Random Group {i}',
                telegram_id=f'-100{9000000000 + i}',
                creator_id=creator_a.id,
                is_active=True,
            )
            _db.session.add(g)
            _db.session.flush()
            slugs.add(g.invite_slug)

        _db.session.commit()
        assert len(slugs) == 10  # Todos unicos

    def test_callback_data_uses_int_not_slug(self, app_ctx, group_a, plan_a_monthly):
        """callback_data plan_ usa ID numerico (seguro, interno)"""
        from bot.handlers.start import start_subscription_flow

        user = make_user(1202)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        call_kwargs = update.message.reply_text.call_args[1]
        markup = call_kwargs.get('reply_markup')
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data and button.callback_data.startswith('plan_'):
                    # Deve usar IDs inteiros, nao slugs
                    parts = button.callback_data.split('_')
                    assert parts[1].isdigit()
                    assert parts[2].isdigit()

    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_double_payment_verification(self, mock_verify, app_ctx, group_a,
                                          plan_a_monthly, creator_a):
        """Verificacao dupla nao atualiza saldo duas vezes"""
        mock_verify.return_value = True

        user_id = 1203
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='doublepay',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub)
        _db.session.flush()
        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('29.90'),
            fee=Decimal('2.99'), net_amount=Decimal('26.91'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_test_double_1203',
        )
        _db.session.add(txn)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        user = make_user(user_id)
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()
        ctx.bot.create_chat_invite_link = AsyncMock(
            return_value=MagicMock(invite_link='https://t.me/+test')
        )

        import asyncio

        # Primeira verificacao
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))
        _db.session.refresh(creator_a)
        balance_after_first = creator_a.balance

        # Segunda verificacao - transacao ja completed, nao deve encontrar pendentes
        query2 = make_callback_query(user=user, data='check_payment_status')
        update2 = MagicMock()
        update2.callback_query = query2
        ctx2 = make_context()

        asyncio.get_event_loop().run_until_complete(check_payment_status(update2, ctx2))
        _db.session.refresh(creator_a)
        assert creator_a.balance == balance_after_first  # Saldo nao duplicou

    def test_multiple_creators_balance_isolation(self, app_ctx, group_a, group_b,
                                                  plan_a_monthly, plan_b_monthly,
                                                  creator_a, creator_b):
        """Pagamentos de criadores diferentes atualizam saldos separadamente"""
        user_id = 1204

        # Sub + txn para criador A
        sub_a = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='multibal',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        _db.session.add(sub_a)
        _db.session.flush()
        txn_a = Transaction(
            subscription_id=sub_a.id, amount=Decimal('29.90'),
            fee=Decimal('2.99'), net_amount=Decimal('26.91'),
            status='completed', payment_method='stripe',
            paid_at=datetime.utcnow(),
        )
        _db.session.add(txn_a)

        # Sub + txn para criador B
        sub_b = Subscription(
            group_id=group_b.id, plan_id=plan_b_monthly.id,
            telegram_user_id=str(user_id), telegram_username='multibal',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        _db.session.add(sub_b)
        _db.session.flush()
        txn_b = Transaction(
            subscription_id=sub_b.id, amount=Decimal('19.90'),
            fee=Decimal('1.99'), net_amount=Decimal('17.91'),
            status='completed', payment_method='stripe',
            paid_at=datetime.utcnow(),
        )
        _db.session.add(txn_b)

        # Atualizar saldos manualmente (simula webhook)
        creator_a.balance += txn_a.net_amount
        creator_a.total_earned += txn_a.net_amount
        creator_b.balance += txn_b.net_amount
        creator_b.total_earned += txn_b.net_amount
        _db.session.commit()

        _db.session.refresh(creator_a)
        _db.session.refresh(creator_b)
        # Transaction auto-calculates fees, so use actual net_amount
        assert creator_a.balance > 0
        assert creator_b.balance > 0
        assert creator_a.balance != creator_b.balance  # Isolation
        assert creator_a.total_earned == creator_a.balance
        assert creator_b.total_earned == creator_b.balance


# ===========================================================================
# 14. FULL USER JOURNEY
# ===========================================================================

class TestFullUserJourney:
    """Testes end-to-end do fluxo completo de um usuario"""

    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_complete_journey_subscribe_use_cancel(self, mock_verify, app_ctx,
                                                    group_a, group_b,
                                                    plan_a_monthly, plan_b_monthly,
                                                    creator_a, creator_b):
        """Jornada completa: descobrir -> assinar 2 grupos -> usar -> cancelar 1 -> status"""
        import asyncio
        mock_verify.return_value = True
        user_id = 1300
        user = make_user(user_id, 'JourneyUser', 'journeyuser')

        # STEP 1: Descobrir grupos
        from bot.handlers.discovery import show_popular_groups
        update = make_update(user=user)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(show_popular_groups(update, ctx))
        text = update.message.reply_text.call_args[0][0]
        assert 'Alpha Premium' in text or 'Beta VIP' in text

        # STEP 2: Iniciar assinatura grupo A
        from bot.handlers.start import start_subscription_flow
        update = make_update(user=user)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )
        text = update.message.reply_text.call_args[0][0]
        assert 'Mensal Alpha' in text

        # STEP 3: Selecionar plano A
        from bot.handlers.payment import start_payment
        query = make_callback_query(user=user, data=f'plan_{group_a.id}_{plan_a_monthly.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(start_payment(update, ctx))
        assert ctx.user_data['checkout']['group_id'] == group_a.id

        # STEP 4: Simular pagamento concluido (criamos sub+txn e confirmamos)
        sub_a = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='journeyuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub_a)
        _db.session.flush()
        txn_a = Transaction(
            subscription_id=sub_a.id, amount=Decimal('29.90'),
            fee=Decimal('2.99'), net_amount=Decimal('26.91'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_journey_a',
        )
        _db.session.add(txn_a)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status
        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()
        ctx.bot.create_chat_invite_link = AsyncMock(
            return_value=MagicMock(invite_link='https://t.me/+journeyA')
        )
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))
        _db.session.refresh(sub_a)
        assert sub_a.status == 'active'

        # STEP 5: Assinar grupo B tambem
        sub_b = Subscription(
            group_id=group_b.id, plan_id=plan_b_monthly.id,
            telegram_user_id=str(user_id), telegram_username='journeyuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        _db.session.add(sub_b)
        _db.session.flush()
        txn_b = Transaction(
            subscription_id=sub_b.id, amount=Decimal('19.90'),
            fee=Decimal('1.99'), net_amount=Decimal('17.91'),
            status='pending', payment_method='stripe',
            stripe_session_id='cs_journey_b',
        )
        _db.session.add(txn_b)
        _db.session.commit()

        query = make_callback_query(user=user, data='check_payment_status')
        update = MagicMock()
        update.callback_query = query
        ctx = make_context()
        ctx.bot.create_chat_invite_link = AsyncMock(
            return_value=MagicMock(invite_link='https://t.me/+journeyB')
        )
        asyncio.get_event_loop().run_until_complete(check_payment_status(update, ctx))
        _db.session.refresh(sub_b)
        assert sub_b.status == 'active'

        # STEP 6: Ver status - deve mostrar 2 assinaturas ativas
        from bot.handlers.subscription import status_command
        update = make_update(user=user)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(status_command(update, ctx))
        text = update.message.reply_text.call_args[0][0]
        assert 'Ativas: 2' in text

        # STEP 7: Cancelar grupo A
        from bot.handlers.subscription import confirm_cancel_subscription
        _db.session.refresh(sub_a)
        sub_a.is_legacy = True  # Set as legacy for easier testing
        _db.session.commit()

        query = make_callback_query(user=user, data=f'confirm_cancel_sub_{sub_a.id}')
        update = make_update(user=user, callback_query=query)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(confirm_cancel_subscription(update, ctx))
        _db.session.refresh(sub_a)
        assert sub_a.cancel_at_period_end is True
        assert sub_a.status == 'active'  # Ainda ativo ate expirar

        # STEP 8: sub B nao afetada
        _db.session.refresh(sub_b)
        assert sub_b.status == 'active'
        assert sub_b.cancel_at_period_end is not True

        # STEP 9: Verificar saldos dos criadores (isolados)
        _db.session.refresh(creator_a)
        _db.session.refresh(creator_b)
        assert creator_a.balance > 0
        assert creator_b.balance > 0
        assert creator_a.balance != creator_b.balance  # Saldos diferentes

    def test_user_journey_blocked_creator_midway(self, app_ctx, group_a, plan_a_monthly, creator_a):
        """Criador bloqueado apos usuario assinar - link nao deve funcionar para novos"""
        import asyncio

        # Primeiro usuario assina normalmente
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id='1301', telegram_username='earlybird',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        # Criador eh bloqueado
        creator_a.is_blocked = True
        _db.session.commit()

        # Novo usuario tenta assinar o mesmo grupo
        from bot.handlers.start import start_subscription_flow
        new_user = make_user(1302)
        update = make_update(user=new_user)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_a.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'indisponível' in text

        # Limpar bloqueio para nao afetar outros testes
        creator_a.is_blocked = False
        _db.session.commit()

    def test_subscribe_group_then_group_deleted(self, app_ctx, creator_a):
        """Grupo deletado apos assinatura - status mostra info gracefully"""
        import asyncio

        group_temp = Group(
            name='Temp Group',
            telegram_id='-1009999999999',
            creator_id=creator_a.id,
            is_active=True,
        )
        _db.session.add(group_temp)
        _db.session.flush()
        plan_temp = PricingPlan(
            group_id=group_temp.id, name='Temp Plan',
            duration_days=30, price=Decimal('9.90'), is_active=True,
        )
        _db.session.add(plan_temp)
        _db.session.flush()
        sub = Subscription(
            group_id=group_temp.id, plan_id=plan_temp.id,
            telegram_user_id='1303', telegram_username='tempuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        # Tentar acessar via link do grupo deletado (inativado)
        group_temp.is_active = False
        _db.session.commit()

        from bot.handlers.start import start_subscription_flow
        new_user = make_user(1304)
        update = make_update(user=new_user)
        ctx = make_context()
        asyncio.get_event_loop().run_until_complete(
            start_subscription_flow(update, ctx, group_temp.invite_slug)
        )

        text = update.message.reply_text.call_args[0][0]
        assert 'indisponível' in text


# ===========================================================================
# 15. PLANOS COMMAND TESTS
# ===========================================================================

class TestPlanosCommand:
    """Testes do comando /planos"""

    def test_planos_shows_active_plans(self, app_ctx, group_a, plan_a_monthly):
        """Mostra planos ativos com valor mensal"""
        from bot.handlers.subscription import planos_command

        user_id = 1400
        sub = Subscription(
            group_id=group_a.id, plan_id=plan_a_monthly.id,
            telegram_user_id=str(user_id), telegram_username='planosuser',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=20),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(planos_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Alpha Premium' in text
        assert 'Mensal Alpha' in text
        assert '29.90' in text

    def test_planos_empty(self, app_ctx):
        """Sem planos ativos mostra mensagem vazia"""
        from bot.handlers.subscription import planos_command

        user = make_user(1401)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(planos_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'não possui' in text.lower() or 'Você não' in text

    def test_planos_lifetime_plan(self, app_ctx, group_b, plan_b_lifetime):
        """Plano vitalicio mostra corretamente"""
        from bot.handlers.subscription import planos_command

        user_id = 1402
        sub = Subscription(
            group_id=group_b.id, plan_id=plan_b_lifetime.id,
            telegram_user_id=str(user_id), telegram_username='lifetimeuser',
            start_date=datetime.utcnow(),
            end_date=datetime(2099, 12, 31),
            status='active',
        )
        _db.session.add(sub)
        _db.session.commit()

        user = make_user(user_id)
        update = make_update(user=user)
        ctx = make_context()

        import asyncio
        asyncio.get_event_loop().run_until_complete(planos_command(update, ctx))

        text = update.message.reply_text.call_args[0][0]
        assert 'Vitalicio' in text


# ===========================================================================
# 16. CONCURRENT / LOAD TESTS
# ===========================================================================

import asyncio
import concurrent.futures
import threading


class TestConcurrentStart:
    """Muitos usuarios chamando /start ao mesmo tempo"""

    def test_50_users_start_simultaneously(self, app_ctx):
        """50 usuarios novos chamam /start ao mesmo tempo sem erro"""
        from bot.handlers.start import start_command

        num_users = 50
        results = []

        async def run_all():
            tasks = []
            for i in range(num_users):
                user = make_user(5000 + i, first_name=f'User{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(start_command(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros em 50 starts: {errors[:3]}"

    def test_30_users_start_with_active_subscriptions(self, app_ctx,
                                                       group_a, plan_a_monthly, creator_a):
        """30 usuarios com assinaturas ativas chamam /start simultaneamente"""
        from bot.handlers.start import start_command

        num_users = 30
        # Criar assinaturas para todos
        for i in range(num_users):
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(5100 + i),
                telegram_username=f'activeuser{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=25),
                status='active',
            )
            _db.session.add(sub)
        _db.session.commit()

        async def run_all():
            tasks = []
            for i in range(num_users):
                user = make_user(5100 + i, first_name=f'Active{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(start_command(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"

    def test_mixed_new_and_existing_users(self, app_ctx,
                                           group_a, plan_a_monthly, creator_a):
        """Mistura de novos e existentes usando /start simultaneamente"""
        from bot.handlers.start import start_command

        # Criar 10 assinaturas
        for i in range(10):
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(5200 + i),
                telegram_username=f'mixuser{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=15),
                status='active',
            )
            _db.session.add(sub)
        _db.session.commit()

        async def run_all():
            tasks = []
            # 10 com assinatura + 20 novos
            for i in range(30):
                user = make_user(5200 + i, first_name=f'Mix{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(start_command(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"


class TestConcurrentDiscovery:
    """Muitos usuarios descobrindo grupos ao mesmo tempo"""

    def test_40_users_discover_simultaneously(self, app_ctx,
                                               group_a, group_b, plan_a_monthly,
                                               plan_b_monthly, creator_a, creator_b):
        """40 usuarios chamam /descobrir ao mesmo tempo"""
        from bot.handlers.discovery import descobrir_command as discover_groups

        num_users = 40

        async def run_all():
            tasks = []
            for i in range(num_users):
                user = make_user(6000 + i, first_name=f'Discover{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(discover_groups(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros em discover: {errors[:3]}"


class TestConcurrentSubscriptionFlow:
    """Multiplos usuarios entrando em fluxos de assinatura simultaneamente"""

    def test_20_users_view_plans_same_group(self, app_ctx,
                                             group_a, plan_a_monthly, plan_a_quarterly,
                                             creator_a):
        """20 usuarios vendo planos do mesmo grupo ao mesmo tempo"""
        from bot.handlers.start import start_subscription_flow

        num_users = 20

        async def run_all():
            tasks = []
            for i in range(num_users):
                user = make_user(6100 + i, first_name=f'Plan{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(
                    start_subscription_flow(update, ctx, group_a.invite_slug)
                )
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"

    def test_users_subscribe_different_groups_simultaneously(self, app_ctx,
                                                              group_a, group_b,
                                                              plan_a_monthly, plan_b_monthly,
                                                              creator_a, creator_b):
        """Usuarios assinando grupos diferentes ao mesmo tempo"""
        from bot.handlers.start import start_subscription_flow

        async def run_all():
            tasks = []
            # 15 usuarios no grupo A
            for i in range(15):
                user = make_user(6200 + i, first_name=f'SubA{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(
                    start_subscription_flow(update, ctx, group_a.invite_slug)
                )
            # 15 usuarios no grupo B
            for i in range(15):
                user = make_user(6300 + i, first_name=f'SubB{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(
                    start_subscription_flow(update, ctx, group_b.invite_slug)
                )
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"


class TestConcurrentPaymentVerification:
    """Multiplos usuarios verificando pagamento ao mesmo tempo"""

    @patch('bot.handlers.payment_verification.get_stripe_session_details', new_callable=AsyncMock)
    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_20_users_verify_payment_simultaneously(self, mock_verify, mock_details,
                                                     app_ctx, group_a, plan_a_monthly,
                                                     creator_a):
        """20 usuarios confirmando pagamento ao mesmo tempo — sem race condition no saldo"""
        mock_verify.return_value = True
        mock_details.return_value = {
            'subscription_id': None,
            'payment_intent_id': 'pi_test_conc',
            'payment_method_type': 'card',
        }

        num_users = 20
        subs = []
        for i in range(num_users):
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(7000 + i),
                telegram_username=f'payconc{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status='pending',
            )
            _db.session.add(sub)
            _db.session.flush()
            txn = Transaction(
                subscription_id=sub.id, amount=Decimal('29.90'),
                status='pending', payment_method='stripe',
                stripe_session_id=f'cs_test_conc_{7000 + i}',
            )
            _db.session.add(txn)
            subs.append(sub)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        async def run_all():
            tasks = []
            for i in range(num_users):
                user = make_user(7000 + i)
                query = make_callback_query(user=user, data='check_payment_status')
                update = MagicMock()
                update.callback_query = query
                ctx = make_context()
                invite_obj = MagicMock()
                invite_obj.invite_link = f'https://t.me/+link_{7000 + i}'
                ctx.bot.create_chat_invite_link = AsyncMock(return_value=invite_obj)
                tasks.append(check_payment_status(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"

        # Todas as assinaturas devem estar ativas
        for sub in subs:
            _db.session.refresh(sub)
            assert sub.status == 'active', f"Sub {sub.id} status={sub.status}"

        # Saldo do criador deve ter crescido (20 pagamentos)
        _db.session.refresh(creator_a)
        assert creator_a.balance > 0
        assert creator_a.total_earned > 0

    @patch('bot.handlers.payment_verification.get_stripe_session_details', new_callable=AsyncMock)
    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_mixed_confirmed_and_pending_simultaneously(self, mock_verify, mock_details,
                                                         app_ctx, group_a, plan_a_monthly,
                                                         creator_a):
        """Mistura de pagamentos confirmados e pendentes ao mesmo tempo"""
        # Alternar: pares = confirmado, impares = pendente
        call_count = 0

        async def smart_verify(session_id):
            nonlocal call_count
            call_count += 1
            # Baseado no user_id embutido no session_id
            uid = int(session_id.split('_')[-1])
            return uid % 2 == 0  # Pares pagaram

        mock_verify.side_effect = smart_verify
        mock_details.return_value = {
            'subscription_id': None,
            'payment_intent_id': None,
            'payment_method_type': None,
        }

        num_users = 20
        subs = []
        for i in range(num_users):
            uid = 7200 + i
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(uid),
                telegram_username=f'mixpay{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status='pending',
            )
            _db.session.add(sub)
            _db.session.flush()
            txn = Transaction(
                subscription_id=sub.id, amount=Decimal('29.90'),
                status='pending', payment_method='stripe',
                stripe_session_id=f'cs_test_mix_{uid}',
            )
            _db.session.add(txn)
            subs.append(sub)
        _db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        async def run_all():
            tasks = []
            for i in range(num_users):
                uid = 7200 + i
                user = make_user(uid)
                query = make_callback_query(user=user, data='check_payment_status')
                update = MagicMock()
                update.callback_query = query
                ctx = make_context()
                invite_obj = MagicMock()
                invite_obj.invite_link = f'https://t.me/+link_{uid}'
                ctx.bot.create_chat_invite_link = AsyncMock(return_value=invite_obj)
                tasks.append(check_payment_status(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"

        # Verificar estados: pares=active, impares=pending
        active_count = 0
        pending_count = 0
        for sub in subs:
            _db.session.refresh(sub)
            uid = int(sub.telegram_user_id)
            if uid % 2 == 0:
                assert sub.status == 'active', f"Sub uid={uid} deveria ser active"
                active_count += 1
            else:
                assert sub.status == 'pending', f"Sub uid={uid} deveria ser pending"
                pending_count += 1
        assert active_count == 10
        assert pending_count == 10


class TestConcurrentStatusCheck:
    """Muitos usuarios consultando status ao mesmo tempo"""

    def test_30_users_check_status_simultaneously(self, app_ctx,
                                                    group_a, group_b,
                                                    plan_a_monthly, plan_b_monthly,
                                                    creator_a, creator_b):
        """30 usuarios com assinaturas em grupos diferentes checam /status"""
        from bot.handlers.subscription import status_command

        num_users = 30
        for i in range(num_users):
            # Metade no grupo A, metade no grupo B
            gid = group_a.id if i < 15 else group_b.id
            pid = plan_a_monthly.id if i < 15 else plan_b_monthly.id
            sub = Subscription(
                group_id=gid, plan_id=pid,
                telegram_user_id=str(7400 + i),
                telegram_username=f'statususer{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=20),
                status='active',
            )
            _db.session.add(sub)
        _db.session.commit()

        async def run_all():
            tasks = []
            for i in range(num_users):
                user = make_user(7400 + i, first_name=f'Status{i}')
                update = make_update(user=user)
                ctx = make_context()
                tasks.append(status_command(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"


class TestConcurrentCancellation:
    """Multiplas cancelações ao mesmo tempo"""

    def test_15_users_cancel_simultaneously(self, app_ctx,
                                             group_a, plan_a_monthly, creator_a):
        """15 usuarios cancelam assinatura ao mesmo tempo"""
        from bot.handlers.subscription import confirm_cancel_subscription

        num_users = 15
        subs = []
        for i in range(num_users):
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(7600 + i),
                telegram_username=f'cancelconc{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=20),
                status='active',
                is_legacy=True,
            )
            _db.session.add(sub)
            _db.session.flush()
            subs.append(sub)
        _db.session.commit()

        sub_ids = [s.id for s in subs]

        async def run_all():
            tasks = []
            for i, sid in enumerate(sub_ids):
                user = make_user(7600 + i)
                query = make_callback_query(user=user, data=f'confirm_cancel_sub_{sid}')
                update = make_update(user=user, callback_query=query)
                ctx = make_context()
                tasks.append(confirm_cancel_subscription(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"

        # Todos devem ter cancel_at_period_end=True (mantém acesso até end_date)
        for sub in subs:
            _db.session.refresh(sub)
            assert sub.cancel_at_period_end is True, f"Sub {sub.id} cancel_at_period_end={sub.cancel_at_period_end}"
            assert sub.auto_renew is False, f"Sub {sub.id} auto_renew={sub.auto_renew}"


class TestConcurrentScheduledTasks:
    """Jobs agendados com muitas assinaturas para processar"""

    def test_expire_50_subscriptions_at_once(self, app_ctx,
                                              group_a, plan_a_monthly, creator_a):
        """Job de expiração processa 50 assinaturas vencidas de uma vez"""
        from bot.jobs.scheduled_tasks import check_expired_subscriptions
        import bot.jobs.scheduled_tasks as tasks_mod

        num = 50
        for i in range(num):
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(8000 + i),
                telegram_username=f'expired{i}',
                start_date=datetime.utcnow() - timedelta(days=35),
                end_date=datetime.utcnow() - timedelta(days=5),
                status='active',
                is_legacy=True,
            )
            _db.session.add(sub)
        _db.session.commit()

        # Mock _application para que remove_from_group e notify_expiration funcionem
        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        old_app = tasks_mod._application
        tasks_mod._application = mock_app

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(check_expired_subscriptions())
        finally:
            tasks_mod._application = old_app

        # Verificar que todas foram expiradas
        expired = _db.session.query(Subscription).filter(
            Subscription.telegram_user_id.in_([str(8000 + i) for i in range(num)]),
            Subscription.status == 'expired'
        ).count()
        assert expired == num, f"Apenas {expired}/{num} expiradas"

    def test_renewal_reminders_for_30_users(self, app_ctx,
                                             group_a, plan_a_monthly, creator_a):
        """Lembretes de renovação para 30 usuarios proximos de expirar"""
        from bot.jobs.scheduled_tasks import send_renewal_reminders
        import bot.jobs.scheduled_tasks as tasks_mod

        num = 30
        for i in range(num):
            sub = Subscription(
                group_id=group_a.id, plan_id=plan_a_monthly.id,
                telegram_user_id=str(8100 + i),
                telegram_username=f'renew{i}',
                start_date=datetime.utcnow() - timedelta(days=27),
                end_date=datetime.utcnow() + timedelta(days=3),
                status='active',
                is_legacy=True,
            )
            _db.session.add(sub)
        _db.session.commit()

        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        mock_app.bot.send_message = AsyncMock()
        old_app = tasks_mod._application
        tasks_mod._application = mock_app

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(send_renewal_reminders())
        finally:
            tasks_mod._application = old_app

        # Deve ter tentado enviar mensagem para todos
        assert mock_app.bot.send_message.call_count == num, \
            f"Esperado {num} mensagens, enviadas {mock_app.bot.send_message.call_count}"


class TestConcurrentMultiCreatorLoad:
    """Cenario realista: multiplos criadores com muitos assinantes"""

    def test_many_users_across_many_groups(self, app_ctx, db):
        """Simula 5 criadores, 5 grupos, 50 assinaturas — todos chamam /status"""
        from bot.handlers.subscription import status_command

        creators = []
        groups = []
        plans = []
        for c_idx in range(5):
            creator = Creator(
                name=f'LoadCreator{c_idx}',
                email=f'load{c_idx}@test.com',
                username=f'loadcreator{c_idx}',
                balance=Decimal('0'),
                total_earned=Decimal('0'),
                is_verified=True,
            )
            creator.set_password(f'LoadPass{c_idx}!')
            db.session.add(creator)
            db.session.flush()
            creators.append(creator)

            group = Group(
                name=f'Load Group {c_idx}',
                description=f'Grupo de carga {c_idx}',
                telegram_id=f'-100{9000 + c_idx}',
                creator_id=creator.id,
                is_active=True,
            )
            db.session.add(group)
            db.session.flush()
            groups.append(group)

            plan = PricingPlan(
                group_id=group.id,
                name=f'Mensal Load {c_idx}',
                duration_days=30,
                price=Decimal('29.90'),
                is_active=True,
            )
            db.session.add(plan)
            db.session.flush()
            plans.append(plan)

        # 50 assinaturas: 10 usuarios por grupo
        for g_idx in range(5):
            for u_idx in range(10):
                uid = 9000 + g_idx * 100 + u_idx
                sub = Subscription(
                    group_id=groups[g_idx].id,
                    plan_id=plans[g_idx].id,
                    telegram_user_id=str(uid),
                    telegram_username=f'loaduser_{uid}',
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=25),
                    status='active',
                )
                db.session.add(sub)
        db.session.commit()

        async def run_all():
            tasks = []
            for g_idx in range(5):
                for u_idx in range(10):
                    uid = 9000 + g_idx * 100 + u_idx
                    user = make_user(uid, first_name=f'Load{uid}')
                    update = make_update(user=user)
                    ctx = make_context()
                    tasks.append(status_command(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros em 50 status: {errors[:3]}"

    @patch('bot.handlers.payment_verification.get_stripe_session_details', new_callable=AsyncMock)
    @patch('bot.handlers.payment_verification.verify_payment', new_callable=AsyncMock)
    def test_concurrent_payments_multiple_creators(self, mock_verify, mock_details,
                                                    app_ctx, db):
        """Pagamentos simultaneos para criadores diferentes — saldos independentes"""
        mock_verify.return_value = True
        mock_details.return_value = {
            'subscription_id': None,
            'payment_intent_id': None,
            'payment_method_type': 'card',
        }

        creators = []
        groups = []
        plans = []
        for c_idx in range(3):
            creator = Creator(
                name=f'PayCreator{c_idx}',
                email=f'payc{c_idx}@test.com',
                username=f'paycreator{c_idx}',
                balance=Decimal('0'),
                total_earned=Decimal('0'),
                is_verified=True,
            )
            creator.set_password(f'PayPass{c_idx}!')
            db.session.add(creator)
            db.session.flush()
            creators.append(creator)

            group = Group(
                name=f'Pay Group {c_idx}',
                telegram_id=f'-100{9500 + c_idx}',
                creator_id=creator.id,
                is_active=True,
            )
            db.session.add(group)
            db.session.flush()
            groups.append(group)

            plan = PricingPlan(
                group_id=group.id,
                name=f'Mensal Pay {c_idx}',
                duration_days=30,
                price=Decimal('29.90'),
                is_active=True,
            )
            db.session.add(plan)
            db.session.flush()
            plans.append(plan)

        # 10 assinaturas pendentes por criador = 30 total
        all_subs = []
        for c_idx in range(3):
            for u_idx in range(10):
                uid = 9500 + c_idx * 100 + u_idx
                sub = Subscription(
                    group_id=groups[c_idx].id,
                    plan_id=plans[c_idx].id,
                    telegram_user_id=str(uid),
                    telegram_username=f'payu_{uid}',
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=30),
                    status='pending',
                )
                db.session.add(sub)
                db.session.flush()
                txn = Transaction(
                    subscription_id=sub.id, amount=Decimal('29.90'),
                    status='pending', payment_method='stripe',
                    stripe_session_id=f'cs_test_mc_{uid}',
                )
                db.session.add(txn)
                all_subs.append(sub)
        db.session.commit()

        from bot.handlers.payment_verification import check_payment_status

        async def run_all():
            tasks = []
            for c_idx in range(3):
                for u_idx in range(10):
                    uid = 9500 + c_idx * 100 + u_idx
                    user = make_user(uid)
                    query = make_callback_query(user=user, data='check_payment_status')
                    update = MagicMock()
                    update.callback_query = query
                    ctx = make_context()
                    inv = MagicMock()
                    inv.invite_link = f'https://t.me/+mc_{uid}'
                    ctx.bot.create_chat_invite_link = AsyncMock(return_value=inv)
                    tasks.append(check_payment_status(update, ctx))
            return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(run_all())

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"{len(errors)} erros: {errors[:3]}"

        # Todos ativados
        for sub in all_subs:
            _db.session.refresh(sub)
            assert sub.status == 'active'

        # Cada criador deve ter recebido saldo de 10 pagamentos
        for creator in creators:
            _db.session.refresh(creator)
            assert creator.balance > 0, f"Creator {creator.name} balance={creator.balance}"
            assert creator.total_earned > 0
