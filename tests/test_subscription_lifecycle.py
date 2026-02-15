"""
Testes do ciclo de vida de assinaturas — cenários críticos de produção.

Cobre os 4 bugs encontrados em produção:
1. Webhook retornando 200 em erro (agora retorna 500)
2. Stripe API removendo current_period_end (fallback via invoice lines)
3. Sub expirada antes de sync com Stripe (reativação)
4. Transação pendente eterna (auto-fix no dashboard)
"""
import os
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models import Creator, Group, PricingPlan, Subscription, Transaction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stripe_sub(db, group, pricing_plan):
    """Subscription Stripe-managed com stripe_subscription_id"""
    sub = Subscription(
        group_id=group.id,
        plan_id=pricing_plan.id,
        telegram_user_id='999888777',
        telegram_username='stripe_user',
        stripe_subscription_id='sub_stripe_test_001',
        stripe_customer_id='cus_test_001',
        start_date=datetime.utcnow() - timedelta(days=30),
        end_date=datetime.utcnow() + timedelta(days=1),
        status='active',
        is_legacy=False,
        auto_renew=True,
        cancel_at_period_end=False,
    )
    db.session.add(sub)
    db.session.commit()
    return sub


@pytest.fixture
def expired_stripe_sub(db, group, pricing_plan):
    """Subscription Stripe-managed com status='expired' e end_date no passado"""
    sub = Subscription(
        group_id=group.id,
        plan_id=pricing_plan.id,
        telegram_user_id='999888776',
        telegram_username='expired_user',
        stripe_subscription_id='sub_stripe_expired_001',
        stripe_customer_id='cus_test_002',
        start_date=datetime.utcnow() - timedelta(days=60),
        end_date=datetime.utcnow() - timedelta(hours=5),
        status='expired',
        is_legacy=False,
        auto_renew=True,
        cancel_at_period_end=False,
    )
    db.session.add(sub)
    db.session.commit()
    return sub


def make_invoice_data(stripe_invoice_id, stripe_sub_id, billing_reason,
                      amount_cents, period_end_ts=None):
    """Helper para montar dict de invoice.paid"""
    data = {
        'id': stripe_invoice_id,
        'subscription': stripe_sub_id,
        'billing_reason': billing_reason,
        'amount_paid': amount_cents,
        'charge': None,
        'payment_settings': {'payment_method_types': ['card']},
        'lines': {'data': []},
    }
    if period_end_ts is not None:
        data['lines']['data'] = [{
            'period': {'start': period_end_ts - 30 * 86400, 'end': period_end_ts},
        }]
    return data


# ---------------------------------------------------------------------------
# 1. Webhook handle_invoice_paid
# ---------------------------------------------------------------------------

