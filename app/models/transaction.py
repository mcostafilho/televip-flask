# app/models/transaction.py
from app import db
from datetime import datetime
from app.services.payment_service import PaymentService

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    
    # Valores financeiros
    amount = db.Column(db.Float, nullable=False)  # Valor bruto
    fixed_fee = db.Column(db.Float, nullable=False, default=0.99)  # Taxa fixa R$ 0,99
    percentage_fee = db.Column(db.Float, nullable=False)  # Taxa percentual (7,99% do valor)
    total_fee = db.Column(db.Float, nullable=False)  # Taxa total (fixa + percentual)
    net_amount = db.Column(db.Float, nullable=False)  # Valor líquido para o criador
    
    # Status e método
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed, refunded
    payment_method = db.Column(db.String(20), default='pix')  # pix, stripe, credit_card
    
    # IDs de pagamento externos
    stripe_payment_intent_id = db.Column(db.String(100))
    pix_transaction_id = db.Column(db.String(100))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    refunded_at = db.Column(db.DateTime)
    
    # Relacionamento com subscription
    subscription = db.relationship('Subscription', backref='transactions_list')
    
    def __init__(self, **kwargs):
        """Inicializa transação calculando taxas automaticamente"""
        super(Transaction, self).__init__(**kwargs)
        if 'amount' in kwargs and kwargs['amount'] > 0:
            self.calculate_fees()
    
    def calculate_fees(self):
        """Calcula e atualiza as taxas da transação"""
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
        return fees
    
    def get_fee_breakdown(self):
        """Retorna breakdown formatado das taxas"""
        return {
            'gross': f"R$ {self.amount:.2f}",
            'fixed_fee': f"R$ {self.fixed_fee:.2f}",
            'percentage_fee': f"R$ {self.percentage_fee:.2f} (7,99%)",
            'total_fee': f"R$ {self.total_fee:.2f}",
            'net': f"R$ {self.net_amount:.2f}",
            'effective_rate': f"{(self.total_fee / self.amount * 100):.2f}%" if self.amount > 0 else "0%"
        }
    
    def mark_as_paid(self):
        """Marca transação como paga"""
        self.status = 'completed'
        self.paid_at = datetime.utcnow()
        
    def mark_as_failed(self):
        """Marca transação como falhada"""
        self.status = 'failed'
        
    def process_refund(self):
        """Processa reembolso da transação"""
        if self.status == 'completed':
            self.status = 'refunded'
            self.refunded_at = datetime.utcnow()
            return True
        return False
    
    def __repr__(self):
        return f'<Transaction #{self.id} R${self.amount:.2f} - Fee: R${self.total_fee:.2f} - Net: R${self.net_amount:.2f} - {self.status}>'