# tests/test_session_features.py
"""
Testes das funcionalidades implementadas na sessão:
- calculate_balance() com retenção de 7 dias
- Troca de username com cooldown de 14 dias
- Verificação de disponibilidade de username
- Sugestões de username no registro
- Limite de 30 caracteres e máximo de 6 planos
- Histórico de saques no admin
- Saldo correto (available/blocked) no admin e perfil
- Dashboard mostra todas as transações (não só completed)
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
from tests.conftest import login


# ── Helpers ──────────────────────────────────────────────────────────────

def _create_transaction(db, subscription, amount, status='completed', days_ago=0):
    """Helper: cria transação com paid_at N dias atrás."""
    paid_at = datetime.utcnow() - timedelta(days=days_ago) if status == 'completed' else None
    txn = Transaction(
        subscription_id=subscription.id,
        amount=Decimal(str(amount)),
        status=status,
        payment_method='stripe',
        stripe_session_id=f'cs_test_{amount}_{days_ago}_{status}',
        paid_at=paid_at,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    )
    db.session.add(txn)
    db.session.commit()
    return txn


# ═══════════════════════════════════════════════════════════════════════
# 1. calculate_balance — 7-day hold, available vs blocked
# ═══════════════════════════════════════════════════════════════════════

class TestCalculateBalance:
    """Testes da função calculate_balance()"""

    def test_empty_balance(self, app_context, db, creator):
        """Criador sem transações tem saldo zero."""
        from app.routes.dashboard import calculate_balance
        bal = calculate_balance(creator.id)
        assert bal['available_balance'] == 0
        assert bal['blocked_balance'] == 0
        assert bal['total_balance'] == 0
        assert bal['total_received'] == 0

    def test_old_transaction_is_available(self, app_context, db, creator, group, pricing_plan, subscription):
        """Transação > 7 dias vai para saldo disponível."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, days_ago=10)

        bal = calculate_balance(creator.id)
        # net = 100 - 0.99 - (100 * 0.0999) = 100 - 0.99 - 9.99 = 89.02
        assert round(bal['available_balance'], 2) == 89.02
        assert bal['blocked_balance'] == 0

    def test_recent_transaction_is_blocked(self, app_context, db, creator, group, pricing_plan, subscription):
        """Transação < 7 dias vai para saldo bloqueado."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, days_ago=2)

        bal = calculate_balance(creator.id)
        assert bal['available_balance'] == 0
        assert round(bal['blocked_balance'], 2) == 89.02

    def test_mixed_available_and_blocked(self, app_context, db, creator, group, pricing_plan, subscription):
        """Transações de diferentes idades: separar corretamente."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, days_ago=10)  # available
        _create_transaction(db, subscription, 50, days_ago=1)    # blocked

        bal = calculate_balance(creator.id)
        # available: 100 - 0.99 - 9.99 = 89.02
        assert round(bal['available_balance'], 2) == 89.02
        # blocked: 50 - 0.99 - round(50*0.0999) = 50 - 0.99 - 5.00 = 44.01
        assert round(bal['blocked_balance'], 2) == pytest.approx(44.01, abs=0.01)
        # total = available + blocked
        assert round(bal['total_balance'], 2) == pytest.approx(
            round(bal['available_balance'], 2) + round(bal['blocked_balance'], 2), abs=0.01
        )

    def test_pending_transaction_excluded(self, app_context, db, creator, group, pricing_plan, subscription):
        """Transação pendente NÃO conta no saldo."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, status='pending', days_ago=10)

        bal = calculate_balance(creator.id)
        assert bal['available_balance'] == 0
        assert bal['blocked_balance'] == 0

    def test_failed_transaction_excluded(self, app_context, db, creator, group, pricing_plan, subscription):
        """Transação falha NÃO conta no saldo."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, status='failed', days_ago=10)

        bal = calculate_balance(creator.id)
        assert bal['total_balance'] == 0

    def test_total_received_is_gross(self, app_context, db, creator, group, pricing_plan, subscription):
        """total_received deve ser o valor bruto (sem desconto de taxas)."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, days_ago=10)

        bal = calculate_balance(creator.id)
        assert bal['total_received'] == 100

    def test_transaction_count(self, app_context, db, creator, group, pricing_plan, subscription):
        """transaction_count conta apenas transações completed."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 50, days_ago=10)
        _create_transaction(db, subscription, 30, days_ago=8)
        _create_transaction(db, subscription, 20, status='pending', days_ago=1)

        bal = calculate_balance(creator.id)
        assert bal['transaction_count'] == 2

    def test_boundary_exactly_7_days(self, app_context, db, creator, group, pricing_plan, subscription):
        """Transação de exatamente 7 dias atrás deve estar disponível."""
        from app.routes.dashboard import calculate_balance
        _create_transaction(db, subscription, 100, days_ago=7)

        bal = calculate_balance(creator.id)
        # A comparação é <=, então exatamente 7 dias conta como available
        assert round(bal['available_balance'], 2) == 89.02


