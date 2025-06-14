from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_cors import CORS

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    # Inicializar extensões
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    
    # Configurar login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    
    # Registrar blueprints
    from app.routes import auth, dashboard, groups, admin, webhooks, api
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(groups.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(webhooks.bp)
    app.register_blueprint(api.bp)
    
    # Registrar context processors
    from app.utils.context_processor import inject_global_vars
    app.context_processor(inject_global_vars)
    
    # Criar diretórios necessários
    import os
    os.makedirs('logs', exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    
    return app