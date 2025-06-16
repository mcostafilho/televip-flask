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
    balance = db.Column(db.Float, default=0.0)
    total_earned = db.Column(db.Float, default=0.0)
    pix_key = db.Column(db.String(200))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    
    # Relacionamentos
    groups = db.relationship('Group', backref='creator', lazy='dynamic')
    withdrawals = db.relationship('Withdrawal', backref='creator', lazy='dynamic')
    
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