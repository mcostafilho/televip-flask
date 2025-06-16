#!/usr/bin/env python3
"""
Script para limpar todos os dados do banco e reiniciar do zero
Execute: python reset_database.py
"""
import os
import sys
from datetime import datetime

def reset_database():
    """Limpar banco de dados e recriar do zero"""
    print("⚠️  ATENÇÃO: Este script irá APAGAR TODOS OS DADOS!")
    print("="*50)
    
    confirm = input("\n❓ Tem certeza que deseja continuar? Digite 'SIM' para confirmar: ")
    
    if confirm != 'SIM':
        print("\n❌ Operação cancelada!")
        return
    
    print("\n🔄 Iniciando reset do banco de dados...")
    
    try:
        # Importar app e modelos
        from app import create_app, db
        from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
        
        app = create_app()
        
        with app.app_context():
            # Backup do banco atual (opcional)
            db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            if os.path.exists(db_path):
                backup_name = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                print(f"\n📦 Criando backup em: {backup_name}")
                import shutil
                shutil.copy2(db_path, backup_name)
            
            print("\n🗑️  Removendo todas as tabelas...")
            # Dropar todas as tabelas
            db.drop_all()
            
            print("🔨 Recriando tabelas vazias...")
            # Recriar tabelas
            db.create_all()
            
            print("\n✅ Banco de dados resetado com sucesso!")
            
            # Perguntar se deseja criar admin
            create_admin = input("\n❓ Deseja criar o usuário admin? (s/n): ")
            
            if create_admin.lower() == 's':
                print("\n👤 Criando usuário administrador...")
                
                admin = Creator(
                    name='Mauro Admin',
                    email='mauro_lcf@example.com',
                    username='mauroadmin'
                )
                admin.set_password('admin123')
                
                db.session.add(admin)
                db.session.commit()
                
                print("\n✅ Admin criado com sucesso!")
                print("📧 Email: mauro_lcf@example.com")
                print("🔑 Senha: admin123")
            
            # Mostrar estatísticas
            print("\n📊 Status do banco:")
            print(f"   Criadores: {Creator.query.count()}")
            print(f"   Grupos: {Group.query.count()}")
            print(f"   Planos: {PricingPlan.query.count()}")
            print(f"   Assinaturas: {Subscription.query.count()}")
            print(f"   Transações: {Transaction.query.count()}")
            print(f"   Saques: {Withdrawal.query.count()}")
            
            print("\n✅ Processo concluído!")
            print("\n🚀 Próximos passos:")
            print("1. Execute o Flask: python run.py")
            print("2. Faça login com o admin (se criado)")
            print("3. Configure seus grupos e planos")
            print("4. Teste o sistema do zero!")
            
    except Exception as e:
        print(f"\n❌ Erro ao resetar banco: {e}")
        import traceback
        traceback.print_exc()

def clean_specific_tables():
    """Limpar apenas tabelas específicas mantendo usuários"""
    print("\n🧹 Limpeza seletiva de tabelas")
    print("="*50)
    
    print("\nEscolha o que deseja limpar:")
    print("1. Apenas transações e assinaturas")
    print("2. Grupos e tudo relacionado")
    print("3. Tudo exceto usuários")
    print("4. Cancelar")
    
    choice = input("\nEscolha (1-4): ")
    
    from app import create_app, db
    from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
    
    app = create_app()
    
    with app.app_context():
        if choice == '1':
            print("\n🗑️  Limpando transações e assinaturas...")
            Transaction.query.delete()
            Subscription.query.delete()
            
            # Resetar contadores
            groups = Group.query.all()
            for group in groups:
                group.total_subscribers = 0
            
            # Resetar saldos
            creators = Creator.query.all()
            for creator in creators:
                creator.balance = 0
                creator.total_earned = 0
            
            db.session.commit()
            print("✅ Transações e assinaturas removidas!")
            
        elif choice == '2':
            print("\n🗑️  Limpando grupos e dados relacionados...")
            Transaction.query.delete()
            Subscription.query.delete()
            PricingPlan.query.delete()
            Group.query.delete()
            
            # Resetar saldos
            creators = Creator.query.all()
            for creator in creators:
                creator.balance = 0
                creator.total_earned = 0
            
            db.session.commit()
            print("✅ Grupos e dados relacionados removidos!")
            
        elif choice == '3':
            print("\n🗑️  Limpando tudo exceto usuários...")
            Withdrawal.query.delete()
            Transaction.query.delete()
            Subscription.query.delete()
            PricingPlan.query.delete()
            Group.query.delete()
            
            # Resetar dados dos usuários
            creators = Creator.query.all()
            for creator in creators:
                creator.balance = 0
                creator.total_earned = 0
            
            db.session.commit()
            print("✅ Dados limpos, usuários mantidos!")
        
        else:
            print("❌ Operação cancelada!")
            return
        
        # Mostrar estatísticas
        print("\n📊 Status do banco:")
        print(f"   Criadores: {Creator.query.count()}")
        print(f"   Grupos: {Group.query.count()}")
        print(f"   Assinaturas: {Subscription.query.count()}")
        print(f"   Transações: {Transaction.query.count()}")

def main():
    """Menu principal"""
    print("""
╔══════════════════════════════════════╗
║     🗑️  RESET DATABASE - TeleVIP     ║
╚══════════════════════════════════════╝
    """)
    
    print("Escolha uma opção:\n")
    print("1. Reset completo (apaga TUDO)")
    print("2. Limpeza seletiva (mantém alguns dados)")
    print("3. Sair")
    
    choice = input("\nOpção (1-3): ")
    
    if choice == '1':
        reset_database()
    elif choice == '2':
        clean_specific_tables()
    else:
        print("\n👋 Até logo!")

if __name__ == '__main__':
    main()