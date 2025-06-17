# bot/handlers/payment_verification.py
"""
Sistema de verificação de status de pagamento - VERSÃO CORRIGIDA
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import verify_payment
from app.models import Group, Subscription, Transaction, Creator

logger = logging.getLogger(__name__)

async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verificar status do pagamento - VERSÃO CORRIGIDA"""
    query = update.callback_query
    await query.answer("🔄 Verificando pagamento...")
    
    user = query.from_user
    logger.info(f"Verificando pagamento para usuário {user.id}")
    
    with get_db_session() as session:
        # Buscar transações recentes do usuário (últimas 2 horas)
        recent_transactions = session.query(Transaction).join(
            Subscription
        ).filter(
            Subscription.telegram_user_id == str(user.id),
            Transaction.created_at >= datetime.utcnow() - timedelta(hours=2)
        ).order_by(Transaction.created_at.desc()).all()
        
        logger.info(f"Encontradas {len(recent_transactions)} transações recentes")
        
        # Verificar se alguma transação está completa
        completed_transaction = None
        pending_transaction = None
        
        for transaction in recent_transactions:
            logger.info(f"Transação {transaction.id}: status={transaction.status}")
            if transaction.status == 'completed':
                completed_transaction = transaction
                break
            elif transaction.status == 'pending':
                pending_transaction = transaction
        
        if completed_transaction:
            # Pagamento já confirmado
            logger.info("Pagamento já confirmado, mostrando sucesso")
            await handle_confirmed_payment(query, context, completed_transaction, session)
        elif pending_transaction:
            # Verificar com Stripe se o pagamento foi processado
            logger.info(f"Verificando transação pendente {pending_transaction.id}")
            
            # Tentar múltiplos IDs
            payment_id = (
                pending_transaction.stripe_session_id or 
                pending_transaction.payment_id or 
                pending_transaction.stripe_payment_intent_id
            )
            
            if payment_id:
                logger.info(f"Verificando no Stripe: {payment_id}")
                try:
                    payment_verified = await verify_payment(payment_id)
                    
                    if payment_verified:
                        logger.info("Pagamento verificado no Stripe! Atualizando...")
                        
                        # Atualizar status localmente
                        pending_transaction.status = 'completed'
                        pending_transaction.paid_at = datetime.utcnow()
                        
                        subscription = pending_transaction.subscription
                        subscription.status = 'active'
                        
                        # Atualizar saldo do criador
                        group = subscription.group
                        creator = group.creator
                        creator.available_balance = creator.available_balance or 0
                        creator.available_balance += pending_transaction.net_amount
                        
                        session.commit()
                        logger.info("Status atualizado com sucesso")
                        
                        await handle_confirmed_payment(query, context, pending_transaction, session)
                    else:
                        logger.info("Pagamento ainda não confirmado no Stripe")
                        await show_still_processing(query, context)
                except Exception as e:
                    logger.error(f"Erro ao verificar pagamento: {e}")
                    await show_still_processing(query, context)
            else:
                logger.warning("Nenhum ID de pagamento encontrado")
                await show_still_processing(query, context)
        else:
            # Nenhuma transação encontrada
            logger.info("Nenhuma transação encontrada")
            await show_no_payment_found(query, context)

async def handle_confirmed_payment(query, context, transaction, session):
    """Processar pagamento confirmado"""
    subscription = transaction.subscription
    group = subscription.group
    user = query.from_user
    
    logger.info(f"Processando pagamento confirmado para grupo {group.name}")
    
    # Tentar adicionar ao grupo
    added_to_group = False
    try:
        await context.bot.add_chat_member(
            chat_id=group.telegram_id,
            user_id=user.id
        )
        added_to_group = True
        logger.info(f"Usuário {user.id} adicionado ao grupo {group.telegram_id}")
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário ao grupo: {e}")
    
    # Gerar link se não conseguiu adicionar
    invite_link = None
    if not added_to_group:
        try:
            invite_link_obj = await context.bot.create_chat_invite_link(
                chat_id=group.telegram_id,
                member_limit=1,
                expire_date=datetime.utcnow() + timedelta(hours=24),
                creates_join_request=False
            )
            invite_link = invite_link_obj.invite_link
            
            # Salvar link na assinatura
            subscription.invite_link = invite_link
            session.commit()
            logger.info("Link de convite criado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao criar link de convite: {e}")
    
    # Preparar mensagem baseada no resultado
    if added_to_group:
        text = f"""
✅ **Pagamento Confirmado!**

🎉 Você foi adicionado ao grupo **{group.name}**!

📋 **Detalhes da Assinatura:**
• Plano: {subscription.plan.name}
• Válida até: {subscription.end_date.strftime('%d/%m/%Y')}
• Status: Ativa ✅
• ID: #{subscription.id}

📱 **Como acessar:**
1. Abra o Telegram
2. Vá para seus chats
3. O grupo já deve estar lá!

💡 **Dica:** Fixe o grupo para acesso rápido!
"""
        keyboard = [
            [
                InlineKeyboardButton("📱 Abrir Telegram", url="tg://"),
                InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="check_status")
            ],
            [
                InlineKeyboardButton("🔍 Descobrir Mais Grupos", callback_data="discover")
            ]
        ]
    elif invite_link:
        text = f"""
✅ **Pagamento Confirmado!**

🎉 Sua assinatura para **{group.name}** está ativa!

📋 **Detalhes:**
• Plano: {subscription.plan.name}
• Válida até: {subscription.end_date.strftime('%d/%m/%Y')}
• ID: #{subscription.id}

🔗 **Seu Link de Acesso Exclusivo:**
`{invite_link}`

⚠️ **IMPORTANTE:**
• Este link é válido por 24 horas
• Pode ser usado apenas 1 vez
• Clique no botão abaixo ou copie o link
• Salve o link do grupo após entrar!
"""
        keyboard = [
            [
                InlineKeyboardButton("🚀 Entrar no Grupo Agora", url=invite_link)
            ],
            [
                InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="check_status"),
                InlineKeyboardButton("🔍 Descobrir Mais", callback_data="discover")
            ]
        ]
    else:
        text = f"""
✅ **Pagamento Confirmado!**

Sua assinatura para **{group.name}** está ativa!

⚠️ **Atenção:** Houve um problema ao gerar o link de acesso.

**Por favor, entre em contato:**
• Com o criador: @{group.creator.username or group.creator.name}
• Com nosso suporte: @suporte_televip

**Informações da assinatura:**
• ID: #{subscription.id}
• Válida até: {subscription.end_date.strftime('%d/%m/%Y')}
"""
        keyboard = [
            [
                InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip"),
                InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="check_status")
            ]
        ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_still_processing(query, context):
    """Mostrar que ainda está processando"""
    text = """
⏳ **Pagamento em Processamento**

Seu pagamento ainda está sendo processado pelo sistema.

**Status:** 🔄 Verificando com o processador...

⏱️ **Tempo estimado:** 1-2 minutos

💡 **Dica:** Se você acabou de fazer o pagamento, aguarde alguns segundos e clique em "Verificar Novamente".

Se passar de 5 minutos, entre em contato com o suporte.
"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Verificar Novamente", callback_data="check_payment_status")
        ],
        [
            InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip"),
            InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_no_payment_found(query, context):
    """Mostrar que não encontrou pagamento"""
    text = """
