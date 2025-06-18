#!/usr/bin/env python3
"""Criar transação de teste para hoje"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Transaction, Subscription
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    # Buscar primeira assinatura ativa
    sub = Subscription.query.filter_by(status='active').first()
    if not sub:
        sub = Subscription.query.first()
    
    if sub:
        # Criar transação para hoje
        now = datetime.now(timezone.utc)
        
        trans = Transaction(
            subscription_id=sub.id,
            amount=29.90,
            status='completed',
            payment_method='stripe',
            created_at=now,
            paid_at=now
        )
        
        # Adicionar campos de taxa se existirem
        if hasattr(trans, 'fixed_fee'):
            trans.fixed_fee = 0.99
            trans.percentage_fee = 2.39
            trans.total_fee = 3.38
            trans.net_amount = 26.52
        
        db.session.add(trans)
        db.session.commit()
        
        print(f"✅ Transação de teste criada para hoje: {now.date()}")
        print(f"   Valor: R$ 29.90")
    else:
        print("❌ Nenhuma assinatura encontrada!")