class TestHandleInvoicePaid:
    """Testes para handle_invoice_paid (webhooks.py:358-562)"""

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_subscription_create_activates(self, mock_notify, app_context, db,
                                           stripe_sub, creator):
        """Sub pending→active, txn completed, creator creditado"""
        from app.routes.webhooks import handle_invoice_paid

        stripe_sub.status = 'pending'
        db.session.commit()

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_create_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end,
        )

        balance_before = Decimal(str(creator.balance or 0))
        handle_invoice_paid(invoice)

        db.session.refresh(stripe_sub)
        db.session.refresh(creator)

        assert stripe_sub.status == 'active'
        assert stripe_sub.end_date is not None

        txn = Transaction.query.filter_by(stripe_invoice_id='in_create_001').first()
        assert txn is not None
        assert txn.status == 'completed'
        assert creator.balance > balance_before

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_subscription_cycle_renews(self, mock_notify, app_context, db,
                                       stripe_sub, creator):
        """end_date estendido, nova txn criada, creator creditado"""
        from app.routes.webhooks import handle_invoice_paid

        old_end = stripe_sub.end_date
        period_end = int((datetime.utcnow() + timedelta(days=60)).timestamp())
        invoice = make_invoice_data(
            'in_cycle_001', stripe_sub.stripe_subscription_id,
            'subscription_cycle', 4990, period_end,
        )

        balance_before = Decimal(str(creator.balance or 0))
        handle_invoice_paid(invoice)

        db.session.refresh(stripe_sub)
        db.session.refresh(creator)

        assert stripe_sub.end_date > old_end
        assert stripe_sub.status == 'active'

        txn = Transaction.query.filter_by(stripe_invoice_id='in_cycle_001').first()
        assert txn is not None
        assert txn.status == 'completed'
        assert txn.billing_reason == 'subscription_cycle'
        assert creator.balance > balance_before

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_idempotency(self, mock_notify, app_context, db,
                         stripe_sub, creator):
        """Mesmo stripe_invoice_id processado 2x não duplica txn"""
        from app.routes.webhooks import handle_invoice_paid

        stripe_sub.status = 'pending'
        db.session.commit()

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_idem_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end,
        )

        handle_invoice_paid(invoice)
        balance_after_first = Decimal(str(creator.balance))

        # Processar de novo
        handle_invoice_paid(invoice)

        db.session.refresh(creator)

        count = Transaction.query.filter_by(stripe_invoice_id='in_idem_001').count()
        assert count == 1
        assert creator.balance == balance_after_first

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_missing_period_end_uses_fallback(self, mock_notify, app_context, db,
                                              stripe_sub, pricing_plan, creator):
        """Sem lines.data[0].period.end → usa timedelta(days=plan.duration_days)"""
        from app.routes.webhooks import handle_invoice_paid

        stripe_sub.status = 'pending'
        db.session.commit()

        # Invoice WITHOUT period_end in lines
        invoice = make_invoice_data(
            'in_nope_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end_ts=None,
        )

        handle_invoice_paid(invoice)
        db.session.refresh(stripe_sub)

        # Should use timedelta fallback
        expected_min = datetime.utcnow() + timedelta(days=pricing_plan.duration_days - 1)
        assert stripe_sub.end_date > expected_min

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_already_credited_by_bot(self, mock_notify, app_context, db,
                                     stripe_sub, creator):
        """Txn já completed (pelo bot), não duplica crédito ao creator"""
        from app.routes.webhooks import handle_invoice_paid

        # Pre-create completed transaction (as bot would)
        txn = Transaction(
            subscription_id=stripe_sub.id,
            amount=Decimal('49.90'),
            payment_method='stripe',
            status='completed',
            paid_at=datetime.utcnow(),
            billing_reason='subscription_create',
        )
        db.session.add(txn)
        # Credit creator manually (simulating bot)
        creator.balance = Decimal('44.00')
        creator.total_earned = Decimal('44.00')
        db.session.commit()

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_bot_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end,
        )

        handle_invoice_paid(invoice)
        db.session.refresh(creator)

        # Balance should NOT have increased again
        assert creator.balance == Decimal('44.00')

    def test_error_propagates(self, app_context, db, stripe_sub, creator):
        """Exceção dentro de handle_invoice_paid é re-raised"""
        from app.routes.webhooks import handle_invoice_paid

        stripe_sub.status = 'pending'
        db.session.commit()

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_err_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end,
        )

        with patch('app.routes.webhooks.db.session.commit',
                   side_effect=RuntimeError('DB error')):
            with pytest.raises(RuntimeError, match='DB error'):
                handle_invoice_paid(invoice)

    @patch('app.routes.webhooks.stripe.Webhook.construct_event')
    def test_webhook_returns_500_on_error(self, mock_construct, client, db,
                                          stripe_sub):
        """Endpoint retorna 500 quando handler falha (linhas 98-100)"""
        os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test'

        # construct_event returns an invoice.paid event
        mock_construct.return_value = {
            'type': 'invoice.paid',
            'id': 'evt_500_test',
            'data': {'object': {
                'id': 'in_500_test',
                'subscription': stripe_sub.stripe_subscription_id,
                'billing_reason': 'subscription_create',
                'amount_paid': 4990,
                'charge': None,
                'payment_settings': {'payment_method_types': ['card']},
                'lines': {'data': []},
            }},
        }

        # Force error: break the plan relationship
        stripe_sub.plan_id = 99999
        db.session.commit()

        resp = client.post(
            '/webhooks/stripe',
            data=b'payload',
            headers={'Stripe-Signature': 'sig_test'},
            content_type='application/json',
        )
        assert resp.status_code == 500

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_reactivates_expired_sub(self, mock_notify, app_context, db,
                                     expired_stripe_sub, creator):
        """billing_reason=subscription_cycle com sub expirada → active"""
        from app.routes.webhooks import handle_invoice_paid

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_react_001', expired_stripe_sub.stripe_subscription_id,
            'subscription_cycle', 4990, period_end,
        )

        handle_invoice_paid(invoice)
        db.session.refresh(expired_stripe_sub)

        assert expired_stripe_sub.status == 'active'
        assert expired_stripe_sub.end_date > datetime.utcnow()


