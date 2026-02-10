"""
Utilitários para conexão com banco de dados
"""
import os
import sys
from contextlib import contextmanager
from sqlalchemy import create_engine, text, text, text
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

# DB URL logged at debug level only (not printed to stdout to avoid credential exposure)
import logging as _logging
_logging.getLogger(__name__).debug("Bot database engine configured")

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

# Função helper para executar queries SQL raw
def execute_sql(session, query_string):
    """Executar query SQL raw usando text()"""
    return session.execute(text(query_string))

# Função para testar conexão
def test_connection():
    """Testar conexão com o banco de dados"""
    try:
        with get_db_session() as session:
            result = execute_sql(session, "SELECT 1")
            return True
    except Exception as e:
        print(f"Erro ao conectar com banco: {e}")
        return False