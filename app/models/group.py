from app import db
from datetime import datetime

class Group(db.Model):
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    telegram_id = db.Column(db.String(50), unique=True)
    invite_link = db.Column(db.String(200))
    creator_id = db.Column(db.Integer, db.ForeignKey('creators.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    total_subscribers = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    pricing_plans = db.relationship('PricingPlan', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    subscriptions = db.relationship('Subscription', backref='group', lazy='dynamic')
    
    def __repr__(self):
        return f'<Group {self.name}>'

class PricingPlan(db.Model):
    __tablename__ = 'pricing_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stripe_price_id = db.Column(db.String(100))  # ID do preço no Stripe
    stripe_product_id = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<PricingPlan {self.name} - R${self.price}>'