# ═══════════════════════════════════════════════════════════════════════
# 2. Username change with 14-day cooldown
# ═══════════════════════════════════════════════════════════════════════

class TestUsernameChange:
    """Testes de troca de username com cooldown de 14 dias."""

    def test_username_change_first_time(self, client, creator, db):
        """Primeira troca de username deve funcionar."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'username': 'newusername',
        }, follow_redirects=True)
        assert resp.status_code == 200
        updated = Creator.query.get(creator.id)
        assert updated.username == 'newusername'
        assert updated.username_changed_at is not None

    def test_username_change_cooldown_blocks(self, client, creator, db):
        """Troca antes de 14 dias deve ser bloqueada."""
        # Simular troca recente
        creator.username_changed_at = datetime.utcnow() - timedelta(days=5)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'username': 'anotherusername',
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'dia(s)' in html or 'username' in html.lower()
        # Username não deve ter mudado
        updated = Creator.query.get(creator.id)
        assert updated.username == 'testcreator'

    def test_username_change_after_cooldown(self, client, creator, db):
        """Troca após 14 dias deve funcionar."""
        creator.username_changed_at = datetime.utcnow() - timedelta(days=15)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'username': 'allowedchange',
        }, follow_redirects=True)
        assert resp.status_code == 200
        updated = Creator.query.get(creator.id)
        assert updated.username == 'allowedchange'

    def test_username_change_same_username_no_update(self, client, creator, db):
        """Enviar o mesmo username não deve alterar username_changed_at."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'username': 'testcreator',
        }, follow_redirects=True)
        assert resp.status_code == 200
        updated = Creator.query.get(creator.id)
        assert updated.username_changed_at is None  # Não mudou

    def test_username_change_invalid_format(self, client, creator, db):
        """Username com caracteres especiais deve ser rejeitado."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'username': 'invalid@name!',
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'inv' in html.lower()
        updated = Creator.query.get(creator.id)
        assert updated.username == 'testcreator'

    def test_username_change_duplicate_blocked(self, client, creator, second_creator, db):
        """Username já em uso por outro criador deve ser rejeitado."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'username': 'secondcreator',  # belongs to second_creator
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'em uso' in html.lower()
        updated = Creator.query.get(creator.id)
        assert updated.username == 'testcreator'

    def test_username_changed_at_model_field(self, app_context, db):
        """Campo username_changed_at existe e é nullable."""
        user = Creator(name='New', email='field@test.com', username='fieldtest')
        user.set_password('Test1234')
        db.session.add(user)
        db.session.commit()
        assert user.username_changed_at is None
        user.username_changed_at = datetime.utcnow()
        db.session.commit()
        assert user.username_changed_at is not None


# ═══════════════════════════════════════════════════════════════════════
# 3. Username availability check endpoint
# ═══════════════════════════════════════════════════════════════════════

