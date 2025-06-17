"""
Modelos do banco de dados para o sistema TeleVIP
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db


class Creator(UserMixin, db.Model):
    """Modelo para criadores de conteúdo"""
    __tablename__ = 'creators'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255))
    full_name = db.Column(db.String(200))
    
    # Informações do Telegram
    telegram_username = db.Column(db.String(100))
    telegram_user_id = db.Column(db.String(50), unique=True)
    
    # Informações financeiras
    available_balance = db.Column(db.Numeric(10, 2), default=0)
    pending_balance = db.Column(db.Numeric(10, 2), default=0)
    total_earned = db.Column(db.Numeric(10, 2), default=0)
    
    # Informações de pagamento
    pix_key = db.Column(db.String(200))
    pix_key_type = db.Column(db.String(50))  # cpf, email, phone, random
    
    # Status e datas
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relacionamentos
    groups = db.relationship('Group', back_populates='creator', lazy='dynamic')
    withdrawals = db.relationship('Withdrawal', back_populates='creator', lazy='dynamic')
    
    def set_password(self, password):
        """Definir senha criptografada"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verificar senha"""
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        """Retornar ID como string para Flask-Login"""
        return str(self.id)
    
    @property
    def total_balance(self):
        """Saldo total (disponível + pendente)"""
        return (self.available_balance or 0) + (self.pending_balance or 0)
    
    def __repr__(self):
        return f'<Creator {self.username}>'


class Group(db.Model):
    """Modelo para grupos do Telegram"""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creators.id'), nullable=False)
    
    # Informações do grupo
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    telegram_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    invite_link = db.Column(db.String(500))
    
    # Configurações
    is_active = db.Column(db.Boolean, default=True)
    is_public = db.Column(db.Boolean, default=True)
    max_members = db.Column(db.Integer)
    
    # Estatísticas
    total_members = db.Column(db.Integer, default=0)
    total_revenue = db.Column(db.Numeric(10, 2), default=0)
    
    # Datas
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    creator = db.relationship('Creator', back_populates='groups')
    plans = db.relationship('PricingPlan', back_populates='group', lazy='dynamic', cascade='all, delete-orphan')
    subscriptions = db.relationship('Subscription', back_populates='group', lazy='dynamic')
    
    @property
    def active_members(self):
        """Contar membros ativos"""
        return self.subscriptions.filter_by(status='active').count()
    
    @property
    def cheapest_plan(self):
        """Retornar plano mais barato"""
        return self.plans.filter_by(is_active=True).order_by(PricingPlan.price).first()
    
    def __repr__(self):
        return f'<Group {self.name}>'


class PricingPlan(db.Model):
    """Modelo para planos de preços"""
    __tablename__ = 'pricing_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    
    # Informações do plano
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    
    # Configurações
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    max_subscribers = db.Column(db.Integer)  # Limite de assinantes para este plano
    
    # Benefícios (JSON)
    benefits = db.Column(db.JSON, default=list)
    
    # Datas
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    group = db.relationship('Group', back_populates='plans')
    subscriptions = db.relationship('Subscription', back_populates='plan', lazy='dynamic')
    
    @property
    def daily_price(self):
        """Preço por dia"""
        return self.price / self.duration_days if self.duration_days > 0 else 0
    
    @property
    def active_subscribers(self):
        """Contar assinantes ativos"""
        return self.subscriptions.filter_by(status='active').count()
    
    def __repr__(self):
        return f'<PricingPlan {self.name} - R${self.price}>'


class Subscription(db.Model):
    """Modelo para assinaturas"""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('pricing_plans.id'), nullable=False)
    
    # Informações do assinante
    telegram_user_id = db.Column(db.String(50), nullable=False, index=True)
    telegram_username = db.Column(db.String(100))
    telegram_first_name = db.Column(db.String(100))
    telegram_last_name = db.Column(db.String(100))
    
    # Status
    status = db.Column(db.String(50), default='pending')  # pending, active, cancelled, expired
    
    # Datas
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=False)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Flags
    auto_renew = db.Column(db.Boolean, default=False)
    notified_expiring = db.Column(db.Boolean, default=False)
    notified_expired = db.Column(db.Boolean, default=False)
    
    # Relacionamentos
    group = db.relationship('Group', back_populates='subscriptions')
    plan = db.relationship('PricingPlan', back_populates='subscriptions')
    transactions = db.relationship('Transaction', back_populates='subscription', lazy='dynamic')
    
    @property
    def is_active(self):
        """Verificar se assinatura está ativa"""
        return self.status == 'active' and self.end_date > datetime.utcnow()
    
    @property
    def days_remaining(self):
        """Dias restantes na assinatura"""
        if self.is_active:
            return (self.end_date - datetime.utcnow()).days
        return 0
    
    def __repr__(self):
        return f'<Subscription {self.telegram_user_id} - {self.group.name}>'


class Transaction(db.Model):
    """Modelo para transações financeiras"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    
    # Valores
    amount = db.Column(db.Numeric(10, 2), nullable=False)  # Valor total
    fee = db.Column(db.Numeric(10, 2), nullable=False)  # Taxa da plataforma
    net_amount = db.Column(db.Numeric(10, 2), nullable=False)  # Valor líquido para o criador
    
    # Informações de pagamento
    payment_method = db.Column(db.String(50))  # stripe, pix, etc
    payment_id = db.Column(db.String(200))  # ID genérico do pagamento
    stripe_session_id = db.Column(db.String(200), index=True)  # ID da sessão do Stripe
    stripe_payment_intent_id = db.Column(db.String(200), index=True)  # ID do payment intent
    pix_transaction_id = db.Column(db.String(200))  # ID da transação PIX
    
    # Status
    status = db.Column(db.String(50), default='pending')  # pending, completed, failed, refunded
    
    # Datas
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    refunded_at = db.Column(db.DateTime)
    
    # Relacionamentos
    subscription = db.relationship('Subscription', back_populates='transactions')
    
    def __repr__(self):
        return f'<Transaction {self.id} - R${self.amount} - {self.status}>'


class Withdrawal(db.Model):
    """Modelo para saques"""
    __tablename__ = 'withdrawals'
    
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('creators.id'), nullable=False)
    
    # Valores
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    fee = db.Column(db.Numeric(10, 2), default=0)
    net_amount = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Informações de pagamento
    payment_method = db.Column(db.String(50))  # pix, bank_transfer
    pix_key = db.Column(db.String(200))
    pix_key_type = db.Column(db.String(50))
    bank_account_info = db.Column(db.JSON)
    
    # Status
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    
    # Informações adicionais
    transaction_id = db.Column(db.String(200))
    notes = db.Column(db.Text)
    admin_notes = db.Column(db.Text)
    
    # Datas
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Relacionamentos
    creator = db.relationship('Creator', back_populates='withdrawals')
    
    def __repr__(self):
        return f'<Withdrawal {self.id} - R${self.amount} - {self.status}>'


class SystemSettings(db.Model):
    """Modelo para configurações do sistema"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.JSON)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemSettings {self.key}>'


class AuditLog(db.Model):
    """Modelo para log de auditoria"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    user_type = db.Column(db.String(50))  # creator, admin, system
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.Integer)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user_type}:{self.user_id}>'


# Índices compostos para melhor performance
db.Index('idx_subscription_user_group', Subscription.telegram_user_id, Subscription.group_id)
db.Index('idx_transaction_subscription_status', Transaction.subscription_id, Transaction.status)
db.Index('idx_withdrawal_creator_status', Withdrawal.creator_id, Withdrawal.status)