# ---------------------------------------------------------------------------
# 2. try_fix_stale_end_date
# ---------------------------------------------------------------------------

class TestTryFixStaleEndDate:
    """Testes para try_fix_stale_end_date (format_utils.py:104-258)"""

    def test_fix_via_local_transaction(self, app_context, db, stripe_sub, pricing_plan):
        """Encontra txn completed billing_reason=subscription_cycle → corrige end_date"""
        from bot.utils.format_utils import try_fix_stale_end_date

        # Set end_date in the past
        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        old_end = stripe_sub.end_date

        # Create a completed renewal transaction
        txn = Transaction(
            subscription_id=stripe_sub.id,
            amount=Decimal('49.90'),
            payment_method='stripe',
            status='completed',
            paid_at=datetime.utcnow() - timedelta(hours=1),
            billing_reason='subscription_cycle',
        )
        db.session.add(txn)
        db.session.commit()

        result = try_fix_stale_end_date(stripe_sub)

        assert result is True
        db.session.refresh(stripe_sub)
        assert stripe_sub.end_date > old_end

    @patch('stripe.Invoice.retrieve')
    @patch('stripe.Subscription.retrieve')
    def test_fix_via_stripe_api_fallback(self, mock_stripe_sub, mock_invoice,
                                         app_context, db, stripe_sub):
        """Sem txn local, consulta Stripe, sincroniza end_date"""
        from bot.utils.format_utils import try_fix_stale_end_date

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        db.session.commit()

        future_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        mock_stripe_sub.return_value = {
            'status': 'active',
            'current_period_end': future_end,
            'latest_invoice': 'in_fix_001',
        }
        mock_invoice.return_value = {
            'amount_paid': 4990,
            'billing_reason': 'subscription_cycle',
            'status_transitions': {'paid_at': int(datetime.utcnow().timestamp())},
            'lines': {'data': [{'period': {'end': future_end}}]},
        }

        result = try_fix_stale_end_date(stripe_sub)

        assert result is True
        db.session.refresh(stripe_sub)
        assert stripe_sub.end_date > datetime.utcnow()

    @patch('stripe.Invoice.retrieve')
    @patch('stripe.Subscription.retrieve')
    def test_fix_creates_missing_transaction(self, mock_stripe_sub, mock_invoice,
                                              app_context, db, stripe_sub):
        """Cria txn quando webhook não criou (idempotency via stripe_invoice_id)"""
        from bot.utils.format_utils import try_fix_stale_end_date

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        db.session.commit()

        future_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        mock_stripe_sub.return_value = {
            'status': 'active',
            'current_period_end': future_end,
            'latest_invoice': 'in_missing_txn_001',
        }
        mock_invoice.return_value = {
            'amount_paid': 4990,
            'billing_reason': 'subscription_cycle',
            'status_transitions': {'paid_at': int(datetime.utcnow().timestamp())},
            'lines': {'data': [{'period': {'end': future_end}}]},
        }

        result = try_fix_stale_end_date(stripe_sub)

        assert result is True
        txn = Transaction.query.filter_by(stripe_invoice_id='in_missing_txn_001').first()
        assert txn is not None
        assert txn.status == 'completed'

    @patch('stripe.Invoice.retrieve')
    @patch('stripe.Subscription.retrieve')
    def test_fix_credits_creator(self, mock_stripe_sub, mock_invoice,
                                  app_context, db, stripe_sub, creator):
        """Credita balance + total_earned do criador ao criar txn faltante"""
        from bot.utils.format_utils import try_fix_stale_end_date

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        creator.balance = Decimal('10.00')
        creator.total_earned = Decimal('10.00')
        db.session.commit()

        future_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        mock_stripe_sub.return_value = {
            'status': 'active',
            'current_period_end': future_end,
            'latest_invoice': 'in_credit_001',
        }
        mock_invoice.return_value = {
            'amount_paid': 4990,
            'billing_reason': 'subscription_cycle',
            'status_transitions': {'paid_at': int(datetime.utcnow().timestamp())},
            'lines': {'data': [{'period': {'end': future_end}}]},
        }

        try_fix_stale_end_date(stripe_sub)
        db.session.refresh(creator)

        assert creator.balance > Decimal('10.00')
        assert creator.total_earned > Decimal('10.00')

    @patch('stripe.Invoice.retrieve')
    @patch('stripe.Subscription.retrieve')
    def test_fix_reactivates_expired_sub(self, mock_stripe_sub, mock_invoice,
                                          app_context, db, expired_stripe_sub):
        """Sub status='expired' → 'active' quando Stripe confirma"""
        from bot.utils.format_utils import try_fix_stale_end_date

        future_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        mock_stripe_sub.return_value = {
            'status': 'active',
            'current_period_end': future_end,
            'latest_invoice': 'in_reactivate_001',
        }
        mock_invoice.return_value = {
            'amount_paid': 4990,
            'billing_reason': 'subscription_cycle',
            'status_transitions': {'paid_at': int(datetime.utcnow().timestamp())},
            'lines': {'data': [{'period': {'end': future_end}}]},
        }

        result = try_fix_stale_end_date(expired_stripe_sub)

        assert result is True
        db.session.refresh(expired_stripe_sub)
        assert expired_stripe_sub.status == 'active'
        assert expired_stripe_sub.end_date > datetime.utcnow()

    @patch('stripe.Invoice.retrieve')
    @patch('stripe.Subscription.retrieve')
    def test_fix_handles_missing_current_period_end(self, mock_stripe_sub,
                                                     mock_invoice, app_context,
                                                     db, stripe_sub):
        """Stripe API nova sem current_period_end → usa invoice lines"""
        from bot.utils.format_utils import try_fix_stale_end_date

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        db.session.commit()

        future_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())

        # NO current_period_end field
        mock_stripe_sub.return_value = {
            'status': 'active',
            'latest_invoice': 'in_noperiod_001',
        }
        mock_invoice.return_value = {
            'amount_paid': 4990,
            'billing_reason': 'subscription_cycle',
            'status_transitions': {'paid_at': int(datetime.utcnow().timestamp())},
            'lines': {'data': [{'period': {'end': future_end}}]},
        }

        result = try_fix_stale_end_date(stripe_sub)

        assert result is True
        db.session.refresh(stripe_sub)
        assert stripe_sub.end_date > datetime.utcnow()

    def test_no_op_when_end_date_in_future(self, app_context, db, stripe_sub):
        """end_date > now → return False, nada muda"""
        from bot.utils.format_utils import try_fix_stale_end_date

        stripe_sub.end_date = datetime.utcnow() + timedelta(days=10)
        db.session.commit()

        result = try_fix_stale_end_date(stripe_sub)
        assert result is False

    @patch('stripe.Subscription.retrieve')
    def test_no_op_when_stripe_inactive(self, mock_stripe_sub, app_context,
                                         db, stripe_sub):
        """Stripe status='canceled' → return False"""
        from bot.utils.format_utils import try_fix_stale_end_date

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        db.session.commit()

        mock_stripe_sub.return_value = {
            'status': 'canceled',
            'current_period_end': None,
            'latest_invoice': None,
        }

        result = try_fix_stale_end_date(stripe_sub)
        assert result is False


