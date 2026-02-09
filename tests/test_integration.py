# tests/test_integration.py
"""
Testes de integração - fluxos completos end-to-end
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
from app.routes.webhooks import handle_checkout_session_completed
from tests.conftest import login


class TestFullPaymentFlow:
    """Teste do fluxo completo de pagamento via webhook"""

    def test_payment_creates_subscription_and_updates_balance(self, app_context, db):
        """Fluxo: criador -> grupo -> plano -> assinatura -> transação -> webhook -> saldo"""
        # 1. Criar criador
        creator = Creator(name='Flow Creator', email='flow@test.com', username='flowcreator')
        creator.set_password('FlowPass1')
        db.session.add(creator)
        db.session.commit()

        assert creator.balance == 0 or creator.balance == Decimal('0')

        # 2. Criar grupo
        group = Group(name='Flow Group', creator_id=creator.id,
                     telegram_id='-100flow', is_active=True)
        db.session.add(group)
        db.session.commit()

        # 3. Criar plano
        plan = PricingPlan(group_id=group.id, name='Mensal',
                          duration_days=30, price=Decimal('100.00'))
        db.session.add(plan)
        db.session.commit()

        # 4. Criar assinatura pendente
        sub = Subscription(
            group_id=group.id, plan_id=plan.id,
            telegram_user_id='12345',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        db.session.add(sub)
        db.session.commit()

        # 5. Criar transação pendente
        txn = Transaction(
            subscription_id=sub.id,
            amount=Decimal('100'),
            status='pending',
            stripe_session_id='cs_flow_test',
        )
        db.session.add(txn)
        db.session.commit()

        assert txn.net_amount == Decimal('91.02')

        # 6. Simular webhook do Stripe
        session = {
            'id': 'cs_flow_test',
            'payment_status': 'paid',
            'payment_intent': 'pi_flow_123',
            'customer_email': 'subscriber@test.com',
            'metadata': {
                'transaction_id': str(txn.id),
                'subscription_id': str(sub.id),
            },
        }
        handle_checkout_session_completed(session)

        # 7. Verificar resultados
        updated_txn = Transaction.query.get(txn.id)
        assert updated_txn.status == 'completed'
        assert updated_txn.paid_at is not None

        updated_sub = Subscription.query.get(sub.id)
        assert updated_sub.status == 'active'

        updated_creator = Creator.query.get(creator.id)
        assert updated_creator.balance == Decimal('91.02')
        assert updated_creator.total_earned == Decimal('91.02')

    def test_multiple_payments_accumulate_balance(self, app_context, db):
        """Múltiplas transações devem acumular no saldo do criador"""
        creator = Creator(name='Multi', email='multi@test.com', username='multi')
        creator.set_password('MultiPass1')
        db.session.add(creator)
        db.session.commit()

        group = Group(name='Multi Group', creator_id=creator.id,
                     telegram_id='-100multi')
        db.session.add(group)
        db.session.commit()

        plan = PricingPlan(group_id=group.id, name='Plan',
                          duration_days=30, price=Decimal('50'))
        db.session.add(plan)
        db.session.commit()

        total_expected = Decimal('0')

        for i in range(5):
            sub = Subscription(
                group_id=group.id, plan_id=plan.id,
                telegram_user_id=str(5000 + i),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status='pending',
            )
            db.session.add(sub)
            db.session.commit()

            txn = Transaction(
                subscription_id=sub.id,
                amount=Decimal('50'),
                status='pending',
            )
            db.session.add(txn)
            db.session.commit()
            total_expected += txn.net_amount

            session = {
                'id': f'cs_multi_{i}',
                'payment_status': 'paid',
                'payment_intent': f'pi_multi_{i}',
                'metadata': {
                    'transaction_id': str(txn.id),
                    'subscription_id': str(sub.id),
                },
            }
            handle_checkout_session_completed(session)

        updated_creator = Creator.query.get(creator.id)
        assert updated_creator.balance == total_expected
        assert updated_creator.total_earned == total_expected


class TestWithdrawalFlow:
    """Teste do fluxo de saque"""

    def test_withdrawal_reduces_balance_on_process(self, client, admin_user, db):
        # Criar criador com saldo
        creator = Creator(name='Withdraw', email='withdraw@test.com', username='withdraw')
        creator.set_password('WithPass1')
        creator.balance = Decimal('200.00')
        creator.total_earned = Decimal('200.00')
        db.session.add(creator)
        db.session.commit()

        # Criar saque
        w = Withdrawal(creator_id=creator.id, amount=Decimal('100'),
                       pix_key='123', status='pending')
        db.session.add(w)
        db.session.commit()

        # Admin processa
        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.post(f'/admin/withdrawal/{w.id}/process', follow_redirects=True)
        assert resp.status_code == 200

        updated = Creator.query.get(creator.id)
        assert updated.balance == Decimal('100.00')


class TestCreatorDashboardFlow:
    """Teste do fluxo completo do criador"""

    def test_creator_full_workflow(self, client, db, app_context):
        """Registro -> criar grupo -> ver dashboard -> ver analytics"""
        # 1. Registro
        resp = client.post('/register', data={
            'name': 'Flow Test',
            'email': 'flowtest@test.com',
            'username': 'flowtest',
            'password': 'FlowTest1',
            'confirm_password': 'FlowTest1',
        }, follow_redirects=True)
        assert resp.status_code == 200

        # 2. Dashboard
        resp = client.get('/dashboard/')
        assert resp.status_code == 200

        # 3. Criar grupo
        resp = client.post('/groups/create', data={
            'name': 'Workflow Group',
            'description': 'Test workflow',
            'telegram_id': '-100workflow',
            'skip_validation': 'on',
        }, follow_redirects=True)
        assert resp.status_code == 200

        # 4. Ver lista de grupos
        resp = client.get('/groups/')
        assert resp.status_code == 200
        assert 'Workflow Group' in resp.data.decode('utf-8')

        # 5. Analytics
        resp = client.get('/dashboard/analytics')
        assert resp.status_code == 200

        # 6. Profile
        resp = client.get('/dashboard/profile')
        assert resp.status_code == 200

        # 7. Transactions
        resp = client.get('/dashboard/transactions')
        assert resp.status_code == 200

        # 8. Logout
        resp = client.get('/logout', follow_redirects=True)
        assert resp.status_code == 200


class TestAdminViewsMultipleCreators:
    """Teste da visão admin com múltiplos criadores e dados"""

    def test_admin_sees_all_data(self, client, admin_user, db):
        # Criar 3 criadores com grupos e transações
        for i in range(3):
            c = Creator(name=f'Creator {i}', email=f'c{i}@test.com',
                       username=f'creator{i}')
            c.set_password('Pass1234')
            db.session.add(c)
            db.session.commit()

            g = Group(name=f'Group {i}', creator_id=c.id,
                     telegram_id=f'-100admin{i}')
            db.session.add(g)
            db.session.commit()

            plan = PricingPlan(group_id=g.id, name='Plan',
                              duration_days=30, price=Decimal('100'))
            db.session.add(plan)
            db.session.commit()

            sub = Subscription(
                group_id=g.id, plan_id=plan.id,
                telegram_user_id=str(8000 + i),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status='active',
            )
            db.session.add(sub)
            db.session.commit()

            txn = Transaction(
                subscription_id=sub.id,
                amount=Decimal('100'),
                status='completed',
                paid_at=datetime.utcnow(),
            )
            db.session.add(txn)
            db.session.commit()

        login(client, 'admin@test.com', 'AdminPass123')
        resp = client.get('/admin/')
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200

        # Deve mostrar todos os criadores
        for i in range(3):
            assert f'Creator {i}' in html


class TestDataIsolation:
    """Testa que criadores só veem seus próprios dados"""

    def test_creator_cant_see_others_groups(self, client, db):
        c1 = Creator(name='Owner', email='owner@test.com', username='owner')
        c1.set_password('Owner123')
        db.session.add(c1)
        db.session.commit()

        c2 = Creator(name='Other', email='other@test.com', username='other')
        c2.set_password('Other123')
        db.session.add(c2)
        db.session.commit()

        g = Group(name='Private Group', creator_id=c1.id, telegram_id='-100iso')
        db.session.add(g)
        db.session.commit()

        # c2 tenta ver grupo de c1
        login(client, 'other@test.com', 'Other123')
        resp = client.get(f'/groups/{g.id}/edit')
        assert resp.status_code == 404

        resp = client.get(f'/groups/{g.id}/subscribers')
        assert resp.status_code == 404

        resp = client.get(f'/groups/{g.id}/stats')
        assert resp.status_code == 404

    def test_creator_cant_delete_others_groups(self, client, db):
        c1 = Creator(name='Owner2', email='owner2@test.com', username='owner2')
        c1.set_password('Owner123')
        db.session.add(c1)
        db.session.commit()

        c2 = Creator(name='Other2', email='other2@test.com', username='other2')
        c2.set_password('Other123')
        db.session.add(c2)
        db.session.commit()

        g = Group(name='Dont Delete', creator_id=c1.id, telegram_id='-100isodel')
        db.session.add(g)
        db.session.commit()

        login(client, 'other2@test.com', 'Other123')
        resp = client.post(f'/groups/{g.id}/delete')
        assert resp.status_code == 404

        # Grupo ainda deve existir
        assert Group.query.get(g.id) is not None
