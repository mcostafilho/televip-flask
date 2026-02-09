# tests/test_models.py
"""
Testes dos modelos do banco de dados
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal


class TestCreatorModel:
    """Testes do modelo Creator"""

    def test_create_creator(self, app_context, db):
        user = Creator(name='João', email='joao@test.com', username='joao')
        user.set_password('Test1234')
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert user.name == 'João'
        assert user.email == 'joao@test.com'
        assert user.username == 'joao'
        assert user.is_active is True
        assert user.is_admin is False
        assert user.is_verified is False

    def test_password_hashing(self, app_context, creator):
        assert creator.password_hash is not None
        assert creator.check_password('TestPass123') is True
        assert creator.check_password('WrongPassword1') is False

    def test_password_hash_is_not_plaintext(self, app_context, creator):
        assert creator.password_hash != 'TestPass123'

    def test_unique_email(self, app_context, db, creator):
        dup = Creator(name='Dup', email='creator@test.com', username='dup')
        dup.set_password('Dup12345')
        db.session.add(dup)
        with pytest.raises(Exception):
            db.session.commit()

    def test_unique_username(self, app_context, db, creator):
        dup = Creator(name='Dup', email='dup@test.com', username='testcreator')
        dup.set_password('Dup12345')
        db.session.add(dup)
        with pytest.raises(Exception):
            db.session.commit()

    def test_default_balance(self, app_context, db):
        user = Creator(name='New', email='new@test.com', username='newuser')
        user.set_password('NewPass123')
        db.session.add(user)
        db.session.commit()
        assert user.balance == 0 or user.balance == Decimal('0')

    def test_default_total_earned(self, app_context, db):
        user = Creator(name='New', email='new2@test.com', username='newuser2')
        user.set_password('NewPass123')
        db.session.add(user)
        db.session.commit()
        assert user.total_earned == 0 or user.total_earned == Decimal('0')

    def test_update_last_login(self, app_context, creator):
        assert creator.last_login is None
        creator.update_last_login()
        assert creator.last_login is not None
        assert isinstance(creator.last_login, datetime)

    def test_pix_key_encryption(self, app_context, creator):
        creator.pix_key = '12345678901'
        assert creator._pix_key_encrypted is not None
        assert creator._pix_key_encrypted != '12345678901'
        decrypted = creator.pix_key
        assert decrypted == '12345678901'

    def test_pix_key_none(self, app_context, creator):
        creator.pix_key = None
        assert creator._pix_key_encrypted is None
        assert creator.pix_key is None

    def test_repr(self, app_context, creator):
        assert 'testcreator' in repr(creator)

    def test_groups_relationship(self, app_context, db, creator, group):
        assert creator.groups.count() == 1
        assert creator.groups.first().name == 'Test Group'

    def test_withdrawals_relationship(self, app_context, db, creator, withdrawal):
        assert creator.withdrawals.count() == 1


class TestGroupModel:
    """Testes do modelo Group"""

    def test_create_group(self, app_context, db, creator):
        g = Group(name='My Group', description='Test', creator_id=creator.id)
        db.session.add(g)
        db.session.commit()
        assert g.id is not None
        assert g.is_active is True
        assert g.total_subscribers == 0

    def test_group_creator_relationship(self, app_context, group):
        assert group.creator is not None
        assert group.creator.name == 'Test Creator'

    def test_group_telegram_id_unique(self, app_context, db, creator):
        g1 = Group(name='G1', telegram_id='-100999', creator_id=creator.id)
        g2 = Group(name='G2', telegram_id='-100999', creator_id=creator.id)
        db.session.add(g1)
        db.session.commit()
        db.session.add(g2)
        with pytest.raises(Exception):
            db.session.commit()

    def test_pricing_plans_relationship(self, app_context, group, pricing_plan):
        assert group.pricing_plans.count() == 1
        assert group.pricing_plans.first().name == 'Plano Mensal'

    def test_subscriptions_relationship(self, app_context, group, subscription):
        assert group.subscriptions.count() == 1

    def test_cascade_delete_plans(self, app_context, db, group, pricing_plan):
        group_id = group.id
        db.session.delete(group)
        db.session.commit()
        assert PricingPlan.query.filter_by(group_id=group_id).count() == 0

    def test_repr(self, app_context, group):
        assert 'Test Group' in repr(group)


class TestPricingPlanModel:
    """Testes do modelo PricingPlan"""

    def test_create_plan(self, app_context, pricing_plan):
        assert pricing_plan.id is not None
        assert pricing_plan.name == 'Plano Mensal'
        assert pricing_plan.duration_days == 30
        assert pricing_plan.price == Decimal('49.90')
        assert pricing_plan.is_active is True

    def test_plan_group_relationship(self, app_context, pricing_plan):
        assert pricing_plan.group is not None
        assert pricing_plan.group.name == 'Test Group'

    def test_plan_repr(self, app_context, pricing_plan):
        assert 'Plano Mensal' in repr(pricing_plan)

    def test_multiple_plans_per_group(self, app_context, db, group):
        plans = []
        for i in range(3):
            p = PricingPlan(
                group_id=group.id,
                name=f'Plan {i}',
                duration_days=30 * (i + 1),
                price=Decimal(str(10 * (i + 1))),
            )
            db.session.add(p)
            plans.append(p)
        db.session.commit()
        assert group.pricing_plans.count() == 3


class TestSubscriptionModel:
    """Testes do modelo Subscription"""

    def test_create_subscription(self, app_context, subscription):
        assert subscription.id is not None
        assert subscription.status == 'active'
        assert subscription.telegram_user_id == '123456789'

    def test_subscription_group_relationship(self, app_context, subscription):
        assert subscription.group is not None
        assert subscription.group.name == 'Test Group'

    def test_subscription_plan_relationship(self, app_context, subscription):
        assert subscription.plan is not None
        assert subscription.plan.name == 'Plano Mensal'

    def test_subscription_transactions(self, app_context, subscription, transaction):
        assert subscription.transactions.count() == 1

    def test_expired_subscription(self, app_context, db, group, pricing_plan):
        sub = Subscription(
            group_id=group.id,
            plan_id=pricing_plan.id,
            telegram_user_id='999',
            start_date=datetime.utcnow() - timedelta(days=60),
            end_date=datetime.utcnow() - timedelta(days=30),
            status='expired',
        )
        db.session.add(sub)
        db.session.commit()
        assert sub.status == 'expired'

    def test_multiple_subscriptions_same_group(self, app_context, db, group, pricing_plan):
        for i in range(5):
            sub = Subscription(
                group_id=group.id,
                plan_id=pricing_plan.id,
                telegram_user_id=str(1000 + i),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status='active',
            )
            db.session.add(sub)
        db.session.commit()
        assert group.subscriptions.count() == 5


class TestTransactionModel:
    """Testes do modelo Transaction"""

    def test_create_transaction(self, app_context, transaction):
        assert transaction.id is not None
        assert transaction.status == 'completed'
        assert transaction.amount == Decimal('49.90')

    def test_auto_fee_calculation(self, app_context, db, subscription):
        txn = Transaction(
            subscription_id=subscription.id,
            amount=Decimal('100'),
            status='pending',
        )
        db.session.add(txn)
        db.session.commit()
        assert txn.fixed_fee == Decimal('0.99')
        assert txn.percentage_fee == Decimal('7.99')
        assert txn.total_fee == Decimal('8.98')
        assert txn.net_amount == Decimal('91.02')

    def test_fee_recalculation(self, app_context, db, subscription):
        txn = Transaction(
            subscription_id=subscription.id,
            amount=Decimal('50'),
            status='pending',
        )
        db.session.add(txn)
        db.session.commit()
        old_net = txn.net_amount

        txn.amount = Decimal('200')
        txn.calculate_fees()
        db.session.commit()
        assert txn.net_amount != old_net
        assert txn.net_amount == Decimal('183.03')

    def test_zero_amount_fees(self, app_context, db, subscription):
        txn = Transaction(
            subscription_id=subscription.id,
            amount=Decimal('0'),
            status='pending',
        )
        db.session.add(txn)
        db.session.commit()
        assert txn.total_fee == 0 or txn.total_fee == Decimal('0')
        assert txn.net_amount == 0 or txn.net_amount == Decimal('0')

    def test_transaction_subscription_relationship(self, app_context, transaction):
        assert transaction.subscription is not None
        assert transaction.subscription.telegram_user_id == '123456789'

    def test_stripe_session_id_indexed(self, app_context, db, subscription):
        txn = Transaction(
            subscription_id=subscription.id,
            amount=Decimal('25'),
            status='pending',
            stripe_session_id='cs_unique_test',
        )
        db.session.add(txn)
        db.session.commit()
        found = Transaction.query.filter_by(stripe_session_id='cs_unique_test').first()
        assert found is not None
        assert found.id == txn.id

    def test_paid_at_timestamp(self, app_context, transaction):
        assert transaction.paid_at is not None
        assert isinstance(transaction.paid_at, datetime)

    def test_repr(self, app_context, transaction):
        r = repr(transaction)
        assert 'Transaction' in r


class TestWithdrawalModel:
    """Testes do modelo Withdrawal"""

    def test_create_withdrawal(self, app_context, withdrawal):
        assert withdrawal.id is not None
        assert withdrawal.status == 'pending'
        assert withdrawal.amount == Decimal('50.00')
        assert withdrawal.pix_key == '12345678901'

    def test_mark_as_processing(self, app_context, db, withdrawal):
        withdrawal.mark_as_processing()
        db.session.commit()
        assert withdrawal.status == 'processing'
        assert withdrawal.processed_at is not None

    def test_mark_as_completed(self, app_context, db, withdrawal):
        withdrawal.mark_as_completed(transaction_id='pix_txn_123')
        db.session.commit()
        assert withdrawal.status == 'completed'
        assert withdrawal.transaction_id == 'pix_txn_123'
        assert withdrawal.processed_at is not None

    def test_mark_as_completed_without_txn_id(self, app_context, db, withdrawal):
        withdrawal.mark_as_completed()
        db.session.commit()
        assert withdrawal.status == 'completed'
        assert withdrawal.transaction_id is None

    def test_mark_as_failed(self, app_context, db, withdrawal):
        withdrawal.mark_as_failed(reason='PIX key invalid')
        db.session.commit()
        assert withdrawal.status == 'failed'
        assert withdrawal.notes == 'PIX key invalid'

    def test_mark_as_failed_without_reason(self, app_context, db, withdrawal):
        withdrawal.mark_as_failed()
        db.session.commit()
        assert withdrawal.status == 'failed'
        assert withdrawal.notes is None

    def test_withdrawal_creator_relationship(self, app_context, withdrawal):
        assert withdrawal.creator is not None
        assert withdrawal.creator.name == 'Test Creator'

    def test_repr(self, app_context, withdrawal):
        r = repr(withdrawal)
        assert 'Withdrawal' in r
        assert 'pending' in r