# ---------------------------------------------------------------------------
# 3. is_sub_effectively_active / is_sub_renewing
# ---------------------------------------------------------------------------

class TestIsSubEffectivelyActive:
    """Testes para is_sub_effectively_active (format_utils.py:21-54)"""

    def test_within_period(self, app_context, db, stripe_sub):
        """end_date > now → True"""
        from bot.utils.format_utils import is_sub_effectively_active

        stripe_sub.end_date = datetime.utcnow() + timedelta(days=5)
        stripe_sub.status = 'active'
        db.session.commit()

        assert is_sub_effectively_active(stripe_sub) is True

    def test_grace_window(self, app_context, db, stripe_sub):
        """Stripe autorenew, end_date 1h atrás → True (grace 2h)"""
        from bot.utils.format_utils import is_sub_effectively_active

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=1)
        stripe_sub.status = 'active'
        stripe_sub.cancel_at_period_end = False
        stripe_sub.is_legacy = False
        db.session.commit()

        assert is_sub_effectively_active(stripe_sub) is True

    def test_past_grace(self, app_context, db, stripe_sub):
        """Stripe autorenew, end_date 3h atrás → False"""
        from bot.utils.format_utils import is_sub_effectively_active

        stripe_sub.end_date = datetime.utcnow() - timedelta(hours=3)
        stripe_sub.status = 'active'
        stripe_sub.cancel_at_period_end = False
        stripe_sub.is_legacy = False
        db.session.commit()

        assert is_sub_effectively_active(stripe_sub) is False


