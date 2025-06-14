#!/usr/bin/env python3
"""
Script para migrar o banco de dados
Adiciona campos faltantes sem perder dados
"""
import sqlite3
import os
from app import create_app, db

def check_column_exists(conn, table_name, column_name):
    """Verifica se uma coluna existe na tabela"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(column[1] == column_name for column in columns)

def migrate_database():
    """Adiciona colunas faltantes ao banco de dados"""
    print("🔄 Iniciando migração do banco de dados...")
    
    # Conectar ao banco SQLite
    db_path = 'instance/televip.db'
    if not os.path.exists(db_path):
        db_path = 'televip.db'
    
    if not os.path.exists(db_path):
        print("❌ Banco de dados não encontrado!")
        print("Execute 'python run.py' primeiro para criar o banco.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Adicionar telegram_id à tabela creators se não existir
        if not check_column_exists(conn, 'creators', 'telegram_id'):
            print("📝 Adicionando coluna telegram_id à tabela creators...")
            cursor.execute('ALTER TABLE creators ADD COLUMN telegram_id VARCHAR(50)')
            conn.commit()
            print("✅ Coluna telegram_id adicionada!")
        else:
            print("✅ Coluna telegram_id já existe")
        
        # Verificar outras colunas que podem estar faltando
        tables_to_check = {
            'groups': ['invite_link', 'total_subscribers'],
            'pricing_plans': ['stripe_price_id'],
            'subscriptions': ['stripe_subscription_id'],
            'transactions': ['stripe_payment_intent_id']
        }
        
        for table, columns in tables_to_check.items():
            # Verificar se a tabela existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if cursor.fetchone():
                for column in columns:
                    if not check_column_exists(conn, table, column):
                        print(f"📝 Adicionando coluna {column} à tabela {table}...")
                        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} VARCHAR(200)')
                        conn.commit()
                        print(f"✅ Coluna {column} adicionada!")
        
        print("\n✅ Migração concluída com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro durante a migração: {e}")
        conn.rollback()
    finally:
        conn.close()

def create_all_tables():
    """Cria todas as tabelas usando SQLAlchemy"""
    print("\n🔨 Criando/atualizando tabelas via SQLAlchemy...")
    app = create_app()
    with app.app_context():
        db.create_all()
        print("✅ Tabelas criadas/atualizadas!")

if __name__ == "__main__":
    print("=== Migração do Banco de Dados TeleVIP ===\n")
    
    # Primeiro, migrar colunas existentes
    migrate_database()
    
    # Depois, garantir que todas as tabelas existam
    create_all_tables()
    
    print("\n✅ Processo completo! Você já pode usar o sistema.")