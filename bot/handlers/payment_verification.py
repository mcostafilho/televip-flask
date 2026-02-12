"""
Handler para verificação de status de pagamento
VERSÃO CORRIGIDA - Busca transações recentes do usuário
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import verify_payment, get_stripe_session_details
from app.models import Transaction, Subscription, Group, Creator

logger = logging.getLogger(__name__)


async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verificar status do pagamento - VERSÃO CORRIGIDA"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer("🔄 Verificando pagamento...")
    
    logger.info(f"Verificando pagamento para usuário {user.id}")
    
    with get_db_session() as session:
        # Buscar transações recentes do usuário (últimas 24 horas)
        recent_time = datetime.utcnow() - timedelta(hours=24)
        
        transactions = session.query(Transaction).join(
            Subscription
        ).filter(
            Subscription.telegram_user_id == str(user.id),
            Transaction.created_at >= recent_time,
            Transaction.status.in_(['pending', 'processing'])
        ).order_by(
            Transaction.created_at.desc()
        ).all()
        
        logger.info(f"Encontradas {len(transactions)} transações recentes")
        
        if not transactions:
            # Verificar se tem session_id no contexto
            session_id = context.user_data.get('stripe_session_id')
            if session_id:
                logger.info(f"Usando session_id do contexto: {session_id}")
                # Buscar por session_id
                transaction = session.query(Transaction).filter_by(
                    stripe_session_id=session_id
                ).first()
                if transaction:
                    transactions = [transaction]
        
        if not transactions:
            await query.edit_message_text(
                "❌ Nenhum pagamento pendente encontrado.\n\nSe você acabou de fazer um pagamento, aguarde alguns segundos e tente novamente.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                ]])
            )
            return
        
        # Verificar cada transação pendente
        payment_confirmed = False
        confirmed_transaction = None
        
        for transaction in transactions:
            logger.info(f"Transação {transaction.id}: status={transaction.status}")
            
            # Verificar se tem stripe_session_id
            if transaction.stripe_session_id:
                logger.info(f"Verificando session_id: {transaction.stripe_session_id}")
                is_paid = await verify_payment(transaction.stripe_session_id)
                
                if is_paid:
                    payment_confirmed = True
                    confirmed_transaction = transaction
                    break
            elif transaction.stripe_payment_intent_id:
                logger.info(f"Verificando payment_intent: {transaction.stripe_payment_intent_id}")
                is_paid = await verify_payment(transaction.stripe_payment_intent_id)
                
                if is_paid:
                    payment_confirmed = True
                    confirmed_transaction = transaction
                    break
            else:
                logger.warning(f"Transação {transaction.id} sem ID de pagamento")
        
        if payment_confirmed and confirmed_transaction:
            await handle_payment_confirmed(query, context, confirmed_transaction, session)
        else:
            await handle_payment_pending(query, context)


async def handle_payment_confirmed(query, context, transaction, db_session):
    """Processar pagamento confirmado - COM CRIAÇÃO AUTOMÁTICA DE LINK"""
    logger.info(f"Pagamento confirmado para transação {transaction.id}")
    
    # Ativar assinatura
    subscription = transaction.subscription

    # Buscar detalhes da sessão Stripe (subscription_id, payment_intent, etc.)
    if transaction.stripe_session_id:
        try:
            details = await get_stripe_session_details(transaction.stripe_session_id)
            if details.get('subscription_id') and not subscription.stripe_subscription_id:
                subscription.stripe_subscription_id = details['subscription_id']
                logger.info(f"stripe_subscription_id={details['subscription_id']} salvo na assinatura {subscription.id}")
            if details.get('payment_intent_id') and not transaction.stripe_payment_intent_id:
                transaction.stripe_payment_intent_id = details['payment_intent_id']
            if details.get('payment_method_type'):
                subscription.payment_method_type = details['payment_method_type']
        except Exception as e:
            logger.warning(f"Não foi possível buscar detalhes da sessão Stripe: {e}")

    # Determine if this is a Stripe-managed subscription (webhook handles credit)
    is_stripe_managed = subscription.stripe_subscription_id and not subscription.is_legacy

    # Atualizar transação e crédito do criador
    if is_stripe_managed:
        # Stripe subscription: let invoice.paid webhook handle transaction + credit
        # Bot only activates subscription and shows invite link to user
        subscription.status = 'active'
        logger.info(f"Subscription {subscription.id} ativada pelo bot (crédito via webhook invoice.paid)")
    else:
        # Legacy one-time payment: bot handles everything
        transaction.status = 'completed'
        transaction.paid_at = datetime.utcnow()
        subscription.status = 'active'

        group = subscription.group
        if group and group.creator:
            creator = group.creator
            net = transaction.net_amount or transaction.amount or 0
            if creator.balance is None:
                creator.balance = 0
            creator.balance += net
            if creator.total_earned is None:
                creator.total_earned = 0
            creator.total_earned += net
            logger.info(f"Saldo do criador {creator.id} atualizado: +R${net} = R${creator.balance}")

    db_session.commit()
    
    # Obter informações do grupo
    group = subscription.group
    user = query.from_user
    
    # Tentar adicionar usuário ao grupo diretamente (se bot for admin)
    user_added = False
    invite_link = None
    
    try:
        # Primeiro tentar adicionar o usuário diretamente
        if group.telegram_id:
            try:
                # Adicionar usuário ao grupo
                await context.bot.add_chat_member(
                    chat_id=group.telegram_id,
                    user_id=user.id
                )
                user_added = True
                logger.info(f"Usuário {user.id} adicionado diretamente ao grupo {group.telegram_id}")
            except Exception as e:
                logger.info(f"Não foi possível adicionar diretamente: {e}")
                # Continuar para tentar criar link
    except Exception as e:
        logger.error(f"Erro ao tentar adicionar usuário: {e}")
    
    # Se não conseguiu adicionar diretamente, criar link de convite
    if not user_added and group.telegram_id:
        try:
            # Criar link de convite único
            invite_link_obj = await context.bot.create_chat_invite_link(
                chat_id=group.telegram_id,
                member_limit=1,  # Limite de 1 uso
                expire_date=datetime.utcnow() + timedelta(days=7),  # Expira em 7 dias
                creates_join_request=False  # Entrada direta
            )
            invite_link = invite_link_obj.invite_link
            logger.info(f"Link de convite criado: {invite_link}")
            
            # Salvar link na subscription para referência
            subscription.invite_link_used = invite_link
            db_session.commit()
            
        except Exception as e:
            logger.error(f"Erro ao criar link de convite: {e}")
            # Usar link fixo se existir
            if group.invite_link:
                invite_link = group.invite_link
            elif group.telegram_username:
                invite_link = f"https://t.me/{group.telegram_username}"
    
    # Preparar mensagem baseada no resultado
    if user_added:
        text = f"""
