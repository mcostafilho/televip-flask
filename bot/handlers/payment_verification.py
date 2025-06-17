"""
Sistema de verificação de status de pagamento
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
    """Verificar status do pagamento e processar se necessário"""
    query = update.callback_query
    await query.answer("🔄 Verificando pagamento...")
    
    user = query.from_user
    
    with get_db_session() as session:
        # Buscar transações recentes do usuário (últimos 30 minutos)
        recent_transactions = session.query(Transaction).join(
            Subscription
        ).filter(
            Subscription.telegram_user_id == str(user.id),
            Transaction.created_at >= datetime.utcnow() - timedelta(minutes=30)
        ).order_by(Transaction.created_at.desc()).all()
        
        # Verificar se alguma transação está completa
        completed_transaction = None
        pending_transaction = None
        
        for transaction in recent_transactions:
            if transaction.status == 'completed':
                completed_transaction = transaction
                break
            elif transaction.status == 'pending':
                pending_transaction = transaction
        
        if completed_transaction:
            # Pagamento já confirmado
            await handle_confirmed_payment(query, context, completed_transaction, session)
        elif pending_transaction:
            # Verificar com Stripe se o pagamento foi processado
            if pending_transaction.payment_id:
                payment_verified = await verify_payment(pending_transaction.payment_id)
                if payment_verified:
                    # Atualizar status
                    pending_transaction.status = 'completed'
                    pending_transaction.subscription.status = 'active'
                    
                    # Atualizar saldo do criador
                    group = pending_transaction.subscription.group
                    creator = group.creator
                    creator.available_balance += pending_transaction.net_amount
                    
                    session.commit()
                    
                    await handle_confirmed_payment(query, context, pending_transaction, session)
                else:
                    await show_still_processing(query, context)
            else:
                await show_still_processing(query, context)
        else:
            # Nenhuma transação encontrada
            await show_no_payment_found(query, context)

async def handle_confirmed_payment(query, context, transaction, session):
    """Processar pagamento confirmado"""
    subscription = transaction.subscription
    group = subscription.group
    user = query.from_user
    
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
        except Exception as e:
            logger.error(f"Erro ao criar link de convite: {e}")
    
    # Preparar mensagem
    if added_to_group:
        text = f"""
✅ **Pagamento Confirmado!**

🎉 Você foi adicionado ao grupo **{group.name}**!

📋 **Detalhes da Assinatura:**
• Plano: {subscription.plan.name}
• Válida até: {subscription.end_date.strftime('%d/%m/%Y')}
• Status: Ativa ✅

📱 **Como acessar:**
1. Abra o Telegram
2. Vá para seus chats
3. O grupo já deve estar lá!

💡 Dica: Ative as notificações do grupo!
"""
        keyboard = [
            [
                InlineKeyboardButton("📱 Abrir Telegram", url="tg://"),
                InlineKeyboardButton("📊 Ver Assinaturas", callback_data="check_status")
            ],
            [
                InlineKeyboardButton("🔍 Descobrir Mais", callback_data="discover")
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
{invite_link}

⚠️ **IMPORTANTE:**
• Link válido por 24 horas
• Uso único - não compartilhe!
• Salve o link do grupo após entrar

Clique no botão abaixo para entrar:
"""
        keyboard = [
            [
                InlineKeyboardButton("🚀 Entrar no Grupo Agora", url=invite_link)
            ],
            [
                InlineKeyboardButton("📊 Ver Assinaturas", callback_data="check_status"),
                InlineKeyboardButton("🔍 Descobrir Mais", callback_data="discover")
            ]
        ]
    else:
        text = f"""
✅ **Pagamento Confirmado!**

Sua assinatura para **{group.name}** está ativa!

⚠️ Houve um problema ao gerar o link de acesso.

Por favor, entre em contato:
• Com o criador: @{group.creator.username or group.creator.name}
• Com nosso suporte

Sua assinatura está válida até: {subscription.end_date.strftime('%d/%m/%Y')}
"""
        keyboard = [
            [
                InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip"),
                InlineKeyboardButton("📊 Ver Assinaturas", callback_data="check_status")
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

Isso é normal e geralmente leva alguns segundos.

⏱️ **Tempo estimado:** 1-2 minutos

Se passar de 5 minutos, entre em contato com o suporte.
"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Verificar Novamente", callback_data="check_payment_status")
        ],
        [
            InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip"),
            InlineKeyboardButton("📊 Ver Assinaturas", callback_data="check_status")
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

Não encontramos nenhum pagamento seu nos últimos 30 minutos.

**Possíveis razões:**
• O pagamento pode ter sido cancelado
• Houve um erro no processamento
• Você usou outro usuário do Telegram

**O que fazer:**
• Tente realizar o pagamento novamente
• Verifique seu extrato bancário
• Entre em contato com o suporte

Use /descobrir para ver grupos disponíveis.
"""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
            InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
        ],
        [
            InlineKeyboardButton("🔄 Verificar Novamente", callback_data="check_payment_status")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_stripe_webhook_payment_complete(payment_intent_id: str, bot):
    """Processar webhook do Stripe quando pagamento é confirmado"""
    with get_db_session() as session:
        # Buscar transação pelo payment_intent_id
        transaction = session.query(Transaction).filter_by(
            payment_id=payment_intent_id,
            status='pending'
        ).first()
        
        if not transaction:
            logger.warning(f"Transação não encontrada para payment_intent: {payment_intent_id}")
            return
        
        # Atualizar status
        transaction.status = 'completed'
        subscription = transaction.subscription
        subscription.status = 'active'
        
        # Atualizar saldo do criador
        group = subscription.group
        creator = group.creator
        creator.available_balance += transaction.net_amount
        
        session.commit()
        
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
""",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    logger.error(f"Erro ao notificar usuário {user_id}")
                    
        except Exception as e:
            logger.error(f"Erro ao processar webhook: {e}")