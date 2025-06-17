"""
Sistema de notificações do bot
"""
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Subscription

logger = logging.getLogger(__name__)

class NotificationScheduler:
    """Agendador de notificações"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.tasks = []
    
    async def start(self):
        """Iniciar scheduler"""
        self.running = True
        logger.info("📅 NotificationScheduler iniciado")
        
        # Agendar tarefas
        self.tasks.append(
            asyncio.create_task(self.check_expired_loop())
        )
        self.tasks.append(
            asyncio.create_task(self.send_reminders_loop())
        )
    
    async def stop(self):
        """Parar scheduler"""
        self.running = False
        for task in self.tasks:
            task.cancel()
        logger.info("📅 NotificationScheduler parado")
    
    async def check_expired_loop(self):
        """Loop para verificar assinaturas expiradas"""
        while self.running:
            try:
                await self.check_expired_subscriptions()
                await asyncio.sleep(3600)  # Verificar a cada hora
            except Exception as e:
                logger.error(f"Erro no check_expired_loop: {e}")
                await asyncio.sleep(60)
    
    async def send_reminders_loop(self):
        """Loop para enviar lembretes"""
        while self.running:
            try:
                # Calcular tempo até próximas 10h
                now = datetime.now()
                next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
                if now >= next_run:
                    next_run += timedelta(days=1)
                
                wait_seconds = (next_run - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                await self.send_renewal_reminders()
                
            except Exception as e:
                logger.error(f"Erro no send_reminders_loop: {e}")
                await asyncio.sleep(3600)
    
    async def check_expired_subscriptions(self):
        """Verificar e processar assinaturas expiradas"""
        logger.info("🔍 Verificando assinaturas expiradas...")
        
        with get_db_session() as session:
            # Buscar assinaturas expiradas
            expired = session.query(Subscription).filter(
                Subscription.status == 'active',
                Subscription.end_date < datetime.utcnow()
            ).all()
            
            for sub in expired:
                sub.status = 'expired'
                # TODO: Implementar remoção do grupo
                logger.info(f"Assinatura {sub.id} marcada como expirada")
            
            session.commit()
            logger.info(f"✅ {len(expired)} assinaturas processadas")
    
    async def send_renewal_reminders(self):
        """Enviar lembretes de renovação"""
        logger.info("📨 Enviando lembretes de renovação...")
        
        # TODO: Implementar envio de lembretes
        logger.info("✅ Lembretes enviados")
