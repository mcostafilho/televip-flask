from app import db
from datetime import datetime

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
    amount = db.Column(db.Float, nullable=False)
    fee = db.Column(db.Float, nullable=False)  # 1% da plataforma
    net_amount = db.Column(db.Float, nullable=False)  # amount - fee
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    payment_method = db.Column(db.String(20), default='stripe')
    stripe_payment_intent_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Transaction R${self.amount} - {self.status}>'