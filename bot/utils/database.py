"""
Utilitários para conexão com banco de dados
"""
import os
import sys
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Adicionar o diretório raiz ao path para importar os models
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

# Configurar engine - usar o mesmo banco do Flask
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///instance/televip.db')

# Se for SQLite relativo, ajustar o caminho
if DATABASE_URL.startswith('sqlite:///') and not DATABASE_URL.startswith('sqlite:////'):
    # Pegar o caminho do banco
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    # Se não for caminho absoluto, tornar relativo ao diretório raiz
    if not os.path.isabs(db_path):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_path = os.path.join(root_dir, db_path)
        DATABASE_URL = f'sqlite:///{full_path}'

print(f"Bot usando banco de dados: {DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session() -> Session:
    """Context manager para sessão do banco de dados"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def init_db():
    """Inicializar banco de dados"""
    from app.models import Creator, Group, PricingPlan, Subscription, Transaction, Withdrawal
    from app import db
    
    # Criar todas as tabelas
    db.metadata.create_all(bind=engine)
    print("✅ Banco de dados inicializado")

def get_user_subscription(telegram_user_id: str, group_id: int) -> 'Subscription':
    """Buscar assinatura de um usuário em um grupo"""
    from app.models import Subscription
    
    with get_db_session() as session:
        return session.query(Subscription).filter_by(
            telegram_user_id=telegram_user_id,
            group_id=group_id,
            status='active'
        ).first()

def get_creator_by_telegram_id(telegram_id: str) -> 'Creator':
    """Buscar criador pelo ID do Telegram"""
    from app.models import Creator
    
    with get_db_session() as session:
        return session.query(Creator).filter_by(
            telegram_id=telegram_id
        ).first()

def get_group_by_telegram_id(telegram_id: str) -> 'Group':
    """Buscar grupo pelo ID do Telegram"""
    from app.models import Group
    
    with get_db_session() as session:
        return session.query(Group).filter_by(
            telegram_id=telegram_id
        ).first()

def get_active_subscriptions_count(group_id: int) -> int:
    """Contar assinaturas ativas de um grupo"""
    from app.models import Subscription
    
    with get_db_session() as session:
        return session.query(Subscription).filter_by(
            group_id=group_id,
            status='active'
        ).count()

def get_revenue_stats(creator_id: int) -> dict:
    """Obter estatísticas de receita de um criador"""
    from app.models import Group, Transaction, Subscription
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    with get_db_session() as session:
        # Receita total
        total_revenue = session.query(
            func.sum(Transaction.net_amount)
        ).join(Subscription).join(Group).filter(
            Group.creator_id == creator_id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Receita do mês
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        monthly_revenue = session.query(
            func.sum(Transaction.net_amount)
        ).join(Subscription).join(Group).filter(
            Group.creator_id == creator_id,
            Transaction.status == 'completed',
            Transaction.created_at >= month_start
        ).scalar() or 0
        
        # Receita da semana
        week_start = datetime.now() - timedelta(days=7)
        weekly_revenue = session.query(
            func.sum(Transaction.net_amount)
        ).join(Subscription).join(Group).filter(
            Group.creator_id == creator_id,
            Transaction.status == 'completed',
            Transaction.created_at >= week_start
        ).scalar() or 0
        
        return {
            'total': total_revenue,
            'monthly': monthly_revenue,
            'weekly': weekly_revenue
        }