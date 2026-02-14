# app/models/user.py
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class Creator(UserMixin, db.Model):
    __tablename__ = 'creators'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    telegram_id = db.Column(db.String(50))
    telegram_username = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    bio = db.Column(db.Text)
    avatar_url = db.Column(db.String(500))

    # Campos financeiros
    balance = db.Column(db.Numeric(10, 2), default=0)
    total_earned = db.Column(db.Numeric(10, 2), default=0)
    _pix_key_encrypted = db.Column('pix_key', db.String(500))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)

    # Aparencia da pagina publica
    page_theme = db.Column(db.String(20), default='galactic', nullable=False, server_default='galactic')

    # Taxas personalizadas (NULL = usar padrao do sistema)
    custom_fixed_fee = db.Column(db.Numeric(10, 2), nullable=True)
    custom_percentage_fee = db.Column(db.Numeric(10, 4), nullable=True)

    # Controle de troca de username (cooldown 14 dias)
    username_changed_at = db.Column(db.DateTime, nullable=True)

    # Aceite dos termos (prova jurídica)
    terms_accepted_at = db.Column(db.DateTime)
    terms_ip = db.Column(db.String(45))
    terms_user_agent = db.Column(db.String(500))
    
    # Relacionamentos
    groups = db.relationship('Group', backref='creator', lazy='dynamic')
    withdrawals = db.relationship('Withdrawal', backref='creator', lazy='dynamic')
    
    @property
    def pix_key(self):
        """Descriptografa a PIX key ao acessar"""
        if not self._pix_key_encrypted:
            return None
        from app.utils.security import decrypt_data
        decrypted = decrypt_data(self._pix_key_encrypted)
        if decrypted is None:
            import logging
            logging.getLogger(__name__).warning(
                'Failed to decrypt PIX key for creator %s', self.id
            )
        return decrypted

    @pix_key.setter
    def pix_key(self, value):
        """Encripta a PIX key ao salvar"""
        if value:
            from app.utils.security import encrypt_data
            self._pix_key_encrypted = encrypt_data(value)
        else:
            self._pix_key_encrypted = None

    def set_password(self, password):
        """Define a senha do usuário"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica a senha do usuário"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def get_fee_rates(self):
        """Retorna taxas efetivas (custom > faixa por assinantes > default)"""
        from app.services.payment_service import PaymentService

        # Custom fees (admin) tem prioridade
        if self.custom_fixed_fee is not None or self.custom_percentage_fee is not None:
            return {
                'fixed_fee': self.custom_fixed_fee if self.custom_fixed_fee is not None else PaymentService.FIXED_FEE,
                'percentage_fee': self.custom_percentage_fee if self.custom_percentage_fee is not None else PaymentService.PERCENTAGE_FEE,
                'is_custom': True,
                'tier_info': None
            }

        # Contar assinantes ativos para determinar faixa
        from app.models.group import Group, Subscription
        from sqlalchemy import func
        subscriber_count = db.session.query(func.count(Subscription.id)).join(
            Group
        ).filter(
            Group.creator_id == self.id,
            Subscription.status == 'active'
        ).scalar() or 0

        tiered_pct = PaymentService.get_tiered_percentage(subscriber_count)

        return {
            'fixed_fee': PaymentService.FIXED_FEE,
            'percentage_fee': tiered_pct,
            'is_custom': tiered_pct != PaymentService.PERCENTAGE_FEE,
            'tier_info': {
                'subscriber_count': subscriber_count,
                'percentage_display': f"{tiered_pct * 100:.2f}".replace('.', ',') + "%"
            }
        }

    def update_last_login(self):
        """Atualiza último login"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Creator {self.username}>'

# Função para o Flask-Login
# Esta função deve ser colocada no __init__.py ou em outro lugar, não aqui
def load_user(user_id):
    return Creator.query.get(int(user_id))