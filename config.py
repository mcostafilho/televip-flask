# config.py
"""
Arquivo de configuração da aplicação Flask
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

# Carregar variáveis de ambiente
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Configurações base da aplicação"""
    
    # Configurações gerais
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Configurações do banco de dados
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configurações do Telegram
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    BOT_TOKEN = os.environ.get('BOT_TOKEN')  # Alias para compatibilidade
    TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME')
    
    # Configurações do Stripe
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Configurações de sessão
    SESSION_PERMANENT = False
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Configurações de upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # Configurações de paginação
    POSTS_PER_PAGE = 20
    USERS_PER_PAGE = 50
    
    # Configurações de cache
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Configurações de email (se necessário no futuro)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Configurações da aplicação
    APP_NAME = 'TeleVIP'
    APP_VERSION = '1.0.0'
    APP_DESCRIPTION = 'Sistema de Assinaturas para Grupos Telegram'
    
    # URLs base
    BASE_URL = os.environ.get('BASE_URL') or 'http://localhost:5000'
    TELEGRAM_WEBHOOK_URL = f"{BASE_URL}/webhooks/telegram"
    
    # Configurações de segurança
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # Configurações de desenvolvimento
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'on']
    TESTING = False
    
    # Configurações de log
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT', 'False').lower() in ['true', '1', 'on']
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Taxas da plataforma
    PLATFORM_FIXED_FEE = 0.99  # R$ 0,99
    PLATFORM_PERCENTAGE_FEE = 0.0999  # 9,99%
    
    # Configurações de limites
    MIN_WITHDRAWAL_AMOUNT = 10.00  # Valor mínimo para saque
    MAX_GROUPS_PER_CREATOR = 10  # Máximo de grupos por criador
    MAX_PLANS_PER_GROUP = 5  # Máximo de planos por grupo
    
    @staticmethod
    def init_app(app):
        """Inicializar configurações adicionais da aplicação"""
        pass

class DevelopmentConfig(Config):
    """Configurações de desenvolvimento"""
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Log de queries SQL

class ProductionConfig(Config):
    """Configurações de produção"""
    DEBUG = False

    # Cookies seguros em produção (HTTPONLY and SameSite are in base Config)
    SESSION_COOKIE_SECURE = True

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)

        # Verificar SECRET_KEY em produção
        secret = app.config.get('SECRET_KEY')
        if not secret or secret == 'dev-secret-key-change-in-production':
            raise ValueError(
                'SECRET_KEY não configurada para produção. '
                'Defina a variável de ambiente SECRET_KEY com um valor seguro.'
            )

        # Log para stderr
        import logging
        from logging import StreamHandler
        file_handler = StreamHandler()
        file_handler.setLevel(logging.WARNING)
        app.logger.addHandler(file_handler)

class TestingConfig(Config):
    """Configurações de teste"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

# Dicionário de configurações
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

# Função para obter configuração
def get_config():
    """Retornar configuração baseada na variável de ambiente"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])