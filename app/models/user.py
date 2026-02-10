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
    telegram_id = db.Column(db.String(50))
    telegram_username = db.Column(db.String(50))
    
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
        try:
            from app.utils.security import decrypt_data
            return decrypt_data(self._pix_key_encrypted)
        except Exception:
            return self._pix_key_encrypted  # Fallback para dados antigos nao encriptados

    @pix_key.setter
    def pix_key(self, value):
        """Encripta a PIX key ao salvar"""
        if value:
            try:
                from app.utils.security import encrypt_data
                self._pix_key_encrypted = encrypt_data(value)
            except Exception:
                self._pix_key_encrypted = value
        else:
            self._pix_key_encrypted = None

    def set_password(self, password):
        """Define a senha do usuário"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica a senha do usuário"""
        return check_password_hash(self.password_hash, password)
    
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