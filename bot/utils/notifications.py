"""
Sistema de notificações automáticas
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from telegram import Bot
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Subscription, Group

logger = logging.getLogger(__name__)

class NotificationScheduler:
    """Scheduler para notificações automáticas"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.tasks = []
        
    async def start(self):
        """Iniciar scheduler"""
        self.running = True
        
        # Criar tasks
        self.tasks = [
            asyncio.create_task(self.check_expiring_subscriptions()),
            asyncio.create_task(self.remove_expired_members()),
            asyncio.create_task(self.send_daily_stats())
        ]
        
        logger.info("📅 Scheduler de notificações iniciado")
        
    async def stop(self):
        """Parar scheduler"""
        self.running = False
        
        # Cancelar todas as tasks
        for task in self.tasks:
            task.cancel()
        
        # Aguardar cancelamento
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("📅 Scheduler de notificações parado")
    
    async def check_expiring_subscriptions(self):
        """Verificar assinaturas próximas do vencimento"""
        while self.running:
            try:
                with get_db_session() as session:
                    # Buscar assinaturas que vencem em 3 dias
                    expiry_date = datetime.utcnow() + timedelta(days=3)
                    
                    expiring_subs = session.query(Subscription).filter(
                        Subscription.status == 'active',
                        Subscription.end_date <= expiry_date,
                        Subscription.end_date > datetime.utcnow()
                    ).all()
                    
                    for sub in expiring_subs:
                        await self.send_expiry_notification(sub)
                
                # Verificar a cada hora
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Erro ao verificar assinaturas: {e}")
                await asyncio.sleep(60)
    
    async def send_expiry_notification(self, subscription: Subscription):
        """Enviar notificação de vencimento"""
        try:
            days_left = (subscription.end_date - datetime.utcnow()).days
            group = subscription.group
            
            message = f"""
⏰ *Assinatura Expirando!*

Sua assinatura do grupo *{group.name}* vence em {days_left} dias.

💡 Renove agora para não perder o acesso ao conteúdo exclusivo!

Use /status para renovar sua assinatura.
"""
            
            await self.bot.send_message(
                chat_id=subscription.telegram_user_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Notificação enviada para {subscription.telegram_username}")
            
        except Exception as e:
            logger.error(f"Erro ao enviar notificação: {e}")
    
    async def remove_expired_members(self):
        """Remover membros com assinatura expirada"""
        while self.running:
            try:
                with get_db_session() as session:
                    # Buscar assinaturas expiradas há mais de 1 dia
                    expired_date = datetime.utcnow() - timedelta(days=1)
                    
                    expired_subs = session.query(Subscription).filter(
                        Subscription.status == 'active',
                        Subscription.end_date < expired_date
                    ).all()
                    
                    for sub in expired_subs:
                        await self.process_expired_subscription(sub, session)
                    
                    session.commit()
                
                # Verificar a cada 6 horas
                await asyncio.sleep(21600)
                
            except Exception as e:
                logger.error(f"Erro ao remover membros expirados: {e}")
                await asyncio.sleep(300)
    
    async def process_expired_subscription(self, subscription: Subscription, session):
        """Processar assinatura expirada"""
        try:
            group = subscription.group
            
            # Tentar remover do grupo do Telegram
            try:
                await self.bot.ban_chat_member(
                    chat_id=group.telegram_id,
                    user_id=int(subscription.telegram_user_id)
                )
                
                # Desbanir imediatamente (apenas remove, não bane)
                await self.bot.unban_chat_member(
                    chat_id=group.telegram_id,
                    user_id=int(subscription.telegram_user_id)
                )
            except Exception as e:
                logger.warning(f"Não foi possível remover usuário do grupo: {e}")
            
            # Atualizar status da assinatura
            subscription.status = 'expired'
            
            # Notificar usuário
            message = f"""
❌ *Assinatura Expirada*

Sua assinatura do grupo *{group.name}* expirou e você foi removido do grupo.

Para voltar a ter acesso, renove sua assinatura usando /start
"""
            
            await self.bot.send_message(
                chat_id=subscription.telegram_user_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Atualizar contador de assinantes
            group.total_subscribers = max(0, group.total_subscribers - 1)
            
            logger.info(f"Assinatura expirada processada: {subscription.telegram_username}")
            
        except Exception as e:
            logger.error(f"Erro ao processar assinatura expirada: {e}")
    
    async def send_daily_stats(self):
        """Enviar estatísticas diárias para criadores"""
        while self.running:
            try:
                # Aguardar até 9h da manhã
                now = datetime.now()
                next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
                
                if now.hour >= 9:
                    next_run += timedelta(days=1)
                
                wait_seconds = (next_run - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # Enviar estatísticas
                with get_db_session() as session:
                    groups = session.query(Group).filter_by(is_active=True).all()
                    
                    for group in groups:
                        await self.send_group_stats(group)
                
            except Exception as e:
                logger.error(f"Erro ao enviar estatísticas diárias: {e}")
                await asyncio.sleep(3600)
    
    async def send_group_stats(self, group: Group):
        """Enviar estatísticas de um grupo para o criador"""
        try:
            # Calcular estatísticas
            with get_db_session() as session:
                # Assinantes ativos
                active_subs = session.query(Subscription).filter_by(
                    group_id=group.id,
                    status='active'
                ).count()
                
                # Novos assinantes hoje
                today_start = datetime.now().replace(hour=0, minute=0, second=0)
                new_subs_today = session.query(Subscription).filter(
                    Subscription.group_id == group.id,
                    Subscription.created_at >= today_start
                ).count()
                
                # Vencimentos próximos (7 dias)
                expiry_date = datetime.utcnow() + timedelta(days=7)
                expiring_soon = session.query(Subscription).filter(
                    Subscription.group_id == group.id,
                    Subscription.status == 'active',
                    Subscription.end_date <= expiry_date
                ).count()
            
            message = f"""
📊 *Relatório Diário - {group.name}*

👥 Assinantes ativos: {active_subs}
📈 Novos hoje: {new_subs_today}
⏰ Vencendo em 7 dias: {expiring_soon}

Use /stats para ver relatório completo.
"""
            
            # Enviar para o criador (precisa implementar campo telegram_id no Creator)
            # await self.bot.send_message(
            #     chat_id=group.creator.telegram_id,
            #     text=message,
            #     parse_mode=ParseMode.MARKDOWN
            # )
            
        except Exception as e:
            logger.error(f"Erro ao enviar estatísticas do grupo: {e}")