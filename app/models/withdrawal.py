from app import db
from datetime import datetime

class Withdrawal(db.Model):
    __tablename__ = 'withdrawals'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creators.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    pix_key = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)  # Notas do admin
    
    def __repr__(self):
        return f'<Withdrawal R${self.amount} - {self.status}>'