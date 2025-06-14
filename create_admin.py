"""
Script para criar usuário administrador
Execute: python create_admin.py
"""

from app import create_app, db
from app.models import Creator

def create_admin():
    app = create_app()
    
    with app.app_context():
        # Verificar se o admin já existe
        admin = Creator.query.filter_by(email='mauro_lcf@example.com').first()
        
        if admin:
            print("⚠️  Admin já existe!")
            print("🔐 Resetando senha para: admin123")
            admin.set_password('admin123')
            db.session.commit()
        else:
            # Criar novo admin
            admin = Creator(
                name='Mauro Admin',
                email='mauro_lcf@example.com',
                username='mauroadmin'
            )
            admin.set_password('admin123')
            
            db.session.add(admin)
            db.session.commit()
            
            print("✅ Admin criado com sucesso!")
        
        print("\n📧 Email: mauro_lcf@example.com")
        print("🔑 Senha: admin123")
        print("\n🚀 Agora você pode fazer login!")

if __name__ == '__main__':
    create_admin()