# tests/test_payment_service.py
import pytest
from app.services.payment_service import PaymentService
from app.models import Transaction
from app import create_app, db

class TestPaymentService:
    """Testes para o serviço de cálculo de taxas"""
    
    def test_fee_calculation_basic(self):
        """Testa o cálculo básico das taxas"""
        # Teste 1: Venda de R$ 100
        fees = PaymentService.calculate_fees(100)
        assert fees['fixed_fee'] == 0.99
        assert fees['percentage_fee'] == 7.99
        assert fees['total_fee'] == 8.98
        assert fees['net_amount'] == 91.02
        assert round(fees['fee_percentage'], 2) == 8.98
        
    def test_fee_calculation_small_amount(self):
        """Testa cálculo com valores pequenos"""
        # Teste 2: Venda de R$ 10
        fees = PaymentService.calculate_fees(10)
        assert fees['fixed_fee'] == 0.99
        assert fees['percentage_fee'] == 0.80  # 7.99% de 10
        assert fees['total_fee'] == 1.79
        assert fees['net_amount'] == 8.21
        
    def test_fee_calculation_large_amount(self):
        """Testa cálculo com valores grandes"""
        # Teste 3: Venda de R$ 1000
        fees = PaymentService.calculate_fees(1000)
        assert fees['fixed_fee'] == 0.99
        assert fees['percentage_fee'] == 79.90
        assert fees['total_fee'] == 80.89
        assert fees['net_amount'] == 919.11
        
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
        assert formatted['percentage_fee'] == "R$ 7.99 (7,99%)"
        assert formatted['total_fee'] == "R$ 8.98"
        assert formatted['net'] == "R$ 91.02"
        assert "8.98%" in formatted['effective_rate']
        
    def test_fee_description(self):
        """Testa a descrição das taxas"""
        description = PaymentService.get_fee_description()
        assert description == "R$ 0,99 + 7,99% por transação"
        
    def test_calculate_creator_earnings(self):
        """Testa cálculo de ganhos do criador"""
        # Criar transações mock
        class MockTransaction:
            def __init__(self, amount, status='completed'):
                self.amount = amount
                self.status = status
                self.total_fee = PaymentService.calculate_fees(amount)['total_fee']
                self.net_amount = PaymentService.calculate_fees(amount)['net_amount']
        
        transactions = [
            MockTransaction(100),  # R$ 91.02 líquido
            MockTransaction(50),   # R$ 45.01 líquido
            MockTransaction(200),  # R$ 183.03 líquido
            MockTransaction(100, status='pending')  # Não deve contar
        ]
        
        earnings = PaymentService.calculate_creator_earnings(transactions)
        
        assert earnings['total_gross'] == 350  # 100 + 50 + 200
        assert round(earnings['total_net'], 2) == 319.06  # 91.02 + 45.01 + 183.03
        assert earnings['transaction_count'] == 3  # Apenas completed
        
    def test_monthly_projection(self):
        """Testa projeção mensal de ganhos"""
        # Ganhou R$ 100 em 5 dias
        projection = PaymentService.calculate_monthly_projection(100, 5)
        assert projection == 600  # (100/5) * 30
        
        # Teste com 0 dias
        projection = PaymentService.calculate_monthly_projection(100, 0)
        assert projection == 0


class TestTransactionModel:
    """Testes para o modelo Transaction com cálculo automático"""
    
    @pytest.fixture
    def app(self):
        """Cria app de teste"""
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
            # Criar transação
            transaction = Transaction(
                subscription_id=1,
                amount=100,
                status='pending',
                payment_method='pix'
            )
            
            # Verificar cálculo automático
            assert transaction.fixed_fee == 0.99
            assert transaction.percentage_fee == 7.99
            assert transaction.total_fee == 8.98
            assert transaction.net_amount == 91.02
            
    def test_transaction_recalculation(self, app):
        """Testa recálculo de taxas"""
        with app.app_context():
            transaction = Transaction(
                subscription_id=1,
                amount=50,
                status='pending'
            )
            
            # Verificar valores iniciais
            assert transaction.net_amount == 45.01
            
            # Alterar valor e recalcular
            transaction.amount = 200
            transaction.calculate_fees()
            
            assert transaction.fixed_fee == 0.99
            assert transaction.percentage_fee == 15.98
            assert transaction.total_fee == 16.97
            assert transaction.net_amount == 183.03


# Para executar os testes:
# pytest tests/test_payment_service.py -v