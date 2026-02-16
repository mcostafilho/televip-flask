from app import db
from datetime import datetime


class LeakIncident(db.Model):
    __tablename__ = 'leak_incidents'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    telegram_user_id = db.Column(db.String(50), nullable=False)
    telegram_username = db.Column(db.String(100))
    plan_name = db.Column(db.String(50))
    subscription_status = db.Column(db.String(20))
    leaked_text_preview = db.Column(db.Text)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)

    group = db.relationship('Group', backref='leak_incidents')
    subscription = db.relationship('Subscription', backref='leak_incidents')

    def __repr__(self):
        return f'<LeakIncident {self.telegram_username} @ {self.detected_at}>'
