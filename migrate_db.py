#!/usr/bin/env python3
"""
Script para criar dados de teste no banco
"""
import os
import sys
from datetime import datetime

# Adicionar diretório ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def create_test_data():
    """Criar dados de teste"""
    from app import create_app, db
    from app.models import Creator, Group, PricingPlan
    
    app = create_app()
    
    with app.app_context():
        print("📝 Criando dados de teste...\n")
        
        try:
            # Verificar se já existe um criador de teste
            existing = db.session.query(Creator).filter_by(email="teste@example.com").first()
            if existing:
                print("⚠️  Dados de teste já existem!")
                return False
            
            # 1. Criar criador de teste
            creator = Creator(
                email="teste@example.com",
                name="Criador Teste",
                username="criador_teste",
                is_active=True,
                balance=0.0,
                total_earned=0.0
            )
            creator.set_password("senha123")
            db.session.add(creator)
            db.session.flush()
            print("✅ Criador de teste criado")
            
            # 2. Criar grupo de teste
            group = Group(
                name="Grupo VIP Teste",
                telegram_id="-1001234567890",
                creator_id=creator.id,
                description="Grupo de teste para desenvolvimento",
                is_active=True,
                total_subscribers=0
            )
            db.session.add(group)
            db.session.flush()
            print("✅ Grupo de teste criado")
            
            # 3. Criar planos (sem description se não existir no modelo)
            plans_data = [
                {
                    "name": "Plano Mensal",
                    "price": 99.90,
                    "duration_days": 30
                },
                {
                    "name": "Plano Trimestral",
                    "price": 269.90,
                    "duration_days": 90
                },
                {
                    "name": "Plano Anual", 
                    "price": 999.90,
                    "duration_days": 365
                }
            ]
            
            for plan_data in plans_data:
                plan = PricingPlan(
                    group_id=group.id,
                    name=plan_data["name"],
                    price=plan_data["price"],
                    duration_days=plan_data["duration_days"],
                    is_active=True
                )
                db.session.add(plan)
                print(f"✅ Plano '{plan_data['name']}' criado")
            
            # Commit final
            db.session.commit()
            
            print("\n✅ Dados de teste criados com sucesso!")
            print("\n📌 Informações de teste:")
            print(f"   Email: teste@example.com")
            print(f"   Senha: senha123")
            print(f"   Username: criador_teste")
            print(f"   Grupo Telegram ID: -1001234567890")
            print(f"\n🔗 Link do bot para teste:")
            
            bot_username = os.getenv('BOT_USERNAME', 'seu_bot')
            print(f"   https://t.me/{bot_username}?start=g_-1001234567890")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao criar dados: {e}")
            db.session.rollback()
            return False

def check_database():
    """Verificar estrutura do banco"""
    from app import create_app, db
    from sqlalchemy import inspect
    
    app = create_app()
    
    with app.app_context():
        print("🔍 Verificando banco de dados...\n")
        
        inspector = inspect(db.engine)
        
        # Listar tabelas
        tables = inspector.get_table_names()
        print(f"📊 Tabelas encontradas: {len(tables)}")
        for table in tables:
            print(f"   ✓ {table}")
            
            # Mostrar colunas da tabela pricing_plans
            if table == 'pricing_plans':
                print(f"\n   📋 Colunas de {table}:")
                columns = inspector.get_columns(table)
                for col in columns:
                    print(f"      - {col['name']} ({col['type']})")
        
        return True

def main():
    print("""
╔══════════════════════════════════════╗
║    🧪 CRIAR DADOS DE TESTE          ║
╚══════════════════════════════════════╝
""")
    
    # Primeiro verificar o banco
    check_database()
    
    print("\n" + "="*40 + "\n")
    
    # Criar dados
    if create_test_data():
        print("\n✅ Tudo pronto!")
        print("\n📌 Próximos passos:")
        print("1. Execute o bot: python bot/main.py")
        print("2. No Telegram, procure seu bot")
        print("3. Clique no link de teste gerado acima")
        print("4. Escolha um plano e teste o pagamento")
    else:
        print("\n❌ Erro ao criar dados de teste")

if __name__ == "__main__":
    main()