✅ **PAGAMENTO CONFIRMADO!**

🎉 Você foi adicionado automaticamente ao grupo **{group.name}**!

📱 **Como acessar:**
1. Abra o Telegram
2. Vá para seus chats
3. O grupo **{group.name}** já está lá!

📅 Sua assinatura está ativa até: {subscription.end_date.strftime('%d/%m/%Y')}

💡 **Dica:** Fixe o grupo para não perder!
"""
        keyboard = [[
            InlineKeyboardButton("📱 Abrir Telegram", url="tg://resolve"),
            InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="my_subscriptions")
        ]]
    
    elif invite_link:
        text = f"""
✅ **PAGAMENTO CONFIRMADO!**

Bem-vindo ao grupo **{group.name}**!

🔗 **Seu link de acesso exclusivo:**
`{invite_link}`

📱 **Como entrar:**
1. Clique no botão abaixo ou
2. Copie o link acima (toque nele)
3. Cole no Telegram

📅 Assinatura ativa até: {subscription.end_date.strftime('%d/%m/%Y')}

⚠️ **IMPORTANTE:** 
- Este link é pessoal e pode ser usado apenas 1 vez
- Válido por 7 dias
- Após entrar, salve o grupo!
"""
        keyboard = [[
            InlineKeyboardButton("🚀 ENTRAR NO GRUPO AGORA", url=invite_link)
        ], [
            InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="my_subscriptions")
        ]]
    
    else:
        # Fallback - nenhum método funcionou
        text = f"""
✅ **PAGAMENTO CONFIRMADO!**

Sua assinatura para **{group.name}** está ativa!

⚠️ **Atenção:** Não foi possível gerar o link automaticamente.

📨 **O que fazer:**
1. Entre em contato com o suporte
2. Informe o ID da sua assinatura: #{subscription.id}
3. Ou aguarde o administrador enviar o link

📅 Assinatura válida até: {subscription.end_date.strftime('%d/%m/%Y')}

💬 Suporte: @suporte_televip
"""
        keyboard = [[
            InlineKeyboardButton("💬 Contactar Suporte", url="https://t.me/suporte_televip")
        ], [
            InlineKeyboardButton("📊 Minhas Assinaturas", callback_data="my_subscriptions")
        ]]
    
    # Enviar mensagem
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Limpar dados da sessão
    context.user_data.pop('stripe_session_id', None)
    context.user_data.pop('checkout', None)
    
    # Log final
    if user_added:
        logger.info(f"✅ Usuário {user.id} adicionado ao grupo com sucesso!")
    elif invite_link:
        logger.info(f"✅ Link de convite enviado para usuário {user.id}")
    else:
        logger.warning(f"⚠️ Não foi possível enviar acesso para usuário {user.id}")

async def handle_payment_pending(query, context):
    """Processar pagamento pendente"""
    text = """
⏳ **Pagamento ainda não confirmado**

Seu pagamento está sendo processado. Isso pode levar alguns minutos.

**O que fazer:**
1. Se você completou o pagamento, aguarde 1-2 minutos
2. Clique em "Verificar Novamente"
3. Se o problema persistir, entre em contato com o suporte

💡 **Dica:** Verifique seu email para a confirmação do Stripe.
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Verificar Novamente", callback_data="check_payment_status"),
            InlineKeyboardButton("❌ Cancelar", callback_data="back_to_start")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Função para ser chamada pelo start quando retornar do pagamento
async def check_payment_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verificar pagamento quando usuário retorna com /start payment_success"""
    user = update.effective_user
    
    logger.info(f"Verificando pagamento após retorno do usuário {user.id}")
    
    # Criar um objeto fake de callback query para reusar a lógica
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.message = message
            
        async def answer(self, text=""):
            pass
            
        async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
            await self.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    
    fake_query = FakeQuery(user, update.message)
    await check_payment_status(Update(update_id=update.update_id, callback_query=fake_query), context)
