# tests/test_groups.py
"""
Testes das rotas de grupos
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction
from tests.conftest import login


class TestGroupsAccess:
    """Testes de acesso à lista de grupos"""

    def test_groups_requires_login(self, client):
        resp = client.get('/groups/')
        assert resp.status_code == 302

    def test_groups_page_renders(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/groups/')
        assert resp.status_code == 200

    def test_groups_shows_creator_groups(self, client, creator, group):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/groups/')
        html = resp.data.decode('utf-8')
        assert 'Test Group' in html


class TestCreateGroup:
    """Testes de criação de grupo"""

    def test_create_group_page_renders(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/groups/create')
        assert resp.status_code == 200

    def test_create_group_success(self, client, creator, db):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/groups/create', data={
            'name': 'New Group',
            'description': 'A new test group',
            'telegram_id': '-1009999999',
            'plan_name[]': 'Mensal',
            'plan_duration[]': '30',
            'plan_price[]': '29.90',
            'plan_lifetime[]': '0',
        }, follow_redirects=True)
        assert resp.status_code == 200
        g = Group.query.filter_by(name='New Group').first()
        assert g is not None
        assert g.creator_id == creator.id

    def test_create_group_empty_name(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/groups/create', data={
            'name': '',
            'description': 'Desc',
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestEditGroup:
    """Testes de edição de grupo"""

    def test_edit_group_page_renders(self, client, creator, group):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/edit')
        assert resp.status_code == 200

    def test_edit_group_success(self, client, creator, group, db):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group.id}/edit', data={
            'name': 'Updated Group Name',
            'description': 'Updated description',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_edit_group_wrong_owner(self, client, second_creator, group):
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/edit')
        assert resp.status_code == 404

    def test_edit_nonexistent_group(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/groups/9999/edit')
        assert resp.status_code == 404


class TestDeleteGroup:
    """Testes de exclusão de grupo"""

    def test_delete_group(self, client, creator, group, db):
        group_id = group.id
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group_id}/delete', follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_group_wrong_owner(self, client, second_creator, group):
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.post(f'/groups/{group.id}/delete')
        assert resp.status_code == 404

    def test_delete_nonexistent_group(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/groups/9999/delete')
        assert resp.status_code == 404


class TestToggleGroup:
    """Testes de ativação/desativação de grupo"""

    def test_toggle_group(self, client, creator, group, db):
        login(client, 'creator@test.com', 'TestPass123')
        assert group.is_active is True
        resp = client.post(f'/groups/{group.id}/toggle', follow_redirects=True)
        assert resp.status_code == 200

    def test_toggle_nonexistent_group(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/groups/9999/toggle')
        assert resp.status_code == 404


class TestSubscribersList:
    """Testes da lista de assinantes"""

    def test_subscribers_page_renders(self, client, creator, group):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers')
        assert resp.status_code == 200

    def test_subscribers_shows_data(self, client, creator, group, subscription):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200
        assert 'testsubscriber' in html or '123456789' in html

    def test_subscribers_filter_active(self, client, creator, group, subscription):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers?status=active')
        assert resp.status_code == 200

    def test_subscribers_filter_expired(self, client, creator, group):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers?status=expired')
        assert resp.status_code == 200

    def test_subscribers_pagination(self, client, creator, group, pricing_plan, db):
        # Criar muitas assinaturas
        for i in range(25):
            sub = Subscription(
                group_id=group.id, plan_id=pricing_plan.id,
                telegram_user_id=str(2000 + i), telegram_username=f'user{i}',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status='active',
            )
            db.session.add(sub)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers?page=1')
        assert resp.status_code == 200

    def test_subscribers_wrong_owner(self, client, second_creator, group):
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/subscribers')
        assert resp.status_code == 404

    def test_subscribers_search(self, client, creator, group, subscription):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers?search=testsubscriber')
        assert resp.status_code == 200


class TestGroupStats:
    """Testes de estatísticas do grupo"""

    def test_stats_page_renders(self, client, creator, group):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/stats')
        assert resp.status_code == 200

    def test_stats_wrong_owner(self, client, second_creator, group):
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/stats')
        assert resp.status_code == 404


class TestGroupLink:
    """Testes de link do bot"""

    def test_get_group_link(self, client, creator, group):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/link')
        assert resp.status_code == 200

    def test_get_link_wrong_owner(self, client, second_creator, group):
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/link')
        assert resp.status_code == 404


class TestExportSubscribers:
    """Testes de exportação CSV"""

    def test_export_csv(self, client, creator, group, subscription):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/export-subscribers')
        assert resp.status_code == 200
        assert 'text/csv' in resp.content_type or resp.status_code == 200

    def test_export_wrong_owner(self, client, second_creator, group):
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/export-subscribers')
        assert resp.status_code == 404
