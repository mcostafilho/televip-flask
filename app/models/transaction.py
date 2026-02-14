# app/models/transaction.py
from app import db
from datetime import datetime

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'))
    
    # Valores financeiros
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # Compatibilidade
    net_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # Taxas detalhadas
    fixed_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0.99)
    percentage_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    fee_amount = db.Column(db.Numeric(10, 2), default=0)  # Alias para compatibilidade
    
    # IDs de pagamento - CAMPOS IMPORTANTES
    stripe_session_id = db.Column(db.String(255))
    payment_id = db.Column(db.String(255))
    stripe_payment_intent_id = db.Column(db.String(100))
    stripe_invoice_id = db.Column(db.String(100))
    billing_reason = db.Column(db.String(50))  # 'subscription_create', 'subscription_cycle'
    pix_transaction_id = db.Column(db.String(100))
    
    # Status e método
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(20), default='stripe')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    
    # Relacionamentos
    subscription = db.relationship('Subscription', backref='transactions')
    
    def __init__(self, **kwargs):
        """Inicializar transação com cálculo automático de taxas"""
        self._custom_fixed_fee = kwargs.pop('custom_fixed_fee', None)
        self._custom_percentage_fee = kwargs.pop('custom_percentage_fee', None)
        super().__init__(**kwargs)
        if self.amount and self.amount > 0:
            self.calculate_fees()

    def calculate_fees(self):
        """Calcular taxas automaticamente (usa custom fees se fornecidos)"""
        from app.services.payment_service import PaymentService

        if not self.amount or self.amount <= 0:
            self.fixed_fee = 0
            self.percentage_fee = 0
            self.total_fee = 0
            self.net_amount = 0
            return

        fees = PaymentService.calculate_fees(
            self.amount,
            fixed_fee=getattr(self, '_custom_fixed_fee', None),
            percentage_fee=getattr(self, '_custom_percentage_fee', None)
        )
        self.fixed_fee = fees['fixed_fee']
        self.percentage_fee = fees['percentage_fee']
        self.total_fee = fees['total_fee']
        self.net_amount = fees['net_amount']

        # Compatibilidade com campos antigos
        self.fee = self.total_fee
        self.fee_amount = self.total_fee
    
    def get_fee_breakdown(self):
        """Retornar breakdown das taxas para exibição"""
        return {
            'gross': f"R$ {self.amount:.2f}",
            'fixed_fee': f"R$ {self.fixed_fee:.2f}",
            'percentage_fee': f"R$ {self.percentage_fee:.2f}",
            'total_fee': f"R$ {self.total_fee:.2f}",
            'net': f"R$ {self.net_amount:.2f}"
        }
    
    def __repr__(self):
        return f'<Transaction {self.id} - R$ {self.amount} - {self.status}>'