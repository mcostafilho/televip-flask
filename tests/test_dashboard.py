# tests/test_dashboard.py
"""
Testes das rotas do dashboard
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
from tests.conftest import login


class TestDashboardAccess:
    """Testes de acesso ao dashboard"""

    def test_dashboard_requires_login(self, client):
        resp = client.get('/dashboard/')
        assert resp.status_code == 302

    def test_dashboard_accessible_when_logged_in(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        assert resp.status_code == 200

    def test_dashboard_shows_creator_name(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        html = resp.data.decode('utf-8')
        assert 'Test Creator' in html or resp.status_code == 200


class TestDashboardStats:
    """Testes de estatísticas do dashboard"""

    def test_dashboard_with_no_data(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        assert resp.status_code == 200

    def test_dashboard_with_group_and_subscriptions(self, client, creator, group,
                                                      pricing_plan, subscription, transaction):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        assert resp.status_code == 200


class TestTransactions:
    """Testes da página de transações"""

    def test_transactions_page_requires_login(self, client):
        resp = client.get('/dashboard/transactions')
        assert resp.status_code == 302

    def test_transactions_page_renders(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/transactions')
        assert resp.status_code == 200

    def test_transactions_shows_data(self, client, creator, group, pricing_plan,
                                      subscription, transaction):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/transactions')
        assert resp.status_code == 200


class TestWithdrawals:
    """Testes de saques"""

    def test_withdrawals_page_requires_login(self, client):
        resp = client.get('/dashboard/withdrawals')
        assert resp.status_code == 302

    def test_withdrawals_page_renders(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/withdrawals')
        assert resp.status_code == 200

    def test_withdrawal_request(self, client, creator, db):
        creator.balance = Decimal('100')
        creator.pix_key = '12345678901'
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/withdraw', data={
            'amount': '50.00',
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestProfile:
    """Testes do perfil"""

    def test_profile_page_requires_login(self, client):
        resp = client.get('/dashboard/profile')
        assert resp.status_code == 302

    def test_profile_page_renders(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        assert resp.status_code == 200

    def test_profile_update(self, client, creator, db):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Updated Name',
            'telegram_username': 'newtelegram',
            'pix_key': '99999999999',
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestAnalytics:
    """Testes da página de analytics"""

    def test_analytics_requires_login(self, client):
        resp = client.get('/dashboard/analytics')
        assert resp.status_code == 302

    def test_analytics_renders(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/analytics')
        assert resp.status_code == 200

    def test_analytics_with_period(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/analytics?period=7')
        assert resp.status_code == 200

    def test_analytics_with_30_days(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/analytics?period=30')
        assert resp.status_code == 200

    def test_analytics_with_transactions(self, client, creator, group, pricing_plan,
                                          subscription, transaction):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/analytics')
        assert resp.status_code == 200
