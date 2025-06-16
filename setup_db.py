# setup_db.py
"""
Script para configurar o banco de dados e migrations
Execute com: python setup_db.py
"""

import os
import sys
from app import create_app, db
from flask_migrate import init, migrate, upgrade

def setup_database():
    """Configura o banco de dados e aplica migrations"""
    
    # Criar aplicação
    app = create_app()
    
    with app.app_context():
        try:
            # Criar todas as tabelas (caso não existam)
            print("📦 Criando estrutura do banco de dados...")
            db.create_all()
            print("✅ Tabelas criadas com sucesso!")
            
            # Inicializar migrations se não existir
            if not os.path.exists('migrations'):
                print("\n🔧 Inicializando migrations...")
                init()
                print("✅ Migrations inicializadas!")
            
            # Criar migration para as novas colunas
            print("\n📝 Criando migration para colunas de taxa...")
            try:
                migrate(message='Add detailed fee columns to transactions')
                print("✅ Migration criada!")
            except Exception as e:
                print(f"⚠️  Migration já existe ou erro: {e}")
            
            # Aplicar migrations
            print("\n🚀 Aplicando migrations...")
            try:
                upgrade()
                print("✅ Migrations aplicadas com sucesso!")
            except Exception as e:
                print(f"❌ Erro ao aplicar migrations: {e}")
                
                # Tentar adicionar colunas manualmente
                print("\n🔨 Tentando adicionar colunas manualmente...")
                try:
                    add_columns_manually()
                    print("✅ Colunas adicionadas manualmente!")
                except Exception as e2:
                    print(f"❌ Erro ao adicionar colunas: {e2}")
            
            print("\n✨ Configuração concluída!")
            
        except Exception as e:
            print(f"\n❌ Erro geral: {e}")
            sys.exit(1)

def add_columns_manually():
    """Adiciona colunas manualmente se migration falhar"""
    from sqlalchemy import text
    
    # Verificar se colunas já existem
    inspector = db.inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('transactions')]
    
    # Adicionar colunas que faltam
    with db.engine.connect() as conn:
        if 'fixed_fee' not in columns:
            conn.execute(text('ALTER TABLE transactions ADD COLUMN fixed_fee FLOAT DEFAULT 0.99'))
            conn.commit()
            
        if 'percentage_fee' not in columns:
            conn.execute(text('ALTER TABLE transactions ADD COLUMN percentage_fee FLOAT DEFAULT 0'))
            conn.commit()
            
        if 'total_fee' not in columns:
            conn.execute(text('ALTER TABLE transactions ADD COLUMN total_fee FLOAT DEFAULT 0'))
            conn.commit()
            
        if 'pix_transaction_id' not in columns:
            conn.execute(text('ALTER TABLE transactions ADD COLUMN pix_transaction_id VARCHAR(100)'))
            conn.commit()
    
    # Atualizar valores
    with db.engine.connect() as conn:
        # Calcular taxas para transações existentes
        conn.execute(text("""
            UPDATE transactions 
            SET percentage_fee = ROUND(amount * 0.0799, 2),
                total_fee = ROUND(0.99 + (amount * 0.0799), 2),
                net_amount = ROUND(amount - (0.99 + (amount * 0.0799)), 2)
            WHERE fixed_fee = 0.99
        """))
        conn.commit()

if __name__ == '__main__':
    print("🚀 Configurando banco de dados TeleVIP...")
    print("=" * 50)
    setup_database()