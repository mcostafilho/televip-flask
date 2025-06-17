"""
Tarefas agendadas do bot - Versão alternativa sem JobQueue
"""
import logging
import asyncio
from datetime import datetime, timedelta
from telegram.ext import Application

from bot.utils.database import get_db_session
from app.models import Subscription, Group

logger = logging.getLogger(__name__)

# Variável global para controlar as tarefas
scheduled_tasks = []
running = False

def setup_jobs(application: Application):
    """Configurar jobs agendados usando asyncio em vez de JobQueue"""
    global running
    
    logger.info("📅 Configurando sistema de tarefas agendadas...")
    
    # Como o JobQueue está desabilitado, vamos usar asyncio tasks
    running = True
    
    # Criar tarefas assíncronas
    task1 = asyncio.create_task(check_expired_loop())
    task2 = asyncio.create_task(send_reminders_loop())
    
    scheduled_tasks.extend([task1, task2])
    
    logger.info("✅ Sistema de tarefas agendadas configurado (usando asyncio)")

async def check_expired_loop():
    """Loop para verificar assinaturas expiradas a cada hora"""
    global running
    
    while running:
        try:
            logger.info("🔍 Executando verificação de assinaturas expiradas...")
            await check_expired_subscriptions()
            
            # Aguardar 1 hora
            await asyncio.sleep(3600)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no check_expired_loop: {e}")
            await asyncio.sleep(60)  # Tentar novamente em 1 minuto

async def send_reminders_loop():
    """Loop para enviar lembretes diariamente às 10h"""
    global running
    
    while running:
        try:
            # Calcular tempo até próximas 10h
            now = datetime.now()
            next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"⏰ Próximo envio de lembretes em {wait_seconds/3600:.1f} horas")
            
            await asyncio.sleep(wait_seconds)
            
            logger.info("📨 Executando envio de lembretes...")
            await send_renewal_reminders()
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no send_reminders_loop: {e}")
            await asyncio.sleep(3600)  # Tentar novamente em 1 hora

async def check_expired_subscriptions():
    """Verificar e processar assinaturas expiradas"""
    try:
        with get_db_session() as session:
            # Buscar assinaturas expiradas
            expired = session.query(Subscription).filter(
                Subscription.status == 'active',
                Subscription.end_date < datetime.utcnow()
            ).all()
            
            if expired:
                logger.info(f"📊 Encontradas {len(expired)} assinaturas expiradas")
                
                for sub in expired:
                    # Marcar como expirada
                    sub.status = 'expired'
                    logger.info(f"❌ Assinatura {sub.id} do usuário {sub.telegram_user_id} expirada")
                    
                    # TODO: Implementar remoção do grupo e notificação
                    # await remove_from_group(sub)
                    # await notify_expiration(sub)
                
                session.commit()
                logger.info(f"✅ {len(expired)} assinaturas processadas")
            else:
                logger.info("✅ Nenhuma assinatura expirada encontrada")
                
    except Exception as e:
        logger.error(f"Erro ao verificar assinaturas expiradas: {e}")

async def send_renewal_reminders():
    """Enviar lembretes de renovação"""
    try:
        with get_db_session() as session:
            # Buscar assinaturas que expiram em 7, 3 ou 1 dia
            reminders_sent = 0
            
            for days in [7, 3, 1]:
                target_date = datetime.utcnow() + timedelta(days=days)
                
                # Buscar assinaturas que expiram na data alvo
                subs = session.query(Subscription).filter(
                    Subscription.status == 'active',
                    Subscription.end_date >= target_date.replace(hour=0, minute=0, second=0),
                    Subscription.end_date < target_date.replace(hour=23, minute=59, second=59)
                ).all()
                
                if subs:
                    logger.info(f"📅 {len(subs)} assinaturas expiram em {days} dia(s)")
                    
                    for sub in subs:
                        # TODO: Implementar envio de notificação
                        # await send_renewal_notification(sub, days)
                        reminders_sent += 1
            
            logger.info(f"✅ {reminders_sent} lembretes enviados")
            
    except Exception as e:
        logger.error(f"Erro ao enviar lembretes: {e}")

def stop_jobs():
    """Parar todas as tarefas agendadas"""
    global running, scheduled_tasks
    
    logger.info("🛑 Parando tarefas agendadas...")
    running = False
    
    # Cancelar todas as tarefas
    for task in scheduled_tasks:
        task.cancel()
    
    scheduled_tasks.clear()
    logger.info("✅ Tarefas agendadas paradas")

# Funções auxiliares que serão implementadas quando o bot estiver completo

async def remove_from_group(subscription):
    """Remover usuário do grupo"""
    # TODO: Implementar quando o bot tiver acesso aos grupos
    pass

async def notify_expiration(subscription):
    """Notificar usuário sobre expiração"""
    # TODO: Implementar quando o sistema de notificações estiver pronto
    pass

async def send_renewal_notification(subscription, days_left):
    """Enviar notificação de renovação"""
    # TODO: Implementar quando o sistema de notificações estiver pronto
    pass