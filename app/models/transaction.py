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
        super().__init__(**kwargs)
        self.calculate_fees()
    
    def calculate_fees(self):
        """
        Calcular taxas automaticamente
        Taxa fixa: R$ 0,99
        Taxa percentual: 9,99%
        """
        if self.amount:
            # Taxa fixa
            self.fixed_fee = 0.99
            
            # Taxa percentual (9,99%)
            self.percentage_fee = float(self.amount) * 0.0999
            
            # Taxa total
            self.total_fee = self.fixed_fee + self.percentage_fee
            
            # Compatibilidade com campos antigos
            self.fee = self.total_fee
            self.fee_amount = self.total_fee
            
            # Valor líquido para o criador
            self.net_amount = float(self.amount) - self.total_fee
    
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