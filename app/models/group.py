import json
import secrets
from app import db
from datetime import datetime

class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    telegram_id = db.Column(db.String(50), unique=True)
    invite_link = db.Column(db.String(200))
    invite_slug = db.Column(db.String(16), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(6))
    creator_id = db.Column(db.Integer, db.ForeignKey('creators.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    total_subscribers = db.Column(db.Integer, default=0)
    last_broadcast_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Lista de exceção: Telegram IDs que o bot NÃO deve remover do grupo
    # JSON array: [{"telegram_id": "123456789", "name": "João", "added_at": "2026-02-11"}]
    whitelist_json = db.Column(db.Text, default='[]')
    # Lista de exceção do SISTEMA (oculta dos criadores): Telegram IDs protegidos pela plataforma
    # JSON array: [{"telegram_id": "123456789", "added_at": "2026-02-12", "reason": "investigate"}]
    system_whitelist_json = db.Column(db.Text, default='[]')
    # Tipo de chat: 'group' (grupo/supergrupo) ou 'channel' (canal)
    chat_type = db.Column(db.String(20), default='group')
    cover_image_url = db.Column(db.String(500))
    is_public = db.Column(db.Boolean, default=False)
    anti_leak_enabled = db.Column(db.Boolean, default=False)

    # Relacionamentos
    pricing_plans = db.relationship('PricingPlan', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    subscriptions = db.relationship('Subscription', backref='group', lazy='dynamic')

    def __repr__(self):
        return f'<Group {self.name}>'

    def get_whitelist(self):
        """Retorna a lista de exceção como lista de dicts"""
        try:
            return json.loads(self.whitelist_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def add_to_whitelist(self, telegram_id, name=''):
        """Adiciona um Telegram ID à lista de exceção"""
        whitelist = self.get_whitelist()
        # Evitar duplicatas
        if any(e['telegram_id'] == str(telegram_id) for e in whitelist):
            return False
        whitelist.append({
            'telegram_id': str(telegram_id),
            'name': name.strip(),
            'added_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        })
        self.whitelist_json = json.dumps(whitelist)
        return True

    def remove_from_whitelist(self, telegram_id):
        """Remove um Telegram ID da lista de exceção"""
        whitelist = self.get_whitelist()
        new_list = [e for e in whitelist if e['telegram_id'] != str(telegram_id)]
        if len(new_list) == len(whitelist):
            return False
        self.whitelist_json = json.dumps(new_list)
        return True

    def is_whitelisted(self, telegram_id):
        """Verifica se um Telegram ID está na lista de exceção"""
        return any(e['telegram_id'] == str(telegram_id) for e in self.get_whitelist())

    def get_system_whitelist(self):
        """Retorna a system whitelist (oculta) como lista de dicts"""
        try:
            return json.loads(self.system_whitelist_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def add_to_system_whitelist(self, telegram_id, reason=''):
        """Adiciona um Telegram ID à system whitelist (oculta)"""
        whitelist = self.get_system_whitelist()
        if any(e['telegram_id'] == str(telegram_id) for e in whitelist):
            return False
        whitelist.append({
            'telegram_id': str(telegram_id),
            'added_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            'reason': reason
        })
        self.system_whitelist_json = json.dumps(whitelist)
        return True

    def remove_from_system_whitelist(self, telegram_id):
        """Remove um Telegram ID da system whitelist (oculta)"""
        whitelist = self.get_system_whitelist()
        new_list = [e for e in whitelist if e['telegram_id'] != str(telegram_id)]
        if len(new_list) == len(whitelist):
            return False
        self.system_whitelist_json = json.dumps(new_list)
        return True

    def is_system_whitelisted(self, telegram_id):
        """Verifica se um Telegram ID está na system whitelist (oculta)"""
        return any(e['telegram_id'] == str(telegram_id) for e in self.get_system_whitelist())

class PricingPlan(db.Model):
    __tablename__ = 'pricing_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stripe_price_id = db.Column(db.String(100))  # ID do preço no Stripe
    stripe_product_id = db.Column(db.String(100))
    is_lifetime = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<PricingPlan {self.name} - R${self.price}>'