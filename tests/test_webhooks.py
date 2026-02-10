# tests/test_webhooks.py
"""
Testes das rotas de webhook
"""
import pytest
import json
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction
from app.routes.webhooks import handle_checkout_session_completed


class TestStripeWebhook:
    """Testes do webhook do Stripe"""

    def test_webhook_requires_signature(self, client):
        resp = client.post('/webhooks/stripe',
                          data=b'{}',
                          content_type='application/json')
        # Sem assinatura, deve retornar erro
        assert resp.status_code in [400, 500]

    def test_webhook_invalid_payload(self, client):
        resp = client.post('/webhooks/stripe',
                          data=b'invalid json',
                          content_type='application/json')
        assert resp.status_code in [400, 500]

    def test_telegram_webhook_returns_ok(self, client):
        resp = client.post('/webhooks/telegram',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'ok'


class TestHandleCheckoutCompleted:
    """Testes da função handle_checkout_session_completed"""

    def test_skip_unpaid_session(self, app_context, db):
        session = {
            'id': 'cs_test_1',
            'payment_status': 'unpaid',
            'metadata': {},
        }
        # Não deve levantar erro, apenas retornar
        handle_checkout_session_completed(session)

    def test_skip_empty_metadata(self, app_context, db):
        session = {
            'id': 'cs_test_2',
            'payment_status': 'paid',
            'metadata': {},
        }
        handle_checkout_session_completed(session)

    def test_skip_nonexistent_transaction(self, app_context, db):
        session = {
            'id': 'cs_test_3',
            'payment_status': 'paid',
            'metadata': {'transaction_id': '99999'},
        }
        handle_checkout_session_completed(session)

    def test_successful_checkout_updates_transaction(self, app_context, db,
                                                      creator, group, pricing_plan):
        # Criar subscription e transaction pendente
        sub = Subscription(
            group_id=group.id, plan_id=pricing_plan.id,
            telegram_user_id='777',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        db.session.add(sub)
        db.session.commit()

        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('100'),
            status='pending',
        )
        db.session.add(txn)
        db.session.commit()

        session = {
            'id': 'cs_live_test',
            'payment_status': 'paid',
            'payment_intent': 'pi_test_123',
            'customer_email': 'payer@test.com',
            'metadata': {
                'transaction_id': str(txn.id),
                'subscription_id': str(sub.id),
            },
        }
        handle_checkout_session_completed(session)

        # Verificar que a transação foi atualizada
        updated_txn = Transaction.query.get(txn.id)
        assert updated_txn.status == 'completed'
        assert updated_txn.stripe_payment_intent_id == 'pi_test_123'
        assert updated_txn.paid_at is not None

    def test_successful_checkout_activates_subscription(self, app_context, db,
                                                         creator, group, pricing_plan):
        sub = Subscription(
            group_id=group.id, plan_id=pricing_plan.id,
            telegram_user_id='888',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        db.session.add(sub)
        db.session.commit()

        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('50'),
            status='pending',
        )
        db.session.add(txn)
        db.session.commit()

        session = {
            'id': 'cs_test_sub',
            'payment_status': 'paid',
            'payment_intent': 'pi_test_sub',
            'metadata': {
                'transaction_id': str(txn.id),
                'subscription_id': str(sub.id),
            },
        }
        handle_checkout_session_completed(session)

        updated_sub = Subscription.query.get(sub.id)
        assert updated_sub.status == 'active'

    def test_successful_checkout_updates_creator_balance(self, app_context, db,
                                                          creator, group, pricing_plan):
        """Verifica que o saldo do criador é atualizado após checkout"""
        # Salvar valores iniciais antes do webhook processar
        initial_balance = float(creator.balance or 0)
        initial_earned = float(creator.total_earned or 0)

        sub = Subscription(
            group_id=group.id, plan_id=pricing_plan.id,
            telegram_user_id='999',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='pending',
        )
        db.session.add(sub)
        db.session.commit()

        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('100'),
            status='pending',
        )
        db.session.add(txn)
        db.session.commit()

        expected_net = float(txn.net_amount)  # 89.02

        session = {
            'id': 'cs_test_balance',
            'payment_status': 'paid',
            'payment_intent': 'pi_test_bal',
            'metadata': {
                'transaction_id': str(txn.id),
                'subscription_id': str(sub.id),
            },
        }
        handle_checkout_session_completed(session)

        updated_creator = Creator.query.get(creator.id)
        assert float(updated_creator.balance) == initial_balance + expected_net
        assert float(updated_creator.total_earned) == initial_earned + expected_net

    def test_already_processed_transaction_skipped(self, app_context, db,
                                                    creator, group, pricing_plan):
        sub = Subscription(
            group_id=group.id, plan_id=pricing_plan.id,
            telegram_user_id='111',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        db.session.add(sub)
        db.session.commit()

        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('100'),
            status='completed',  # Já completada
            paid_at=datetime.utcnow(),
        )
        db.session.add(txn)
        db.session.commit()

        session = {
            'id': 'cs_test_dup',
            'payment_status': 'paid',
            'metadata': {'transaction_id': str(txn.id)},
        }
        # Não deve processar novamente
        handle_checkout_session_completed(session)
        # Status permanece completed (não duplicado)
        assert Transaction.query.get(txn.id).status == 'completed'
