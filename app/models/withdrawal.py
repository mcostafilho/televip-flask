# app/models/withdrawal.py
from app import db
from datetime import datetime

class Withdrawal(db.Model):
    __tablename__ = 'withdrawals'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creators.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    pix_key = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    # Informações adicionais
    notes = db.Column(db.Text)  # Notas do admin
    transaction_id = db.Column(db.String(100))  # ID da transação PIX
    
    # NÃO adicionar relationship aqui - será definido no modelo Creator
    
    def __repr__(self):
        return f'<Withdrawal R${self.amount} - {self.status}>'
    
    def mark_as_processing(self):
        """Marca saque como em processamento"""
        self.status = 'processing'
        self.processed_at = datetime.utcnow()
    
    def mark_as_completed(self, transaction_id=None):
        """Marca saque como concluído"""
        self.status = 'completed'
        self.processed_at = datetime.utcnow()
        if transaction_id:
            self.transaction_id = transaction_id
    
    def mark_as_failed(self, reason=None):
        """Marca saque como falhado"""
        self.status = 'failed'
        self.processed_at = datetime.utcnow()
        if reason:
            self.notes = reason