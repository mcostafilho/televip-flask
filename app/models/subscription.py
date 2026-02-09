# app/models/subscription.py
from app import db
from datetime import datetime

# Importar PaymentService apenas quando necessário para evitar importação circular
# from app.services.payment_service import PaymentService

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('pricing_plans.id'), nullable=False)
    telegram_user_id = db.Column(db.String(50), nullable=False)
    telegram_username = db.Column(db.String(100))
    stripe_subscription_id = db.Column(db.String(100))
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, expired, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    plan = db.relationship('PricingPlan', backref='subscriptions')
    transactions = db.relationship('Transaction', backref='subscription', lazy='dynamic')
    
    def __repr__(self):
        return f'<Subscription {self.telegram_username} - {self.status}>'


class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    
    # Valores financeiros
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # Compatibilidade
    net_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # Novas colunas de taxa detalhada
    fixed_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0.99)
    percentage_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    pix_transaction_id = db.Column(db.String(100))
    
    # Status e método
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(20), default='stripe')
    stripe_payment_intent_id = db.Column(db.String(100))
    stripe_session_id = db.Column(db.String(200), index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        """Inicializa transação calculando taxas automaticamente"""
        super(Transaction, self).__init__(**kwargs)
        
        # Se tem amount, calcular taxas automaticamente
        if 'amount' in kwargs and kwargs['amount'] > 0:
            self.calculate_fees()
    
    def calculate_fees(self):
        """Calcula as taxas da transação"""
        # Importar aqui para evitar importação circular
        from app.services.payment_service import PaymentService
        
        if not self.amount or self.amount <= 0:
            self.fixed_fee = 0
            self.percentage_fee = 0
            self.total_fee = 0
            self.net_amount = 0
            return
        
        fees = PaymentService.calculate_fees(self.amount)
        self.fixed_fee = fees['fixed_fee']
        self.percentage_fee = fees['percentage_fee']
        self.total_fee = fees['total_fee']
        self.net_amount = fees['net_amount']
        
        # Manter compatibilidade com campo 'fee' antigo
        self.fee = self.total_fee
        
        return fees
    
    def __repr__(self):
        return f'<Transaction R${self.amount} - {self.status}>'