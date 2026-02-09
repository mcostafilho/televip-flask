from app import create_app, db
import os

app = create_app()

@app.shell_context_processor
def make_shell_context():
    # Importar models aqui para evitar importação circular
    from app.models.user import Creator
    from app.models.group import Group
    from app.models.subscription import Subscription
    
    return {'db': db, 'Creator': Creator, 'Group': Group, 'Subscription': Subscription}

if __name__ == '__main__':
    with app.app_context():
        # Garantir que o diretório instance existe
        os.makedirs('instance', exist_ok=True)
        
        # Mostrar configuração do banco
        print(f"Banco de dados: {app.config['SQLALCHEMY_DATABASE_URI']}")

        # Criar tabelas
        db.create_all()
        print("Banco de dados criado/atualizado")

    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'on']
    print(f"TeleVIP rodando em http://localhost:5000 (debug={debug})")
    app.run(debug=debug, host='0.0.0.0', port=5000)