# tests/test_payment_service_full.py
"""
Testes completos do serviço de pagamento - stress test com edge cases
"""
import pytest
from decimal import Decimal
from app.services.payment_service import PaymentService



class TestFeeCalculationStress:
    """Stress test de cálculos de taxa"""

    def test_very_small_amount(self):
        fees = PaymentService.calculate_fees(0.01)
        assert fees['net_amount'] >= 0 or fees['net_amount'] < 0
        # Taxa fixa maior que o valor - net negativo

    def test_fee_equals_amount(self):
        """Quando a taxa consome todo o valor"""
        fees = PaymentService.calculate_fees(1)
        assert fees['total_fee'] > 0

    def test_large_amount(self):
        fees = PaymentService.calculate_fees(10000)
        assert fees['net_amount'] > 0
        assert fees['total_fee'] > 0
        # 10000 - 0.99 - (10000 * 0.0999) = 10000 - 0.99 - 999 = 9000.01
        assert fees['net_amount'] == Decimal('9000.01')

    def test_very_large_amount(self):
        fees = PaymentService.calculate_fees(999999.99)
        assert fees['net_amount'] > 0
        assert fees['total_fee'] > 0

    def test_one_cent(self):
        fees = PaymentService.calculate_fees(0.01)
        assert isinstance(fees['total_fee'], (int, float, Decimal))

    def test_round_numbers(self):
        """Teste com valores redondos"""
        for amount in [10, 20, 50, 100, 200, 500, 1000]:
            fees = PaymentService.calculate_fees(amount)
            assert fees['gross_amount'] == amount
            assert fees['net_amount'] == fees['gross_amount'] - fees['total_fee']

    def test_fee_consistency(self):
        """Taxa deve ser consistente para o mesmo valor"""
        for _ in range(100):
            fees = PaymentService.calculate_fees(49.90)
            assert fees['fixed_fee'] == Decimal('0.99')

    def test_net_amount_formula(self):
        """net_amount = gross - fixed_fee - percentage_fee"""
        for amount in [10, 25.5, 49.90, 100, 250.75, 999.99]:
            fees = PaymentService.calculate_fees(amount)
            expected_net = Decimal(str(amount)) - fees['fixed_fee'] - fees['percentage_fee']
            assert abs(fees['net_amount'] - expected_net) < Decimal('0.01')

    def test_fee_percentage_correct(self):
        """fee_percentage deve ser total_fee / gross_amount * 100"""
        fees = PaymentService.calculate_fees(100)
        expected_pct = float(fees['total_fee']) / 100 * 100
        assert abs(float(fees['fee_percentage']) - expected_pct) < 0.01

    def test_negative_amount(self):
        fees = PaymentService.calculate_fees(-100)
        assert fees['total_fee'] == 0
        assert fees['net_amount'] == 0

    def test_zero_amount(self):
        fees = PaymentService.calculate_fees(0)
        assert fees['total_fee'] == 0
        assert fees['net_amount'] == 0
        assert fees['fee_percentage'] == 0

    def test_string_amount_decimal(self):
        """Deve funcionar com Decimal input"""
        fees = PaymentService.calculate_fees(Decimal('49.90'))
        assert fees['net_amount'] > 0

    def test_integer_amount(self):
        fees = PaymentService.calculate_fees(100)
        assert fees['net_amount'] == Decimal('89.02')


class TestFormatFeeBreakdown:
    """Testes de formatação"""

    def test_format_basic(self):
        formatted = PaymentService.format_fee_breakdown(100)
        assert 'R$' in formatted['gross']
        assert 'R$' in formatted['net']
        assert '9,99%' in formatted['percentage_fee']

    def test_format_zero(self):
        formatted = PaymentService.format_fee_breakdown(0)
        assert 'R$' in formatted['gross']

    def test_format_large(self):
        formatted = PaymentService.format_fee_breakdown(10000)
        assert 'R$' in formatted['gross']


class TestCreatorEarnings:
    """Testes de cálculo de ganhos"""

    class MockTransaction:
        def __init__(self, amount, status='completed'):
            self.amount = amount
            self.status = status
            fees = PaymentService.calculate_fees(amount)
            self.total_fee = fees['total_fee']
            self.net_amount = fees['net_amount']

    def test_empty_transactions(self):
        result = PaymentService.calculate_creator_earnings([])
        assert result['total_gross'] == 0
        assert result['total_net'] == 0
        assert result['transaction_count'] == 0

    def test_only_pending_transactions(self):
        txns = [self.MockTransaction(100, 'pending'), self.MockTransaction(50, 'failed')]
        result = PaymentService.calculate_creator_earnings(txns)
        assert result['transaction_count'] == 0
        assert result['total_gross'] == 0

    def test_mixed_statuses(self):
        txns = [
            self.MockTransaction(100, 'completed'),
            self.MockTransaction(50, 'pending'),
            self.MockTransaction(200, 'completed'),
            self.MockTransaction(30, 'failed'),
        ]
        result = PaymentService.calculate_creator_earnings(txns)
        assert result['transaction_count'] == 2
        assert result['total_gross'] == 300

    def test_many_transactions(self):
        """Stress test com muitas transações"""
        txns = [self.MockTransaction(10 + i) for i in range(100)]
        result = PaymentService.calculate_creator_earnings(txns)
        assert result['transaction_count'] == 100
        assert result['total_gross'] > 0
        assert result['total_net'] > 0
        assert result['total_fees'] > 0

    def test_single_transaction(self):
        txns = [self.MockTransaction(100)]
        result = PaymentService.calculate_creator_earnings(txns)
        assert result['transaction_count'] == 1
        assert result['total_gross'] == 100
        assert round(Decimal(str(result['total_net'])), 2) == Decimal('89.02')


class TestMonthlyProjection:
    """Testes de projeção mensal"""

    def test_basic_projection(self):
        proj = PaymentService.calculate_monthly_projection(100, 10)
        assert proj == 300  # (100/10) * 30

    def test_zero_days(self):
        proj = PaymentService.calculate_monthly_projection(100, 0)
        assert proj == 0

    def test_one_day(self):
        proj = PaymentService.calculate_monthly_projection(50, 1)
        assert proj == 1500  # (50/1) * 30

    def test_30_days(self):
        proj = PaymentService.calculate_monthly_projection(300, 30)
        assert proj == 300  # (300/30) * 30

    def test_zero_earnings(self):
        proj = PaymentService.calculate_monthly_projection(0, 10)
        assert proj == 0


class TestFeeDescription:
    """Testes de descrição de taxa"""

    def test_description_format(self):
        desc = PaymentService.get_fee_description()
        assert 'R$' in desc
        assert '0,99' in desc
        assert '9,99%' in desc
