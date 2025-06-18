#!/usr/bin/env python3
"""
Adicionar campo paid_at nas transações
Execute: python add_paid_at_field.py
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text
from datetime import datetime

app = create_app()

with app.app_context():
    print("📝 Adicionando campo paid_at...")
    
    try:
        # Adicionar campo paid_at se não existir
        db.engine.execute(text(
            "ALTER TABLE transactions ADD COLUMN paid_at DATETIME"
        ))
        print("✅ Campo paid_at adicionado")
    except Exception as e:
        if 'duplicate' in str(e).lower() or 'already exists' in str(e).lower():
            print("ℹ️  Campo paid_at já existe")
        else:
            print(f"❌ Erro: {e}")
    
    # Atualizar transações existentes
    try:
        result = db.engine.execute(text("""
            UPDATE transactions 
            SET paid_at = created_at 
            WHERE status = 'completed' AND paid_at IS NULL
        """))
        print(f"✅ {result.rowcount} transações atualizadas")
    except Exception as e:
        print(f"⚠️  Erro ao atualizar: {e}")
    
    print("✅ Migração concluída!")