❓ **Nenhum Pagamento Recente Encontrado**

Não encontramos nenhum pagamento seu nas últimas 2 horas.

**Possíveis razões:**
• O pagamento foi cancelado antes de concluir
• Você usou outro usuário do Telegram
• O pagamento ainda não foi registrado

**O que fazer:**
• Se acabou de pagar, aguarde 1 minuto e tente novamente
• Verifique seu extrato bancário/cartão
• Se foi cobrado, entre em contato com suporte

💡 Use /descobrir para ver grupos disponíveis
"""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
            InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
        ],
        [
            InlineKeyboardButton("🔄 Verificar Novamente", callback_data="check_payment_status"),
            InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_stripe_webhook_payment_complete(payment_intent_id: str, bot):
    """Processar webhook do Stripe quando pagamento é confirmado"""
    logger.info(f"Processando webhook para payment_intent: {payment_intent_id}")
    
    with get_db_session() as session:
        # Buscar transação por múltiplos campos
        transaction = (
            session.query(Transaction).filter_by(
                stripe_payment_intent_id=payment_intent_id
            ).first() or
            session.query(Transaction).filter_by(
                payment_id=payment_intent_id
            ).first() or
            session.query(Transaction).filter_by(
                stripe_session_id=payment_intent_id
            ).first()
        )
        
        if not transaction:
            logger.warning(f"Transação não encontrada para payment_intent: {payment_intent_id}")
            return
        
        if transaction.status == 'completed':
            logger.info("Transação já processada")
            return
        
        # Atualizar status
        transaction.status = 'completed'
        transaction.paid_at = datetime.utcnow()
        
        subscription = transaction.subscription
        subscription.status = 'active'
        
        # Atualizar saldo do criador
        group = subscription.group
        creator = group.creator
        creator.available_balance = creator.available_balance or 0
        creator.available_balance += transaction.net_amount
        
        session.commit()
        logger.info("Transação atualizada via webhook")
        
        # Tentar notificar usuário via Telegram
        try:
            user_id = int(subscription.telegram_user_id)
            
            # Tentar adicionar ao grupo
            try:
                await bot.add_chat_member(
                    chat_id=group.telegram_id,
                    user_id=user_id
                )
                
                # Notificar sucesso
                await bot.send_message(
                    chat_id=user_id,
                    text=f"""
✅ **Pagamento Aprovado!**

Você foi adicionado automaticamente ao grupo **{group.name}**!

Abra o Telegram e procure o grupo nos seus chats.

Sua assinatura está ativa até: {subscription.end_date.strftime('%d/%m/%Y')}

Use /start para ver todas suas assinaturas.
""",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                # Criar link e enviar
                try:
                    invite_link_obj = await bot.create_chat_invite_link(
                        chat_id=group.telegram_id,
                        member_limit=1,
                        expire_date=datetime.utcnow() + timedelta(hours=24)
                    )
                    
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"""
✅ **Pagamento Aprovado!**

Sua assinatura para **{group.name}** está ativa!

🔗 Clique para entrar no grupo:
{invite_link_obj.invite_link}

⚠️ Este link expira em 24 horas!

Use /start para ver todas suas assinaturas.
""",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    logger.error(f"Erro ao notificar usuário {user_id}")
                    
        except Exception as e:
            logger.error(f"Erro ao processar notificação: {e}")