class TestIsSubRenewing:
    """Testes para is_sub_renewing (format_utils.py:57-101)"""

    def test_renewing_within_grace(self, app_context, db, stripe_sub):
        """end_date passou, Stripe autorenew, sem txn cycle → True"""
        from bot.utils.format_utils import is_sub_renewing

        stripe_sub.end_date = datetime.utcnow() - timedelta(minutes=30)
        stripe_sub.status = 'active'
        stripe_sub.cancel_at_period_end = False
        stripe_sub.is_legacy = False
        db.session.commit()

        assert is_sub_renewing(stripe_sub) is True

    def test_already_renewed(self, app_context, db, stripe_sub):
        """txn cycle completed existe → False"""
        from bot.utils.format_utils import is_sub_renewing

        stripe_sub.end_date = datetime.utcnow() - timedelta(minutes=30)
        stripe_sub.status = 'active'
        stripe_sub.cancel_at_period_end = False
        stripe_sub.is_legacy = False

        # Create completed renewal transaction
        txn = Transaction(
            subscription_id=stripe_sub.id,
            amount=Decimal('49.90'),
            payment_method='stripe',
            status='completed',
            paid_at=datetime.utcnow() - timedelta(minutes=10),
            billing_reason='subscription_cycle',
        )
        db.session.add(txn)
        db.session.commit()

        assert is_sub_renewing(stripe_sub) is False


# ---------------------------------------------------------------------------
# 4. Consistência de status
# ---------------------------------------------------------------------------

