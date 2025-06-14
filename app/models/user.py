from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
import bcrypt

@login_manager.user_loader
def load_user(user_id):
    return Creator.query.get(int(user_id))

class Creator(UserMixin, db.Model):
    __tablename__ = 'creators'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(128))
    balance = db.Column(db.Float, default=0.0)
    total_earned = db.Column(db.Float, default=0.0)
    stripe_customer_id = db.Column(db.String(100))
    telegram_id = db.Column(db.String(50), unique=True)  # ID do Telegram do criador
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    groups = db.relationship('Group', backref='creator', lazy='dynamic')
    withdrawals = db.relationship('Withdrawal', backref='creator', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        try:
            return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
        except:
            return False
    
    def __repr__(self):
        return f'<Creator {self.username}>'