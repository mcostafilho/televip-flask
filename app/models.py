class Subscription(db.Model):
    """Modelo para assinaturas de grupos"""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Relacionamentos
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    pricing_plan_id = db.Column(db.Integer, db.ForeignKey('pricing_plans.id'), nullable=False)
    
    # Informações do assinante
    telegram_user_id = db.Column(db.String(50), nullable=False, index=True)
    telegram_username = db.Column(db.String(100))
    telegram_first_name = db.Column(db.String(100))
    telegram_last_name = db.Column(db.String(100))
    
    # Status e datas
    status = db.Column(db.String(20), default='pending')  # pending, active, expired, cancelled, suspended
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    
    # ADICIONAR ESTE CAMPO
    auto_renew = db.Column(db.Boolean, default=False)  # Por padrão false, sem renovação automática
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    group = db.relationship('Group', back_populates='subscriptions')
    pricing_plan = db.relationship('PricingPlan')
    transactions = db.relationship('Transaction', back_populates='subscription', lazy='dynamic')
    
    @property
    def is_active(self):
        """Verifica se a assinatura está ativa"""
        if self.status != 'active':
            return False
        if self.end_date and self.end_date < datetime.utcnow():
            return False
        return True
    
    @property
    def days_remaining(self):
        """Dias restantes da assinatura"""
        if not self.end_date or not self.is_active:
            return 0
        delta = self.end_date - datetime.utcnow()
        return max(0, delta.days)
    
    def __repr__(self):
        return f'<Subscription {self.id} - User {self.telegram_user_id}>'