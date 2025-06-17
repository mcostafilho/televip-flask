"""
Modelo Transaction com cálculo automático de taxas
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, DECIMAL, Boolean
from sqlalchemy.orm import relationship
from app.models import db

class Transaction(db.Model):
    """
    Modelo de transação com taxas automáticas
    Taxa fixa: R$ 0,99
    Taxa percentual: 7,99%
    """
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey('subscriptions.id'), nullable=False)
    
    # Valores
    amount = Column(DECIMAL(10, 2), nullable=False)  # Valor total pago
    original_amount = Column(DECIMAL(10, 2))  # Valor original (para descontos)
    discount_percentage = Column(DECIMAL(5, 2), default=0)  # Desconto aplicado
    
    # Taxas calculadas automaticamente
    fixed_fee = Column(DECIMAL(10, 2), default=Decimal('0.99'))
    percentage_fee = Column(DECIMAL(10, 2))  # 7.99% do amount
    total_fee = Column(DECIMAL(10, 2))  # fixed_fee + percentage_fee
    net_amount = Column(DECIMAL(10, 2))  # amount - total_fee
    
    # Status e método
    status = Column(String(20), default='pending')  # pending, completed, failed, refunded
    payment_method = Column(String(20), default='stripe')  # stripe, pix
    
    # IDs externos
    stripe_payment_intent_id = Column(String(255))
    stripe_session_id = Column(String(255))
    receipt_hash = Column(String(64))  # Hash do comprovante PIX
    verification_score = Column(DECIMAL(3, 2))  # Score de verificação PIX
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    refunded_at = Column(DateTime)
    
    # Relacionamentos
    subscription = relationship('Subscription', back_populates='transactions')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calculate_fees()
    
    def calculate_fees(self):
        """
        Calcular taxas automaticamente
        Taxa fixa: R$ 0,99
        Taxa percentual: 7,99%
        """
        if self.amount:
            amount = Decimal(str(self.amount))
            
            # Taxa fixa
            self.fixed_fee = Decimal('0.99')
            
            # Taxa percentual (7,99%)
            self.percentage_fee = amount * Decimal('0.0799')
            
            # Taxa total
            self.total_fee = self.fixed_fee + self.percentage_fee
            
            # Valor líquido para o criador
            self.net_amount = amount - self.total_fee
    
    def __repr__(self):
        return f'<Transaction {self.id} - R$ {self.amount} - {self.status}>'