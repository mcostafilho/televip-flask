#!/usr/bin/env python3
"""
Script principal para executar o bot do TeleVIP
"""
import os
import sys
import io
import logging

# CORREÇÃO DE ENCODING - Adicionar logo no início
# Fix encoding issues on Windows
if sys.platform == 'win32':
    # Configurar UTF-8 para stdout e stderr
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    # Definir variável de ambiente
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from pathlib import Path
from dotenv import load_dotenv

# Configurar logging antes de qualquer import
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Função principal para executar o bot"""
    # Carregar variáveis de ambiente
    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path)
    
    # Verificar se as variáveis essenciais estão configuradas
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    database_url = os.getenv('DATABASE_URL') or 'sqlite:///instance/televip.db'
    
    if not bot_token:
        logger.error("BOT_TOKEN não configurado! Configure no arquivo .env")
        sys.exit(1)
    
    # Log do banco sendo usado
    logger.info(f"Bot usando banco de dados: {database_url}")
    
    # Importar e executar o bot
    try:
        from bot.main import main as bot_main
        logger.info("🤖 Iniciando TeleVIP Bot...")
        bot_main()
    except KeyboardInterrupt:
        logger.info("Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao executar bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    # Configurar diretório de trabalho
    os.chdir(Path(__file__).parent)
    
    # Adicionar diretório ao path
    sys.path.insert(0, str(Path(__file__).parent))
    
    # Executar bot
    main()