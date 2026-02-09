# tests/conftest.py
"""
Fixtures compartilhados para todos os testes do TeleVIP
"""
import os
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

# Forçar variáveis de ambiente ANTES de importar a app
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'

from app import create_app, db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal


@pytest.fixture(scope='function')
def app():
    """Cria a aplicação Flask para testes"""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SERVER_NAME': 'localhost',
        'SECRET_KEY': 'test-secret-key-for-testing',
        'RATELIMIT_ENABLED': False,
        'RATELIMIT_STORAGE_URI': 'memory://',
    })
    return app


@pytest.fixture(scope='function')
def db(app):
    """Cria e limpa o banco de dados para cada teste"""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    """Cliente de teste HTTP"""
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def app_context(app, db):
    """Contexto da aplicação"""
    with app.app_context():
        yield app


@pytest.fixture
def creator(db):
    """Cria um criador de teste"""
    user = Creator(
        name='Test Creator',
        email='creator@test.com',
        username='testcreator',
        balance=Decimal('0'),
        total_earned=Decimal('0'),
    )
    user.set_password('TestPass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(db):
    """Cria um admin de teste"""
    user = Creator(
        name='Admin User',
        email='admin@test.com',
        username='adminuser',
        is_admin=True,
        balance=Decimal('0'),
        total_earned=Decimal('0'),
    )
    user.set_password('AdminPass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def second_creator(db):
    """Cria um segundo criador de teste"""
    user = Creator(
        name='Second Creator',
        email='second@test.com',
        username='secondcreator',
        balance=Decimal('100.00'),
        total_earned=Decimal('500.00'),
    )
    user.set_password('SecondPass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def group(db, creator):
    """Cria um grupo de teste"""
    g = Group(
        name='Test Group',
        description='A test group',
        telegram_id='-1001234567890',
        invite_link='https://t.me/+abc123',
        creator_id=creator.id,
        is_active=True,
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def pricing_plan(db, group):
    """Cria um plano de preços de teste"""
    plan = PricingPlan(
        group_id=group.id,
        name='Plano Mensal',
        duration_days=30,
        price=Decimal('49.90'),
        is_active=True,
    )
    db.session.add(plan)
    db.session.commit()
    return plan


@pytest.fixture
def subscription(db, group, pricing_plan):
    """Cria uma assinatura de teste"""
    sub = Subscription(
        group_id=group.id,
        plan_id=pricing_plan.id,
        telegram_user_id='123456789',
        telegram_username='testsubscriber',
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        status='active',
    )
    db.session.add(sub)
    db.session.commit()
    return sub


@pytest.fixture
def transaction(db, subscription):
    """Cria uma transação de teste"""
    txn = Transaction(
        subscription_id=subscription.id,
        amount=Decimal('49.90'),
        status='completed',
        payment_method='stripe',
        stripe_session_id='cs_test_123',
        paid_at=datetime.utcnow(),
    )
    db.session.add(txn)
    db.session.commit()
    return txn


@pytest.fixture
def pending_transaction(db, subscription):
    """Cria uma transação pendente"""
    txn = Transaction(
        subscription_id=subscription.id,
        amount=Decimal('49.90'),
        status='pending',
        payment_method='stripe',
        stripe_session_id='cs_test_pending_456',
    )
    db.session.add(txn)
    db.session.commit()
    return txn


@pytest.fixture
def withdrawal(db, creator):
    """Cria um saque de teste"""
    w = Withdrawal(
        creator_id=creator.id,
        amount=Decimal('50.00'),
        pix_key='12345678901',
        status='pending',
    )
    db.session.add(w)
    db.session.commit()
    return w


def login(client, email, password):
    """Helper para fazer login nos testes"""
    return client.post('/login', data={
        'email': email,
        'password': password,
    }, follow_redirects=True)


def logout(client):
    """Helper para fazer logout"""
    return client.get('/logout', follow_redirects=True)
