"""
Utilitários para conexão com banco de dados
"""
import os
import sys
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Adicionar o diretório raiz ao path para importar os models
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

# Configurar engine - usar o mesmo banco do Flask
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///instance/televip.db')

# Se for SQLite relativo, ajustar o caminho
if DATABASE_URL.startswith('sqlite:///') and not DATABASE_URL.startswith('sqlite:////'):
    db_path = DATABASE_URL.replace('sqlite:///', '')
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
