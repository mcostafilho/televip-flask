# tests/test_payment_service.py
import pytest
from decimal import Decimal
from app.services.payment_service import PaymentService
from app.models import Transaction
from app import create_app, db


class TestPaymentService:
    """Testes para o serviço de cálculo de taxas"""

    def test_fee_calculation_basic(self):
        """Testa o cálculo básico das taxas"""
        fees = PaymentService.calculate_fees(100)
        assert fees['fixed_fee'] == Decimal('0.99')
        assert fees['percentage_fee'] == Decimal('9.99')
        assert fees['total_fee'] == Decimal('10.98')
        assert fees['net_amount'] == Decimal('89.02')
        assert round(fees['fee_percentage'], 2) == Decimal('10.98')

    def test_fee_calculation_small_amount(self):
        """Testa cálculo com valores pequenos"""
        fees = PaymentService.calculate_fees(10)
        assert fees['fixed_fee'] == Decimal('0.99')
        assert fees['percentage_fee'] == Decimal('1.00')
        assert fees['total_fee'] == Decimal('1.99')
        assert fees['net_amount'] == Decimal('8.01')

    def test_fee_calculation_large_amount(self):
        """Testa cálculo com valores grandes"""
        fees = PaymentService.calculate_fees(1000)
        assert fees['fixed_fee'] == Decimal('0.99')
        assert fees['percentage_fee'] == Decimal('99.90')
        assert fees['total_fee'] == Decimal('100.89')
        assert fees['net_amount'] == Decimal('899.11')

    def test_fee_calculation_zero(self):
        """Testa cálculo com valor zero"""
        fees = PaymentService.calculate_fees(0)
        assert fees['fixed_fee'] == 0
        assert fees['percentage_fee'] == 0
        assert fees['total_fee'] == 0
        assert fees['net_amount'] == 0
        assert fees['fee_percentage'] == 0

    def test_fee_calculation_negative(self):
        """Testa cálculo com valor negativo"""
        fees = PaymentService.calculate_fees(-10)
        assert fees['fixed_fee'] == 0
        assert fees['percentage_fee'] == 0
        assert fees['total_fee'] == 0
        assert fees['net_amount'] == 0

    def test_fee_formatting(self):
        """Testa a formatação das taxas"""
        formatted = PaymentService.format_fee_breakdown(100)
        assert formatted['gross'] == "R$ 100.00"
        assert formatted['fixed_fee'] == "R$ 0.99"
        assert formatted['percentage_fee'] == "R$ 9.99 (9,99%)"
        assert formatted['total_fee'] == "R$ 10.98"
        assert formatted['net'] == "R$ 89.02"
        assert "10.98%" in formatted['effective_rate']

    def test_fee_description(self):
        """Testa a descrição das taxas"""
        description = PaymentService.get_fee_description()
        assert description == "R$ 0,99 + 9,99% por transação"

    def test_calculate_creator_earnings(self):
        """Testa cálculo de ganhos do criador"""
        class MockTransaction:
            def __init__(self, amount, status='completed'):
                self.amount = amount
                self.status = status
                fees = PaymentService.calculate_fees(amount)
                self.total_fee = fees['total_fee']
                self.net_amount = fees['net_amount']

        transactions = [
            MockTransaction(100),
            MockTransaction(50),
            MockTransaction(200),
            MockTransaction(100, status='pending'),
        ]

        earnings = PaymentService.calculate_creator_earnings(transactions)

        assert earnings['total_gross'] == 350
        assert round(Decimal(str(earnings['total_net'])), 2) == Decimal('312.06')
        assert earnings['transaction_count'] == 3

    def test_monthly_projection(self):
        """Testa projeção mensal de ganhos"""
        projection = PaymentService.calculate_monthly_projection(100, 5)
        assert projection == 600

        projection = PaymentService.calculate_monthly_projection(100, 0)
        assert projection == 0


class TestTransactionModel:
    """Testes para o modelo Transaction com cálculo automático"""

    @pytest.fixture
    def app(self):
        """Cria app de teste"""
        import os
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        app = create_app()
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()

    def test_transaction_auto_calculation(self, app):
        """Testa cálculo automático de taxas ao criar transação"""
        with app.app_context():
            transaction = Transaction(
                subscription_id=1,
                amount=100,
                status='pending',
                payment_method='pix'
            )
            assert transaction.fixed_fee == Decimal('0.99')
            assert transaction.percentage_fee == Decimal('9.99')
            assert transaction.total_fee == Decimal('10.98')
            assert transaction.net_amount == Decimal('89.02')

    def test_transaction_recalculation(self, app):
        """Testa recálculo de taxas"""
        with app.app_context():
            transaction = Transaction(
                subscription_id=1,
                amount=50,
                status='pending'
            )
            assert abs(float(transaction.net_amount) - 44.015) < 0.01

            transaction.amount = 200
            transaction.calculate_fees()
            assert abs(float(transaction.fixed_fee) - 0.99) < 0.01
            assert abs(float(transaction.percentage_fee) - 19.98) < 0.01
            assert abs(float(transaction.total_fee) - 20.97) < 0.01
            assert abs(float(transaction.net_amount) - 179.03) < 0.01
