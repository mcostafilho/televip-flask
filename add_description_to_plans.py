"""
Migration para adicionar campo description na tabela pricing_plans
Salve como: add_description_to_plans.py
Execute: python add_description_to_plans.py
"""
import os
import sys
from datetime import datetime

# Adicionar o diretório ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Verificar se psycopg2 está instalado (para PostgreSQL)
try:
    import psycopg2
    has_psycopg2 = True
except:
    has_psycopg2 = False

import sqlite3

def get_database_info():
    """Obter informações do banco de dados do arquivo .env"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    
    if not os.path.exists(env_path):
        print("❌ Arquivo .env não encontrado!")
        return None, None
    
    database_url = None
    with open(env_path, 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if 'DATABASE_URL' in line:
                    database_url = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    
    if not database_url:
        print("❌ DATABASE_URL não encontrado no .env")
        return None, None
    
    # Determinar tipo de banco
    if 'postgresql' in database_url or 'postgres' in database_url:
        return 'postgresql', database_url
    elif 'sqlite' in database_url:
        if 'sqlite:///' in database_url:
            db_path = database_url.replace('sqlite:///', '')
        else:
            db_path = 'instance/app.db'
        return 'sqlite', db_path
    else:
        return 'unknown', database_url

def add_description_postgresql(database_url):
    """Adicionar campo description no PostgreSQL"""
    if not has_psycopg2:
        print("❌ psycopg2 não instalado. Execute: pip install psycopg2-binary")
        return False
    
    try:
        import urllib.parse
        url = urllib.parse.urlparse(database_url)
        
        conn = psycopg2.connect(
            host=url.hostname,
            port=url.port or 5432,
            database=url.path[1:],
            user=url.username,
            password=url.password
        )
        cursor = conn.cursor()
        print("✅ Conectado ao PostgreSQL")
        
        # Adicionar campo description
        try:
            cursor.execute("""
                ALTER TABLE pricing_plans 
                ADD COLUMN description TEXT
            """)
            conn.commit()
            print("✅ Campo description adicionado")
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
            print("⚠️  Campo description já existe")
        
        # Adicionar campo features se não existir
        try:
            cursor.execute("""
                ALTER TABLE pricing_plans 
                ADD COLUMN features TEXT
            """)
            conn.commit()
            print("✅ Campo features adicionado")
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
            print("⚠️  Campo features já existe")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def add_description_sqlite(db_path):
    """Adicionar campo description no SQLite"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print(f"✅ Conectado ao SQLite: {db_path}")
        
        # Verificar colunas existentes
        cursor.execute("PRAGMA table_info(pricing_plans)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Adicionar description se não existir
        if 'description' not in columns:
            try:
                cursor.execute("""
                    ALTER TABLE pricing_plans 
                    ADD COLUMN description TEXT
                """)
                conn.commit()
                print("✅ Campo description adicionado")
            except Exception as e:
                print(f"❌ Erro ao adicionar description: {e}")
        else:
            print("⚠️  Campo description já existe")
        
        # Adicionar features se não existir
        if 'features' not in columns:
            try:
                cursor.execute("""
                    ALTER TABLE pricing_plans 
                    ADD COLUMN features TEXT
                """)
                conn.commit()
                print("✅ Campo features adicionado")
            except Exception as e:
                print(f"❌ Erro ao adicionar features: {e}")
        else:
            print("⚠️  Campo features já existe")
        
        # Atualizar planos existentes com descrições padrão
        cursor.execute("SELECT id, name FROM pricing_plans WHERE description IS NULL")
        plans = cursor.fetchall()
        
        if plans:
            print(f"\n📝 Atualizando {len(plans)} planos com descrições padrão...")
            for plan_id, plan_name in plans:
                description = f"Acesso completo ao grupo VIP"
                cursor.execute(
                    "UPDATE pricing_plans SET description = ? WHERE id = ?",
                    (description, plan_id)
                )
            conn.commit()
            print("✅ Descrições padrão adicionadas")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚀 Adicionando campo description aos planos")
    print(f"📅 Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    # Obter informações do banco
    db_type, db_info = get_database_info()
    
    if not db_type:
        return False
    
    print(f"📊 Tipo de banco: {db_type}")
    
    # Executar migration
    if db_type == 'postgresql':
        success = add_description_postgresql(db_info)
    elif db_type == 'sqlite':
        success = add_description_sqlite(db_info)
    else:
        print(f"❌ Tipo de banco não suportado: {db_type}")
        return False
    
    if success:
        print("\n✅ Migration concluída!")
        print("\n📝 Próximos passos:")
        print("1. Reinicie o servidor Flask")
        print("2. Reinicie o bot")
        print("3. Os planos agora têm campo description")
    else:
        print("\n❌ Migration falhou!")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)