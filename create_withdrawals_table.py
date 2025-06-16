# create_withdrawals_table.py
"""Script para criar a tabela withdrawals no banco de dados"""

from app import create_app, db
from sqlalchemy import text

def create_withdrawals_table():
    """Cria a tabela withdrawals se não existir"""
    app = create_app()
    
    with app.app_context():
        try:
            # Verificar se a tabela já existe
            inspector = db.inspect(db.engine)
            if 'withdrawals' in inspector.get_table_names():
                print("✅ Tabela 'withdrawals' já existe!")
                return
            
            # Criar tabela withdrawals
            db.engine.execute(text("""
                CREATE TABLE withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    amount FLOAT NOT NULL,
                    pix_key VARCHAR(200) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed_at DATETIME,
                    notes TEXT,
                    transaction_id VARCHAR(100),
                    FOREIGN KEY (creator_id) REFERENCES creators (id)
                )
            """))
            
            print("✅ Tabela 'withdrawals' criada com sucesso!")
            
            # Adicionar campos faltantes na tabela creators se necessário
            columns = [col['name'] for col in inspector.get_columns('creators')]
            
            if 'balance' not in columns:
                db.engine.execute(text("ALTER TABLE creators ADD COLUMN balance FLOAT DEFAULT 0"))
                print("✅ Coluna 'balance' adicionada à tabela 'creators'")
            
            if 'total_earned' not in columns:
                db.engine.execute(text("ALTER TABLE creators ADD COLUMN total_earned FLOAT DEFAULT 0"))
                print("✅ Coluna 'total_earned' adicionada à tabela 'creators'")
            
            if 'pix_key' not in columns:
                db.engine.execute(text("ALTER TABLE creators ADD COLUMN pix_key VARCHAR(200)"))
                print("✅ Coluna 'pix_key' adicionada à tabela 'creators'")
                
        except Exception as e:
            print(f"❌ Erro: {e}")

if __name__ == "__main__":
    print("🔧 Criando tabela withdrawals...")
    create_withdrawals_table()