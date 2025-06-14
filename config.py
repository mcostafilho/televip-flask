import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Diretório base do projeto
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    
    # Database - Usar caminho absoluto
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or         'sqlite:///' + os.path.join(basedir, 'instance', 'televip.db')
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
