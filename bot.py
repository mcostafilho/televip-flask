#!/usr/bin/env python
"""
Script principal para executar o bot
"""
import sys
import os
import logging

# Configurar path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Iniciar o bot"""
    try:
        from bot.main import main as bot_main
        logger.info("🤖 Iniciando TeleVIP Bot...")
        bot_main()
    except ImportError as e:
        logger.error(f"Erro de importação: {e}")
        logger.error("Certifique-se de que todos os arquivos necessários existem")
        
        # Tentar importação alternativa
        try:
            logger.info("Tentando importação alternativa...")
            from bot import create_bot
            from telegram.ext import Application
            import asyncio
            
            # Criar e rodar bot
            app = create_bot()
            app.run_polling()
        except Exception as alt_error:
            logger.error(f"Importação alternativa também falhou: {alt_error}")
            raise
    except KeyboardInterrupt:
        logger.info("👋 Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Criar pasta de logs se não existir
    os.makedirs('logs', exist_ok=True)
    
    # Verificar estrutura
    required_files = [
        'bot/__init__.py',
        'bot/main.py',
        'bot/handlers/__init__.py',
        'bot/handlers/payment.py',
        'bot/utils/__init__.py',
        'bot/utils/format_utils.py'
    ]
    
    missing = []
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
    
    if missing:
        print("❌ Arquivos faltando:")
        for f in missing:
            print(f"   - {f}")
        print("\nCrie estes arquivos antes de continuar!")
        sys.exit(1)
    
    main()