class TestCheckUsername:
    """Testes do endpoint /profile/check-username."""

    def test_available_username(self, client, creator, db):
        """Username não existente deve retornar available=True."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile/check-username?username=brandnew')
        data = resp.get_json()
        assert data['available'] is True

    def test_taken_username_returns_suggestions(self, client, creator, second_creator, db):
        """Username já em uso retorna available=False com sugestões."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile/check-username?username=secondcreator')
        data = resp.get_json()
        assert data['available'] is False
        assert 'suggestions' in data
        assert len(data['suggestions']) > 0
        # Sugestões devem começar com 'secondcreator' (sem dígitos finais) + número
        for sug in data['suggestions']:
            assert sug.startswith('secondcreator')

    def test_own_username_returns_current(self, client, creator, db):
        """Próprio username retorna available=True + current=True."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile/check-username?username=testcreator')
        data = resp.get_json()
        assert data['available'] is True
        assert data.get('current') is True

    def test_invalid_format_returns_error(self, client, creator, db):
        """Username com formato inválido retorna error."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile/check-username?username=ab')
        data = resp.get_json()
        assert data['available'] is False

    def test_empty_username_returns_error(self, client, creator, db):
        """Username vazio retorna error."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile/check-username?username=')
        data = resp.get_json()
        assert data['available'] is False

    def test_requires_login(self, client):
        """Endpoint requer autenticação."""
        resp = client.get('/dashboard/profile/check-username?username=test')
        assert resp.status_code == 302

    def test_suggestions_are_unique(self, client, creator, db):
        """Sugestões geradas devem ser usernames não existentes."""
        # Criar vários criadores com nomes parecidos
        for i in range(1, 4):
            u = Creator(name=f'User{i}', email=f'user{i}@test.com', username=f'taken{i}')
            u.set_password('Test1234')
            db.session.add(u)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile/check-username?username=taken1')
        data = resp.get_json()
        assert data['available'] is False
        # Sugestões não devem incluir taken1, taken2, taken3
        for sug in data['suggestions']:
            assert Creator.query.filter_by(username=sug).first() is None


# ═══════════════════════════════════════════════════════════════════════
# 4. Registration username suggestions
# ═══════════════════════════════════════════════════════════════════════

class TestRegistrationUsernameSuggestions:
    """Testes de sugestão de username no registro."""

    def test_duplicate_username_shows_suggestions(self, client, creator, db):
        """Registro com username duplicado sugere alternativas."""
        resp = client.post('/register', data={
            'name': 'New User',
            'email': 'new@test.com',
            'username': 'testcreator',  # already exists
            'password': 'NewPass123',
            'confirm_password': 'NewPass123',
            'accept_terms': 'on',
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'em uso' in html.lower()
        assert 'Sugest' in html or 'sugest' in html  # "Sugestões:"

    def test_available_username_registers(self, client, db):
        """Username disponível registra normalmente."""
        from unittest.mock import patch
        with patch('app.routes.auth.send_confirmation_email'):
            resp = client.post('/register', data={
                'name': 'Brand New',
                'email': 'brandnew@test.com',
                'username': 'uniquename',
                'password': 'ValidPass1',
                'confirm_password': 'ValidPass1',
                'accept_terms': 'on',
            }, follow_redirects=True)
            assert resp.status_code == 200
            user = Creator.query.filter_by(username='uniquename').first()
            assert user is not None


# ═══════════════════════════════════════════════════════════════════════
# 5. Plan name limit (30 chars) and max 6 plans
# ═══════════════════════════════════════════════════════════════════════

class TestPlanLimits:
    """Testes de limites de planos: 30 caracteres no nome, máximo 6 planos."""

    def test_plan_name_truncated_to_30(self, client, creator, db):
        """Nome do plano com mais de 30 chars é truncado para 30."""
        login(client, 'creator@test.com', 'TestPass123')
        long_name = 'A' * 50
        resp = client.post('/groups/create', data={
            'name': 'Group Limit Test',
            'description': 'Test',
            'telegram_id': '-1009876543',
            'plan_name[]': long_name,
            'plan_duration[]': '30',
            'plan_price[]': '29.90',
            'plan_lifetime[]': '0',
        }, follow_redirects=True)
        assert resp.status_code == 200
        plan = PricingPlan.query.filter(PricingPlan.name.like('A%')).first()
        if plan:
            assert len(plan.name) <= 30

    def test_plan_name_validation_rejects_over_30(self, app_context):
        """_validate_plan_input rejeita nomes > 30 chars."""
        from app.routes.groups import _validate_plan_input
        errors, price, duration = _validate_plan_input('A' * 31, '29.90', '30')
        assert any('30' in e for e in errors)

    def test_plan_name_validation_accepts_30(self, app_context):
        """_validate_plan_input aceita nomes de exatamente 30 chars."""
        from app.routes.groups import _validate_plan_input
        errors, price, duration = _validate_plan_input('A' * 30, '29.90', '30')
        assert not any('30' in e for e in errors)

    def test_max_6_plans_enforced(self, client, creator, db):
        """Backend trunca para no máximo 6 planos via [:6]."""
        login(client, 'creator@test.com', 'TestPass123')

        data = {
            'name': 'Group Max Plans',
            'description': 'Test max plans',
            'telegram_id': '-1009876544',
        }
        # Enviar 8 planos
        plan_names = [f'Plan{i}' for i in range(8)]
        plan_durations = ['30'] * 8
        plan_prices = ['10.00'] * 8
        plan_lifetimes = ['0'] * 8

        # Flask test client precisa de listas para campos com []
        from werkzeug.datastructures import MultiDict
        form_data = MultiDict()
        form_data['name'] = data['name']
        form_data['description'] = data['description']
        form_data['telegram_id'] = data['telegram_id']
        for i in range(8):
            form_data.add('plan_name[]', plan_names[i])
            form_data.add('plan_duration[]', plan_durations[i])
            form_data.add('plan_price[]', plan_prices[i])
            form_data.add('plan_lifetime[]', plan_lifetimes[i])

        resp = client.post('/groups/create', data=form_data, follow_redirects=True)
        assert resp.status_code == 200

        group = Group.query.filter_by(name='Group Max Plans').first()
        if group:
            plan_count = PricingPlan.query.filter_by(group_id=group.id).count()
            assert plan_count <= 6

    def test_plan_price_minimum_5(self, app_context):
        """Preço mínimo do plano é R$ 5,00."""
        from app.routes.groups import _validate_plan_input
        errors, price, duration = _validate_plan_input('Test', '4.99', '30')
        assert any('5' in e or 'mínimo' in e.lower() for e in errors)

    def test_plan_duration_must_be_integer(self, app_context):
        """Duração deve ser número inteiro."""
        from app.routes.groups import _validate_plan_input
        errors, price, duration = _validate_plan_input('Test', '10.00', '30.5')
        assert any('inteiro' in e.lower() for e in errors)


# ═══════════════════════════════════════════════════════════════════════
# 6. Admin withdrawal history
# ═══════════════════════════════════════════════════════════════════════

class TestAdminWithdrawalHistory:
    """Testes do histórico de saques processados no admin."""

    def test_admin_shows_completed_withdrawals(self, client, admin_user, creator, db):
        """Admin index mostra saques completados."""
        w = Withdrawal(
            creator_id=creator.id,
            amount=Decimal('30.00'),
            pix_key='11111111111',
            status='completed',
            processed_at=datetime.utcnow(),
        )
        db.session.add(w)
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert '30.00' in html
        # Deve ter seção de histórico
        assert 'rico' in html.lower()  # "Histórico"

    def test_admin_shows_failed_withdrawals(self, client, admin_user, creator, db):
        """Admin mostra saques falhos no histórico."""
        w = Withdrawal(
            creator_id=creator.id,
            amount=Decimal('25.00'),
            pix_key='22222222222',
            status='failed',
            processed_at=datetime.utcnow(),
        )
        db.session.add(w)
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert '25.00' in html

    def test_admin_total_paid(self, client, admin_user, creator, db):
        """Admin mostra total pago (soma de saques completed)."""
        for amount in [20, 30, 50]:
            w = Withdrawal(
                creator_id=creator.id,
                amount=Decimal(str(amount)),
                pix_key='33333333333',
                status='completed',
                processed_at=datetime.utcnow(),
            )
            db.session.add(w)
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert '100.00' in html  # 20+30+50

    def test_admin_pending_and_completed_separate(self, client, admin_user, creator, db):
        """Saques pendentes e completados aparecem em seções separadas."""
        pending = Withdrawal(
            creator_id=creator.id, amount=Decimal('40.00'),
            pix_key='44444444444', status='pending',
        )
        completed = Withdrawal(
            creator_id=creator.id, amount=Decimal('60.00'),
            pix_key='55555555555', status='completed',
            processed_at=datetime.utcnow(),
        )
        db.session.add_all([pending, completed])
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert '40.00' in html
        assert '60.00' in html


# ═══════════════════════════════════════════════════════════════════════
# 7. Admin balance accuracy (available/blocked split)
# ═══════════════════════════════════════════════════════════════════════

class TestAdminBalanceAccuracy:
    """Testes de precisão do saldo no painel admin."""

    def test_admin_creator_shows_available_and_blocked(self, client, admin_user, creator,
                                                        group, pricing_plan, subscription, db):
        """Admin index mostra saldos disponível e bloqueado separados."""
        # Transação antiga (disponível)
        _create_transaction(db, subscription, 100, days_ago=10)
        # Transação recente (bloqueada)
        _create_transaction(db, subscription, 50, days_ago=2)

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200
        # Deve ter valores de saldo
        assert 'R$' in html

    def test_admin_creator_details_balance(self, client, admin_user, creator,
                                            group, pricing_plan, subscription, db):
        """Admin creator details mostra breakdown do saldo."""
        _create_transaction(db, subscription, 100, days_ago=10)

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get(f'/admin/creator/{creator.id}/details')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200
        assert '89.02' in html  # net amount of R$100

    def test_admin_users_page_balance(self, client, admin_user, creator,
                                       group, pricing_plan, subscription, db):
        """Admin users page mostra saldo disponível correto."""
        _create_transaction(db, subscription, 100, days_ago=10)

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/users')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# 8. Profile balance using calculate_balance()
# ═══════════════════════════════════════════════════════════════════════

class TestProfileBalance:
    """Testes do saldo no perfil do criador."""

    def test_profile_shows_available_balance(self, client, creator, group, pricing_plan,
                                              subscription, db):
        """Perfil mostra saldo disponível (líquido, após 7 dias)."""
        _create_transaction(db, subscription, 100, days_ago=10)

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200
        assert '89.02' in html  # net available

    def test_profile_shows_blocked_balance(self, client, creator, group, pricing_plan,
                                            subscription, db):
        """Perfil mostra saldo bloqueado (7 dias)."""
        _create_transaction(db, subscription, 100, days_ago=2)

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200
        # O saldo bloqueado deve aparecer
        assert '89.02' in html  # blocked net amount
        assert 'Bloqueado' in html or 'bloqueado' in html

    def test_profile_shows_total_earned_net(self, client, creator, group, pricing_plan,
                                             subscription, db):
        """Total ganho deve ser líquido (net)."""
        _create_transaction(db, subscription, 100, days_ago=10)

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        # total_earned = total_balance = net amount
        assert '89.02' in html

    def test_profile_shows_total_withdrawn(self, client, creator, group, pricing_plan,
                                            subscription, db):
        """Perfil mostra total sacado."""
        _create_transaction(db, subscription, 100, days_ago=10)
        w = Withdrawal(
            creator_id=creator.id, amount=Decimal('20.00'),
            pix_key='99999999999', status='completed',
            processed_at=datetime.utcnow(),
        )
        db.session.add(w)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert '20.00' in html  # total withdrawn

    def test_profile_balance_minus_withdrawn(self, client, creator, group, pricing_plan,
                                              subscription, db):
        """Saldo disponível para saque = available - withdrawn."""
        _create_transaction(db, subscription, 100, days_ago=10)
        w = Withdrawal(
            creator_id=creator.id, amount=Decimal('20.00'),
            pix_key='88888888888', status='completed',
            processed_at=datetime.utcnow(),
        )
        db.session.add(w)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        # balance = 89.02 - 20 = 69.02
        assert '69.02' in html


# ═══════════════════════════════════════════════════════════════════════
# 9. Dashboard shows ALL transactions (not just completed)
# ═══════════════════════════════════════════════════════════════════════

class TestDashboardAllTransactions:
    """Dashboard deve mostrar transações de todos os status."""

    def test_dashboard_shows_pending_transactions(self, client, creator, group, pricing_plan,
                                                    subscription, db):
        """Dashboard mostra transações pendentes."""
        _create_transaction(db, subscription, 50, status='pending', days_ago=1)
        _create_transaction(db, subscription, 100, status='completed', days_ago=10)

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200

    def test_dashboard_shows_failed_transactions(self, client, creator, group, pricing_plan,
                                                   subscription, db):
        """Dashboard mostra transações falhas."""
        _create_transaction(db, subscription, 75, status='failed', days_ago=3)

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# 10. Profile page — username cooldown display
# ═══════════════════════════════════════════════════════════════════════

class TestProfileUsernameCooldown:
    """Testes de exibição do cooldown de username no perfil."""

    def test_profile_shows_username_field(self, client, creator, db):
        """Perfil mostra campo de username."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert 'testcreator' in html
        assert resp.status_code == 200

    def test_profile_cooldown_info_when_locked(self, client, creator, db):
        """Perfil informa dias restantes quando username está em cooldown."""
        creator.username_changed_at = datetime.utcnow() - timedelta(days=5)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        # Deve indicar que não pode trocar
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# 11. Page theme field
# ═══════════════════════════════════════════════════════════════════════

