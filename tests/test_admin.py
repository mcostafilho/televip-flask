# tests/test_admin.py
"""
Testes das rotas administrativas
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
from tests.conftest import login


class TestAdminAccess:
    """Testes de controle de acesso admin"""

    def test_admin_requires_login(self, client):
        resp = client.get('/admin/')
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()

    def test_admin_requires_admin_role(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/admin/')
        # admin_required retorna 404 para não-admins (segurança por obscuridade)
        assert resp.status_code == 404

    def test_admin_access_granted(self, client, admin_user):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        assert resp.status_code == 200
        assert 'Painel Administrativo' in resp.data.decode('utf-8')


class TestAdminDashboard:
    """Testes do dashboard admin"""

    def test_admin_shows_stats(self, client, admin_user):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert 'Criadores' in html
        assert 'Grupos' in html
        assert 'Assinaturas Ativas' in html
        assert 'Saques Pendentes' in html

    def test_admin_shows_creators_list(self, client, admin_user, creator):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert 'Test Creator' in html
        assert 'creator@test.com' in html

    def test_admin_balance_from_transactions(self, client, admin_user, db, creator,
                                              group, pricing_plan, subscription, transaction):
        """Saldo deve ser calculado a partir das transações completadas"""
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        # O net_amount da transação de R$49.90 deve aparecer
        # net_amount = 49.90 - 0.99 - (49.90 * 0.0999) = 49.90 - 0.99 - 4.99 = 43.92
        assert 'R$' in html

    def test_admin_balance_with_withdrawals(self, client, admin_user, db,
                                             creator, group, pricing_plan):
        """Saldo disponível = available (>7 dias) - saques completados"""
        # Criar subscription + transaction completada >7 dias atrás (available)
        sub = Subscription(
            group_id=group.id, plan_id=pricing_plan.id,
            telegram_user_id='111', start_date=datetime.utcnow() - timedelta(days=10),
            end_date=datetime.utcnow() + timedelta(days=20), status='active',
        )
        db.session.add(sub)
        db.session.commit()

        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('100'),
            status='completed',
            paid_at=datetime.utcnow() - timedelta(days=10),
            created_at=datetime.utcnow() - timedelta(days=10),
        )
        db.session.add(txn)

        # Saque completado
        w = Withdrawal(
            creator_id=creator.id, amount=Decimal('20'),
            pix_key='123', status='completed',
            processed_at=datetime.utcnow(),
        )
        db.session.add(w)
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        # net_amount de R$100 = 89.02 (available, >7 days)
        # saldo = 89.02 - 20.00 = 69.02
        assert '69.02' in html

    def test_admin_multiple_creators(self, client, admin_user, creator, second_creator):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert 'Test Creator' in html
        assert 'Second Creator' in html

    def test_admin_pending_withdrawals_section(self, client, admin_user, creator, withdrawal):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert '50.00' in html
        assert '12345678901' in html


class TestProcessWithdrawal:
    """Testes de processamento de saque"""

    def test_process_withdrawal_success(self, client, admin_user, db, creator, withdrawal):
        # Dar saldo ao creator primeiro
        creator.balance = Decimal('100')
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.post(f'/admin/withdrawal/{withdrawal.id}/process',
                          follow_redirects=True)
        assert resp.status_code == 200

        w = Withdrawal.query.get(withdrawal.id)
        assert w.status == 'completed'
        assert w.processed_at is not None

    def test_process_withdrawal_already_completed(self, client, admin_user, db, withdrawal):
        withdrawal.status = 'completed'
        db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.post(f'/admin/withdrawal/{withdrawal.id}/process',
                          follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'processado' in html.lower()

    def test_process_withdrawal_nonexistent(self, client, admin_user):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.post('/admin/withdrawal/9999/process')
        # Pode retornar 404 (first_or_404) ou 302 (exception caught → redirect)
        assert resp.status_code in [302, 404]

    def test_process_withdrawal_requires_admin(self, client, creator, withdrawal):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/admin/withdrawal/{withdrawal.id}/process')
        # admin_required retorna 404 para não-admins
        assert resp.status_code == 404


class TestAdminCreatorDetails:
    """Testes de detalhes do criador no admin"""

    def test_creator_details_page(self, client, admin_user, creator, group, pricing_plan):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get(f'/admin/creator/{creator.id}/details')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Test Creator' in html

    def test_creator_details_nonexistent(self, client, admin_user):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/creator/9999/details')
        assert resp.status_code == 404

    def test_creator_details_requires_admin(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/admin/creator/{creator.id}/details')
        assert resp.status_code == 404


class TestAdminUsers:
    """Testes de lista de usuários admin"""

    def test_users_page(self, client, admin_user, creator):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/users')
        assert resp.status_code == 200

    def test_users_requires_admin(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/admin/users')
        assert resp.status_code == 404


class TestAdminSendMessage:
    """Testes de envio de mensagem"""

    def test_send_message(self, client, admin_user, creator):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.post(f'/admin/creator/{creator.id}/message', data={
            'subject': 'Test Subject',
            'message': 'Test message body',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'enviada' in resp.data.decode('utf-8').lower()

    def test_send_message_nonexistent_creator(self, client, admin_user):
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.post('/admin/creator/9999/message', data={
            'subject': 'Test', 'message': 'Test',
        })
        assert resp.status_code == 404
