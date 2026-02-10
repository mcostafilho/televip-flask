# app/models/report.py
from app import db
from datetime import datetime


class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(50), nullable=False)  # conteudo_ilicito, fraude, abuso, outro
    target_name = db.Column(db.String(200), nullable=False)  # Nome do grupo ou criador
    description = db.Column(db.Text, nullable=False)
    reporter_email = db.Column(db.String(200))  # Opcional
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Report {self.report_type} - {self.status}>'
