"""
Utilitários de segurança para o bot
"""
import logging
from datetime import datetime
from bot.utils.database import get_db_session
from app.models import Subscription

logger = logging.getLogger(__name__)

async def validate_invite_link(user_id: int, invite_link: str) -> bool:
    """Validar se o usuário tem direito a usar este link de convite"""
    with get_db_session() as session:
        # Buscar assinatura com este link
        subscription = session.query(Subscription).filter_by(
            telegram_user_id=str(user_id),
            invite_link=invite_link,
            status='active'
        ).first()
        
        if subscription:
            # Verificar se ainda está válida
            if subscription.end_date > datetime.utcnow():
                logger.info(f"Link válido para usuário {user_id}")
                return True
            else:
                logger.warning(f"Link expirado para usuário {user_id}")
                return False
        else:
            logger.warning(f"Link inválido ou não pertence ao usuário {user_id}")
            return False

async def verify_subscription_ownership(user_id: int, subscription_id: int) -> bool:
    """Verificar se uma assinatura pertence ao usuário"""
    with get_db_session() as session:
        subscription = session.query(Subscription).filter_by(
            id=subscription_id,
            telegram_user_id=str(user_id)
        ).first()
        
        return subscription is not None

async def check_active_subscription(user_id: int, group_id: int) -> bool:
    """Verificar se o usuário tem assinatura ativa para um grupo"""
    with get_db_session() as session:
        subscription = session.query(Subscription).filter_by(
            telegram_user_id=str(user_id),
            group_id=group_id,
            status='active'
        ).first()
        
        if subscription and subscription.end_date > datetime.utcnow():
            return True
        return False

async def get_user_permissions(user_id: int, group_id: int) -> dict:
    """Obter permissões do usuário em um grupo"""
    with get_db_session() as session:
        subscription = session.query(Subscription).filter_by(
            telegram_user_id=str(user_id),
            group_id=group_id,
            status='active'
        ).first()
        
        if not subscription:
            return {
                'can_access': False,
                'is_active': False,
                'days_left': 0,
                'plan_name': None
            }
        
        days_left = (subscription.end_date - datetime.utcnow()).days
        
        return {
            'can_access': subscription.end_date > datetime.utcnow(),
            'is_active': subscription.status == 'active',
            'days_left': max(0, days_left),
            'plan_name': subscription.plan.name if subscription.plan else None,
            'expires_at': subscription.end_date
        }

async def validate_payment_callback(user_id: int, payment_id: str) -> bool:
    """Validar callback de pagamento"""
    # TODO: Implementar validação com Stripe/provedor de pagamento
    logger.info(f"Validando pagamento {payment_id} para usuário {user_id}")
    return True

async def generate_secure_token(user_id: int, group_id: int) -> str:
    """Gerar token seguro para validação"""
    import hashlib
    import time
    
    # Criar hash único baseado em user_id, group_id e timestamp
    data = f"{user_id}:{group_id}:{int(time.time())}"
    token = hashlib.sha256(data.encode()).hexdigest()[:16]
    
    return token

async def log_security_event(event_type: str, user_id: int, details: dict):
    """Registrar evento de segurança"""
    logger.info(f"SECURITY_EVENT: {event_type} | User: {user_id} | Details: {details}")
    
    # TODO: Implementar salvamento em banco de dados para auditoria
    # SecurityLog.create(
    #     event_type=event_type,
    #     user_id=user_id,
    #     details=details,
    #     timestamp=datetime.utcnow()
    # )