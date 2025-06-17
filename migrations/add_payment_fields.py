"""
Migration para adicionar campos faltantes nas tabelas
Execute este arquivo: python migrations/add_payment_fields.py
"""
import os
import sys
from datetime import datetime

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar configurações diretamente
from dotenv import load_dotenv
load_dotenv()

# Configurar SQLAlchemy diretamente
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

def add_payment_fields():
    """Adicionar campos de pagamento faltantes"""
    
    # Obter URL do banco de dados
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL não configurado no .env")
        return False
    
    # Criar engine
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as connection:
            print("✅ Conectado ao banco de dados")
            
            # Adicionar campos na tabela transactions
            print("\n🔄 Adicionando campos na tabela transactions...")
            
            # Verificar e adicionar stripe_session_id
            try:
                connection.execute(text("""
                    ALTER TABLE transactions 
                    ADD COLUMN stripe_session_id VARCHAR(255)
                """))
                connection.commit()
                print("✅ Campo stripe_session_id adicionado")
            except (OperationalError, ProgrammingError) as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print("⚠️  Campo stripe_session_id já existe")
                else:
                    print(f"❌ Erro ao adicionar stripe_session_id: {e}")
            
            # Verificar e adicionar payment_id
            try:
                connection.execute(text("""
                    ALTER TABLE transactions 
                    ADD COLUMN payment_id VARCHAR(255)
                """))
                connection.commit()
                print("✅ Campo payment_id adicionado")
            except (OperationalError, ProgrammingError) as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print("⚠️  Campo payment_id já existe")
                else:
                    print(f"❌ Erro ao adicionar payment_id: {e}")
            
            # Criar índices
            print("\n🔄 Criando índices...")
            
            indices = [
                ("idx_transactions_stripe_session_id", "transactions", "stripe_session_id"),
                ("idx_transactions_payment_id", "transactions", "payment_id"),
                ("idx_transactions_status", "transactions", "status"),
                ("idx_subscriptions_telegram_user_id", "subscriptions", "telegram_user_id"),
            ]
            
            for index_name, table_name, column_name in indices:
                try:
                    # Para PostgreSQL
                    if 'postgresql' in database_url:
                        connection.execute(text(f"""
                            CREATE INDEX IF NOT EXISTS {index_name} 
                            ON {table_name}({column_name})
                        """))
                    else:
                        # Para SQLite ou outros
                        connection.execute(text(f"""
                            CREATE INDEX {index_name} 
                            ON {table_name}({column_name})
                        """))
                    connection.commit()
                    print(f"✅ Índice {index_name} criado")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"⚠️  Índice {index_name} já existe")
                    else:
                        print(f"❌ Erro ao criar índice {index_name}: {e}")
            
            # Verificar campos
            print("\n📊 Verificando estrutura da tabela transactions:")
            
            # Query específica para o tipo de banco
            if 'postgresql' in database_url:
                result = connection.execute(text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'transactions' 
                    AND column_name IN ('stripe_session_id', 'payment_id')
                    ORDER BY column_name
                """))
            else:
                # Para SQLite
                result = connection.execute(text("""
                    PRAGMA table_info(transactions)
                """))
            
            print("Colunas encontradas:")
            for row in result:
                if 'postgresql' in database_url:
                    print(f"  - {row[0]}: {row[1]}")
                else:
                    # SQLite retorna diferente
                    if row[1] in ['stripe_session_id', 'payment_id']:
                        print(f"  - {row[1]}: {row[2]}")
            
            print("\n✅ Migration concluída com sucesso!")
            return True
            
    except Exception as e:
        print(f"\n❌ Erro durante migration: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Iniciando migration...")
    print(f"📅 Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    # Verificar arquivo .env
    if not os.path.exists('.env'):
        print("❌ Arquivo .env não encontrado!")
        print("Crie um arquivo .env com DATABASE_URL configurado")
        sys.exit(1)
    
    success = add_payment_fields()
    
    if not success:
        print("\n❌ Migration falhou!")
        sys.exit(1)
    else:
        print("\n✨ Tudo pronto!")