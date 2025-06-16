# safe_db_reset.py
"""Reset seguro do banco de dados"""

import os
import time
import shutil
from datetime import datetime

def reset_database_safe():
    """Reseta o banco de dados de forma segura"""
    
    print("\n⚠️  IMPORTANTE: Certifique-se de que o Flask NÃO está rodando!")
    print("   Pressione Ctrl+C em qualquer terminal rodando 'python run.py'\n")
    
    input("Pressione ENTER quando o Flask estiver parado...")
    
    db_path = "instance/televip.db"
    
    # Tentar múltiplas vezes
    for attempt in range(3):
        try:
            if os.path.exists(db_path):
                # Criar backup com timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{db_path}.backup_{timestamp}"
                shutil.copy2(db_path, backup_path)
                print(f"✅ Backup criado: {backup_path}")
                
                # Tentar remover
                os.remove(db_path)
                print("✅ Banco de dados antigo removido")
                break
        except PermissionError:
            if attempt < 2:
                print(f"\n⚠️  Tentativa {attempt + 1} falhou. Aguardando 2 segundos...")
                time.sleep(2)
            else:
                print("\n❌ Não foi possível remover o banco de dados.")
                print("\n🔧 Alternativa: Vamos renomear o banco atual")
                
                # Renomear em vez de deletar
                old_db = f"{db_path}.old_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    os.rename(db_path, old_db)
                    print(f"✅ Banco renomeado para: {old_db}")
                except:
                    print("\n❌ Falha ao renomear. Tente:")
                    print("1. Fechar todos os terminais/IDEs")
                    print("2. Reiniciar o computador se necessário")
                    return False
    
    # Criar novo banco
    print("\n🔧 Criando novo banco de dados...")
    
    # Importar app aqui para evitar problemas
    from app import create_app, db
    
    app = create_app()
    with app.app_context():
        # Criar todas as tabelas
        db.create_all()
        print("✅ Tabelas criadas!")
        
        # Criar usuário admin
        from app.models import Creator
        
        admin = Creator(
            name="Admin",
            email="admin@televip.com",
            username="admin",
            telegram_username="admin",
            balance=0.0,
            total_earned=0.0,
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow()
        )
        admin.set_password("admin123")
        
        db.session.add(admin)
        
        # Criar usuário de teste
        test_user = Creator(
            name="Usuário Teste",
            email="teste@televip.com",
            username="teste",
            telegram_username="teste_user",
            balance=100.0,  # Saldo inicial para testes
            total_earned=100.0,
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow()
        )
        test_user.set_password("teste123")
        
        db.session.add(test_user)
        db.session.commit()
        
        print("\n✅ Usuários criados:")
        print("\n1. Admin:")
        print("   Email: admin@televip.com")
        print("   Senha: admin123")
        print("\n2. Teste:")
        print("   Email: teste@televip.com")
        print("   Senha: teste123")
        print("   Saldo: R$ 100,00")
    
    return True

if __name__ == "__main__":
    print("🔧 Reset Seguro do Banco de Dados")
    print("=" * 50)
    
    if reset_database_safe():
        print("\n✨ Banco de dados recriado com sucesso!")
        print("\nAgora você pode executar: python run.py")
    else:
        print("\n❌ Falha ao recriar o banco de dados.")