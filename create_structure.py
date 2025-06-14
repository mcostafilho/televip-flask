#!/usr/bin/env python3
"""
Script para criar a estrutura completa do projeto TeleVIP
Uso: python create_structure.py
"""

import os
import sys

def create_directory(path):
    """Cria um diretório se não existir"""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"✅ Criado diretório: {path}")
    else:
        print(f"⏭️  Diretório já existe: {path}")

def create_file(path, content=""):
    """Cria um arquivo com conteúdo opcional"""
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Criado arquivo: {path}")
    else:
        print(f"⏭️  Arquivo já existe: {path}")

def create_init_file(path):
    """Cria um arquivo __init__.py vazio"""
    create_file(os.path.join(path, "__init__.py"))

def main():
    print("🚀 Criando estrutura do projeto TeleVIP...\n")
    
    # Diretório raiz (assumindo que o script está na raiz do projeto)
    root_dir = os.getcwd()
    
    # Estrutura de diretórios
    directories = [
        "app",
        "app/models",
        "app/routes",
        "app/services",
        "app/templates",
        "app/templates/auth",
        "app/templates/dashboard",
        "app/templates/admin",
        "app/templates/public",
        "app/static",
        "app/static/css",
        "app/static/js",
        "app/static/img",
        "app/utils",
        "bot",
        "bot/handlers",
        "bot/keyboards",
        "bot/utils",
        "migrations",
        "tests",
        "tests/unit",
        "tests/integration",
        "instance",
        "logs",
    ]
    
    # Criar todos os diretórios
    print("📁 Criando diretórios...")
    for directory in directories:
        create_directory(os.path.join(root_dir, directory))
    
    print("\n📄 Criando arquivos...")
    
    # Arquivos na raiz
    root_files = {
        "config.py": '''import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///televip.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Stripe
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Telegram
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    BOT_USERNAME = os.environ.get('BOT_USERNAME')
    
    # App
    PLATFORM_FEE = 0.01  # 1%
    MIN_WITHDRAWAL = 10.0
    
    # Admin emails
    ADMIN_EMAILS = ['mauro_lcf@example.com', 'admin@televip.com']
''',
        
        "run.py": '''from app import create_app, db
from app.models import Creator, Group, Subscription

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'Creator': Creator, 'Group': Group, 'Subscription': Subscription}

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Banco de dados criado/atualizado")
    
    print("🚀 TeleVIP rodando em http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
''',
        
        ".env.example": '''# Flask
SECRET_KEY=your-secret-key-here
FLASK_ENV=development

# Database
DATABASE_URL=sqlite:///televip.db

# Stripe
STRIPE_PUBLIC_KEY=pk_test_your_public_key_here
STRIPE_SECRET_KEY=sk_test_your_secret_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here

# Telegram Bot
BOT_TOKEN=your_bot_token_here
BOT_USERNAME=your_bot_username_here

# Admin
ADMIN_EMAIL=admin@televip.com
''',
        
        ".gitignore": '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
.venv/

# Flask
instance/
.webassets-cache
*.db
*.sqlite

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local

# Logs
logs/
*.log

# OS
.DS_Store
Thumbs.db

# Testing
.pytest_cache/
.coverage
htmlcov/

# Stripe
stripe-cli/
''',
        
        "requirements.txt": '''# Core
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-Migrate==4.0.5
Flask-Cors==4.0.0

# Database
SQLAlchemy==2.0.23

# Authentication
bcrypt==4.1.2

# Payments
stripe==7.8.0

# Telegram Bot
python-telegram-bot==20.7

# Environment
python-dotenv==1.0.0

# Production
gunicorn==21.2.0

# Development
pytest==7.4.3
black==23.12.1
flake8==7.0.0
''',
        
        "README.md": '''# 📱 TeleVIP - Sistema de Assinaturas para Grupos Telegram

Sistema completo para monetização de grupos no Telegram com pagamentos via Stripe.

## 🚀 Funcionalidades

- ✅ Gestão de múltiplos grupos
- ✅ Planos de assinatura personalizados
- ✅ Pagamentos via Stripe
- ✅ Bot Telegram automatizado
- ✅ Dashboard para criadores
- ✅ Painel administrativo
- ✅ Sistema de saques

## 📋 Pré-requisitos

- Python 3.8+
- PostgreSQL ou SQLite
- Conta Stripe
- Bot no Telegram

## 🛠️ Instalação

1. Clone o repositório
2. Crie um ambiente virtual: `python -m venv venv`
3. Ative o ambiente: `source venv/bin/activate` (Linux/Mac) ou `venv\\Scripts\\activate` (Windows)
4. Instale as dependências: `pip install -r requirements.txt`
5. Configure o `.env` baseado no `.env.example`
6. Execute: `python run.py`

## 📁 Estrutura do Projeto

```
televip-flask/
├── app/              # Aplicação Flask
├── bot/              # Bot Telegram
├── migrations/       # Migrações do banco
├── tests/           # Testes
└── config.py        # Configurações
```

## 📝 Licença

MIT License
'''
    }
    
    # Criar arquivos na raiz
    for filename, content in root_files.items():
        create_file(os.path.join(root_dir, filename), content)
    
    # Criar __init__.py nos diretórios Python
    python_dirs = [
        "app",
        "app/models",
        "app/routes", 
        "app/services",
        "app/utils",
        "bot",
        "bot/handlers",
        "bot/keyboards",
        "bot/utils",
        "tests",
        "tests/unit",
        "tests/integration"
    ]
    
    for dir_path in python_dirs:
        create_init_file(os.path.join(root_dir, dir_path))
    
    # app/__init__.py com conteúdo
    create_file(os.path.join(root_dir, "app", "__init__.py"), '''from flask import Flask
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
    
    # Criar diretórios necessários
    import os
    os.makedirs('logs', exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    
    return app
''')
    
    # Criar arquivos dos models
    models_files = {
        "user.py": "# Model Creator (usuário)\n",
        "group.py": "# Models Group e PricingPlan\n",
        "subscription.py": "# Models Subscription e Transaction\n",
        "withdrawal.py": "# Model Withdrawal\n"
    }
    
    for filename, content in models_files.items():
        create_file(os.path.join(root_dir, "app", "models", filename), content)
    
    # Criar arquivos das rotas
    routes_files = {
        "auth.py": '''from flask import Blueprint

bp = Blueprint('auth', __name__, url_prefix='/auth')

# TODO: Implementar rotas de autenticação
''',
        "dashboard.py": '''from flask import Blueprint
from flask_login import login_required

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.route('/')
@login_required
def index():
    return "Dashboard - TODO"
''',
        "groups.py": '''from flask import Blueprint
from flask_login import login_required

bp = Blueprint('groups', __name__, url_prefix='/groups')

# TODO: Implementar rotas de grupos
''',
        "admin.py": '''from flask import Blueprint
from flask_login import login_required

bp = Blueprint('admin', __name__, url_prefix='/admin')

# TODO: Implementar rotas administrativas
''',
        "webhooks.py": '''from flask import Blueprint

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')

@bp.route('/stripe', methods=['POST'])
def stripe_webhook():
    # TODO: Implementar webhook do Stripe
    return '', 200
''',
        "api.py": '''from flask import Blueprint

bp = Blueprint('api', __name__, url_prefix='/api')

# TODO: Implementar API para o bot
'''
    }
    
    for filename, content in routes_files.items():
        create_file(os.path.join(root_dir, "app", "routes", filename), content)
    
    # Criar arquivos dos services
    services_files = {
        "stripe_service.py": "# Serviço de integração com Stripe\n",
        "telegram_service.py": "# Serviço de comunicação com Telegram\n",
        "payment_service.py": "# Lógica de processamento de pagamentos\n"
    }
    
    for filename, content in services_files.items():
        create_file(os.path.join(root_dir, "app", "services", filename), content)
    
    # Criar arquivos utils
    utils_files = {
        "decorators.py": '''from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        if current_user.email not in ['mauro_lcf@example.com', 'admin@televip.com']:
            flash('Acesso negado. Apenas administradores.', 'error')
            return redirect(url_for('dashboard.index'))
        
        return f(*args, **kwargs)
    return decorated_function
''',
        "helpers.py": "# Funções auxiliares\n"
    }
    
    for filename, content in utils_files.items():
        create_file(os.path.join(root_dir, "app", "utils", filename), content)
    
    # Criar templates base
    templates = {
        "base.html": '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}TeleVIP{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
    {% block extra_css %}{% endblock %}
</head>
<body>
    {% block content %}{% endblock %}
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
''',
        "auth/login.html": '''{% extends "base.html" %}
{% block title %}Login - TeleVIP{% endblock %}
{% block content %}
<!-- TODO: Implementar formulário de login -->
{% endblock %}
''',
        "auth/register.html": '''{% extends "base.html" %}
{% block title %}Registro - TeleVIP{% endblock %}
{% block content %}
<!-- TODO: Implementar formulário de registro -->
{% endblock %}
''',
        "dashboard/index.html": '''{% extends "base.html" %}
{% block title %}Dashboard - TeleVIP{% endblock %}
{% block content %}
<!-- TODO: Implementar dashboard -->
{% endblock %}
''',
        "admin/index.html": '''{% extends "base.html" %}
{% block title %}Admin - TeleVIP{% endblock %}
{% block content %}
<!-- TODO: Implementar painel admin -->
{% endblock %}
'''
    }
    
    for filepath, content in templates.items():
        create_file(os.path.join(root_dir, "app", "templates", filepath), content)
    
    # Criar arquivos estáticos
    create_file(os.path.join(root_dir, "app", "static", "css", "style.css"), 
                "/* TeleVIP Custom Styles */\n")
    create_file(os.path.join(root_dir, "app", "static", "js", "main.js"), 
                "// TeleVIP JavaScript\n")
    
    # Criar arquivos do bot
    bot_files = {
        "main.py": '''#!/usr/bin/env python3
"""
Bot principal do TeleVIP
"""
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("🤖 Bot TeleVIP iniciando...")
    # TODO: Implementar bot
    
if __name__ == '__main__':
    main()
''',
        "handlers/start.py": "# Handler do comando /start\n",
        "handlers/payment.py": "# Handler de pagamentos\n",
        "handlers/subscription.py": "# Handler de assinaturas\n",
        "keyboards/menus.py": "# Teclados inline do bot\n",
        "utils/database.py": "# Conexão com banco de dados\n",
        "utils/stripe_bot.py": "# Integração Stripe no bot\n"
    }
    
    for filepath, content in bot_files.items():
        create_file(os.path.join(root_dir, "bot", filepath), content)
    
    # Criar arquivo de teste básico
    create_file(os.path.join(root_dir, "tests", "test_basic.py"), '''def test_app_exists():
    """Testa se a aplicação pode ser criada"""
    from app import create_app
    app = create_app()
    assert app is not None
''')
    
    print("\n✅ Estrutura do projeto criada com sucesso!")
    print("\n📋 Próximos passos:")
    print("1. Copie .env.example para .env e configure suas variáveis")
    print("2. Crie um ambiente virtual: python -m venv venv")
    print("3. Ative o ambiente virtual")
    print("4. Instale as dependências: pip install -r requirements.txt")
    print("5. Execute: python run.py")
    print("\n💡 Dica: Comece implementando os models em app/models/")

if __name__ == "__main__":
    main()