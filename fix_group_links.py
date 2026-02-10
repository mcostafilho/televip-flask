"""
Script para corrigir os links dos grupos e verificar dados
Salve como: fix_group_links.py
Execute: python fix_group_links.py
"""
import os
import sys
from datetime import datetime

# Adicionar o diretório ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Group, Creator, PricingPlan

def fix_group_links():
    """Corrigir links e verificar grupos"""
    app = create_app()
    
    with app.app_context():
        print("🔍 Verificando e corrigindo grupos...")
        print("=" * 50)
        
        # Obter username do bot
        bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME') or 'seu_bot'
        print(f"Bot Username: @{bot_username}")
        print()
        
        # Listar todos os grupos
        groups = Group.query.all()
        
        if not groups:
            print("❌ Nenhum grupo encontrado no banco de dados!")
            print("\n💡 Para criar um grupo:")
            print("1. Acesse o dashboard web: http://localhost:5000")
            print("2. Faça login como criador")
            print("3. Crie um novo grupo")
            print("\nOU execute: python setup_test_data.py")
            return
        
        print(f"📊 Total de grupos: {len(groups)}")
        print()
        
        for group in groups:
            print(f"Grupo: {group.name}")
            print(f"  - ID no banco: {group.id}")
            print(f"  - Telegram ID: {group.telegram_id}")
            print(f"  - Status: {'✅ Ativo' if group.is_active else '❌ Inativo'}")
            print(f"  - Criador: {group.creator.name if group.creator else 'N/A'}")
            
            # Verificar planos
            plans = PricingPlan.query.filter_by(group_id=group.id, is_active=True).all()
            print(f"  - Planos ativos: {len(plans)}")
            
            # Gerar links corretos
            print(f"\n  🔗 Links corretos para este grupo:")
            print(f"  Link por slug: https://t.me/{bot_username}?start=g_{group.invite_slug}")
            
            if plans:
                print(f"\n  💰 Planos disponíveis:")
                for plan in plans:
                    print(f"    • {plan.name}: R$ {plan.price:.2f} ({plan.duration_days} dias)")
            else:
                print(f"  ⚠️  Nenhum plano ativo! Crie planos no dashboard.")
            
            print("-" * 50)
        
        # Mostrar grupo ativo para teste
        active_groups = [g for g in groups if g.is_active]
        if active_groups:
            test_group = active_groups[0]
            print(f"\n✅ Grupo recomendado para teste: {test_group.name}")
            print(f"🔗 Use este link: https://t.me/{bot_username}?start=g_{test_group.invite_slug}")
            print("\n⚠️  IMPORTANTE: Use o slug aleatório, não o ID numérico!")
        else:
            print("\n⚠️  Nenhum grupo ativo! Ative pelo menos um grupo no dashboard.")

def create_test_group_if_needed():
    """Criar grupo de teste se não existir nenhum"""
    app = create_app()
    
    with app.app_context():
        # Verificar se existe algum grupo
        if Group.query.count() > 0:
            return
        
        print("\n🆕 Criando grupo de teste...")
        
        # Criar ou obter criador
        creator = Creator.query.first()
        if not creator:
            creator = Creator(
                telegram_id="123456789",
                username="criador_teste",
                name="Criador Teste",
                email="teste@example.com",
                is_active=True
            )
            db.session.add(creator)
            db.session.commit()
        
        # Criar grupo
        group = Group(
            name="Grupo VIP Teste",
            description="Grupo de teste para desenvolvimento",
            telegram_id="-1001234567890",  # ID fictício
            creator_id=creator.id,
            category="educacao",
            is_active=True,
            is_private=True
        )
        db.session.add(group)
        db.session.commit()
        
        # Criar planos
        plans = [
            {"name": "Mensal", "price": 29.90, "duration_days": 30},
            {"name": "Trimestral", "price": 79.90, "duration_days": 90},
            {"name": "Anual", "price": 299.90, "duration_days": 365}
        ]
        
        for plan_data in plans:
            plan = PricingPlan(
                group_id=group.id,
                **plan_data,
                description=f"Acesso {plan_data['name'].lower()} ao grupo",
                is_active=True
            )
            db.session.add(plan)
        
        db.session.commit()
        print("✅ Grupo de teste criado!")

if __name__ == "__main__":
    fix_group_links()
    
    # Perguntar se quer criar grupo de teste
    groups = Group.query.count() if 'app' in globals() else 0
    if groups == 0:
        resp = input("\n❓ Nenhum grupo encontrado. Criar grupo de teste? (s/n): ")
        if resp.lower() == 's':
            create_test_group_if_needed()
            print("\n🔄 Execute o script novamente para ver os links corretos.")