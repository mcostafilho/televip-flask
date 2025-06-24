#!/usr/bin/env python3
"""Verificar a data exata da transação"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Transaction
from datetime import datetime

app = create_app()

with app.app_context():
    # Buscar TODAS as transações
    transactions = Transaction.query.all()
    
    print("\n=== TODAS AS TRANSAÇÕES ===")
    for t in transactions:
        print(f"\nTransação ID: {t.id}")
        print(f"  Valor: R$ {t.amount}")
        print(f"  Status: {t.status}")
        print(f"  Created at (raw): {t.created_at}")
        print(f"  Created at (date): {t.created_at.date() if t.created_at else 'None'}")
        print(f"  Created at (formatted): {t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else 'None'}")
        
        # Verificar o tipo do campo
        print(f"  Tipo do campo created_at: {type(t.created_at)}")
        
    # Verificar a data atual do sistema
    print(f"\n=== INFORMAÇÕES DO SISTEMA ===")
    print(f"Data/hora atual (datetime.now()): {datetime.now()}")
    print(f"Data/hora UTC (datetime.utcnow()): {datetime.utcnow()}")
    
    # Testar a query específica
    from sqlalchemy import func
    test_query = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.count(Transaction.id).label('count')
    ).group_by(
        func.date(Transaction.created_at)
    ).all()
    
    print(f"\n=== RESULTADO DA QUERY POR DATA ===")
    for row in test_query:
        print(f"Data: {row.date}, Transações: {row.count}")