class TestStatusConsistency:
    """Testes de consistência de status e auto-fix"""

    def test_dashboard_auto_fixes_pending_transactions(self, client, db,
                                                        creator, group,
                                                        pricing_plan):
        """Txn pending + sub active + Stripe managed → txn completed após dashboard"""
        from tests.conftest import login

        # Create active Stripe sub with pending transaction
        sub = Subscription(
            group_id=group.id,
            plan_id=pricing_plan.id,
            telegram_user_id='555111222',
            telegram_username='pending_fix_user',
            stripe_subscription_id='sub_autofix_001',
            start_date=datetime.utcnow() - timedelta(days=30),
            end_date=datetime.utcnow() + timedelta(days=1),
            status='active',
        )
        db.session.add(sub)
        db.session.flush()

        txn = Transaction(
            subscription_id=sub.id,
            amount=Decimal('49.90'),
            payment_method='stripe',
            status='pending',
            stripe_session_id='cs_autofix_001',
        )
        # Backdate created_at so it's > 2h old (stale cutoff)
        db.session.add(txn)
        db.session.flush()
        txn.created_at = datetime.utcnow() - timedelta(hours=3)
        db.session.commit()

        # Login and hit dashboard/transactions
        login(client, creator.email, 'TestPass123')
        resp = client.get('/dashboard/transactions')

        # Transaction should now be completed
        db.session.refresh(txn)
        assert txn.status == 'completed'

    def test_handle_invoice_paid_no_subscription_found(self, app_context, db):
        """stripe_sub_id inexistente → não crasheia, retorna normalmente"""
        from app.routes.webhooks import handle_invoice_paid

        invoice = make_invoice_data(
            'in_nosub_001', 'sub_nonexistent_999',
            'subscription_create', 4990,
        )

        # Should not raise
        handle_invoice_paid(invoice)

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_checkout_completed_subscription_mode(self, mock_notify,
                                                   app_context, db,
                                                   stripe_sub):
        """mode='subscription' grava stripe_subscription_id"""
        from app.routes.webhooks import handle_checkout_session_completed

        # Create pending transaction linked to session
        txn = Transaction(
            subscription_id=stripe_sub.id,
            amount=Decimal('49.90'),
            payment_method='stripe',
            status='pending',
            stripe_session_id='cs_sub_mode_001',
        )
        db.session.add(txn)
        db.session.commit()

        # Clear stripe_subscription_id to test it gets set
        stripe_sub.stripe_subscription_id = None
        db.session.commit()

        session = {
            'id': 'cs_sub_mode_001',
            'mode': 'subscription',
            'subscription': 'sub_new_from_checkout',
            'payment_status': 'paid',
            'metadata': {},
        }

        handle_checkout_session_completed(session)
        db.session.refresh(stripe_sub)

        assert stripe_sub.stripe_subscription_id == 'sub_new_from_checkout'

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_subscription_create_no_existing_txn(self, mock_notify,
                                                  app_context, db,
                                                  stripe_sub, creator):
        """invoice.paid sem txn pendente → cria nova txn"""
        from app.routes.webhooks import handle_invoice_paid

        stripe_sub.status = 'pending'
        db.session.commit()

        # Ensure no transactions exist for this sub
        Transaction.query.filter_by(subscription_id=stripe_sub.id).delete()
        db.session.commit()

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_notxn_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end,
        )

        handle_invoice_paid(invoice)

        txn = Transaction.query.filter_by(stripe_invoice_id='in_notxn_001').first()
        assert txn is not None
        assert txn.status == 'completed'
        assert txn.billing_reason == 'subscription_create'

    def test_transaction_net_amount_calculated(self, app_context, db, stripe_sub):
        """Transaction.__init__ calcula fees automaticamente"""
        txn = Transaction(
            subscription_id=stripe_sub.id,
            amount=Decimal('49.90'),
            payment_method='stripe',
            status='completed',
        )
        db.session.add(txn)
        db.session.commit()

        assert txn.net_amount is not None
        assert txn.net_amount > 0
        assert txn.net_amount < txn.amount
        assert txn.total_fee > 0

    def test_creator_balance_never_negative(self, app_context, db, stripe_sub,
                                            creator):
        """Creditar criador com balance=None → initializa como 0"""
        from app.routes.webhooks import handle_invoice_paid

        stripe_sub.status = 'pending'
        creator.balance = None
        creator.total_earned = None
        db.session.commit()

        period_end = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        invoice = make_invoice_data(
            'in_null_001', stripe_sub.stripe_subscription_id,
            'subscription_create', 4990, period_end,
        )

        handle_invoice_paid(invoice)
        db.session.refresh(creator)

        assert creator.balance is not None
        assert creator.balance >= 0
        assert creator.total_earned is not None
        assert creator.total_earned >= 0


# ---------------------------------------------------------------------------
# 5. Model imports
# ---------------------------------------------------------------------------

class TestModelImports:
    """Testes de integridade de imports"""

    def test_transaction_import_consistency(self):
        """from app.models import Transaction == from app.models.subscription import Transaction"""
        from app.models import Transaction as T1
        from app.models.subscription import Transaction as T2
        assert T1 is T2

    def test_all_handler_imports_succeed(self, app_context):
        """Imports dos handlers não falham"""
        from app.routes.webhooks import (
            handle_invoice_paid,
            handle_checkout_session_completed,
            handle_invoice_payment_failed,
            handle_subscription_deleted,
        )
        assert callable(handle_invoice_paid)
        assert callable(handle_checkout_session_completed)
        assert callable(handle_invoice_payment_failed)
        assert callable(handle_subscription_deleted)

    def test_get_fee_rates_import_works(self, app_context, db, creator, group):
        """creator.get_fee_rates(group_id=X) não causa ImportError"""
        rates = creator.get_fee_rates(group_id=group.id)
        assert 'fixed_fee' in rates
        assert 'percentage_fee' in rates
        assert 'is_custom' in rates