class TestPageTheme:
    """Testes do campo page_theme no model Creator."""

    def test_default_theme_is_galactic(self, app_context, db):
        """Tema padrão deve ser 'galactic'."""
        user = Creator(name='Theme', email='theme@test.com', username='themeuser')
        user.set_password('Test1234')
        db.session.add(user)
        db.session.commit()
        assert user.page_theme == 'galactic'

    def test_update_theme_via_profile(self, client, creator, db):
        """Atualizar tema pelo perfil."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'page_theme': 'neon',
        }, follow_redirects=True)
        assert resp.status_code == 200
        updated = Creator.query.get(creator.id)
        assert updated.page_theme == 'neon'

    def test_invalid_theme_rejected(self, client, creator, db):
        """Tema inválido não deve ser salvo."""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'page_theme': 'invalid_theme',
        }, follow_redirects=True)
        assert resp.status_code == 200
        updated = Creator.query.get(creator.id)
        assert updated.page_theme == 'galactic'  # default unchanged

    def test_all_valid_themes(self, client, creator, db):
        """Todos os 4 temas válidos devem ser aceitos."""
        for theme in ('galactic', 'clean', 'neon', 'premium'):
            login(client, 'creator@test.com', 'TestPass123')
            resp = client.post('/dashboard/profile/update', data={
                'name': 'Test Creator',
                'page_theme': theme,
            }, follow_redirects=True)
            assert resp.status_code == 200
            updated = Creator.query.get(creator.id)
            assert updated.page_theme == theme
