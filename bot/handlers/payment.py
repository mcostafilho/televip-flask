"""
Handler de pagamento do bot - Sistema completo de processamento de pagamentos
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import (
    create_checkout_session, verify_payment,
    get_or_create_stripe_customer, get_or_create_stripe_price,
    create_subscription_checkout
)
from bot.utils.format_utils import format_currency
from app.models import Group, PricingPlan, Subscription, Transaction, Creator

logger = logging.getLogger(__name__)


async def start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Iniciar processo de pagamento após seleção do plano"""
    query = update.callback_query
    await query.answer()
    
    # Extrair dados do callback
    # Formato: plan_GROUPID_PLANID
    try:
        _, group_id, plan_id = query.data.split('_')
        group_id = int(group_id)
        plan_id = int(plan_id)
    except Exception:
        await query.edit_message_text(
            "❌ Erro ao processar seleção. Tente novamente.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
            ]])
        )
        return
    
    # Buscar informações do grupo e plano
    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        plan = session.query(PricingPlan).get(plan_id)
        
        if not group or not plan:
            await query.edit_message_text(
                "❌ Grupo ou plano não encontrado.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                ]])
            )
            return
        
        # Calcular valores
        amount = float(plan.price)
        platform_fee = amount * 0.10  # 10% de taxa
        creator_amount = amount - platform_fee
        
        # Preparar dados do checkout
        checkout_data = {
            'group_id': group_id,
            'plan_id': plan_id,
            'amount': amount,
            'platform_fee': platform_fee,
            'creator_amount': creator_amount,
            'duration_days': plan.duration_days,
            'group_name': group.name,
            'plan_name': plan.name
        }
        
        # Salvar no contexto
        context.user_data['checkout'] = checkout_data
        
        # Mostrar resumo do pedido
        text = f"""
💳 **RESUMO DO PEDIDO**

📱 **Grupo:** {group.name}
📅 **Plano:** {plan.name}
⏱ **Duração:** {plan.duration_days} dias
🔄 **Renovacao:** Automatica (cartao) ou novo boleto a cada ciclo

💰 **Valor:** {format_currency(amount)}

Clique abaixo para pagar com cartao ou boleto:
"""

        keyboard = [
            [InlineKeyboardButton("💳 Pagar Agora", callback_data="pay_stripe")],
            [InlineKeyboardButton("❌ Cancelar", callback_data=f"group_{group_id}")]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar seleção do método de pagamento"""
    query = update.callback_query
    await query.answer()
    
    # Verificar se temos os dados do checkout
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text(
            "❌ Sessão expirada. Por favor, inicie novamente.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
            ]])
        )
        return
    
    if query.data == "pay_stripe":
        await process_stripe_payment(query, context, checkout_data)


async def process_stripe_payment(query, context, checkout_data):
    """Processar pagamento via Stripe - Modo assinatura recorrente"""
    user = query.from_user

    # URLs de retorno
    bot_username = context.bot.username
    success_url = f"https://t.me/{bot_username}?start=payment_success"
    cancel_url = f"https://t.me/{bot_username}?start=payment_cancel"

    try:
        # 1. Get or create Stripe Customer
        customer_id = get_or_create_stripe_customer(
            telegram_user_id=str(user.id),
            username=user.username
        )

        # 2. Get or create Stripe Price for the plan
        with get_db_session() as session:
            plan = session.query(PricingPlan).get(checkout_data['plan_id'])
            group = session.query(Group).get(checkout_data['group_id'])

            if not plan or not group:
                await query.edit_message_text(
                    "❌ Plano ou grupo nao encontrado.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                    ]])
                )
                return

            price_id = get_or_create_stripe_price(plan, group)

        # 3. Create subscription checkout session
        metadata = {
            'user_id': str(user.id),
            'username': user.username or '',
            'group_id': str(checkout_data['group_id']),
            'plan_id': str(checkout_data['plan_id']),
            'group_name': checkout_data['group_name'],
            'plan_name': checkout_data['plan_name']
        }

        result = await create_subscription_checkout(
            customer_id=customer_id,
            price_id=price_id,
            metadata=metadata,
            success_url=success_url,
            cancel_url=cancel_url
        )

        if result['success']:
            # Salvar dados do checkout
            context.user_data['stripe_session_id'] = result['session_id']

            with get_db_session() as session:
                # Criar subscription como pending (ativação via webhook invoice.paid)
                new_subscription = Subscription(
                    group_id=checkout_data['group_id'],
                    plan_id=checkout_data['plan_id'],
                    telegram_user_id=str(user.id),
                    telegram_username=user.username,
                    stripe_customer_id=customer_id,
                    status='pending',
                    auto_renew=True,
                    is_legacy=False,
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=checkout_data['duration_days'])
                )
                session.add(new_subscription)
                session.flush()

                # Criar transaction pending (completada via webhook)
                transaction = Transaction(
                    subscription_id=new_subscription.id,
                    amount=checkout_data['amount'],
                    fee=checkout_data['platform_fee'],
                    net_amount=checkout_data['creator_amount'],
                    payment_method='stripe',
                    stripe_session_id=result['session_id'],
                    billing_reason='subscription_create',
                    status='pending'
                )
                session.add(transaction)
                session.commit()

                logger.info(f"Criada subscription {new_subscription.id} (recurring) com session_id: {result['session_id']}")

            # Mostrar instruções e botão de pagamento
            text = """
🔐 **Pagamento Seguro via Stripe**

Clique no botao abaixo para ser redirecionado para a pagina de pagamento segura.

💳 **Aceita:** Cartao e Boleto
🔄 **Renovacao automatica** a cada ciclo

Apos concluir o pagamento:
1. Voce sera redirecionado de volta ao Telegram
2. Clique em "Verificar Pagamento" para confirmar
3. Sera adicionado ao grupo automaticamente

⚠️ **Importante:** Nao feche esta conversa durante o pagamento!
"""

            keyboard = [
                [InlineKeyboardButton("💳 Pagar Agora", url=result['url'])],
                [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data="check_payment_status")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"group_{checkout_data['group_id']}")]
            ]

            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Erro ao criar sessão
            await query.edit_message_text(
                f"❌ Erro ao processar pagamento: {result.get('error', 'Erro desconhecido')}\n\n"
                "Por favor, tente novamente ou entre em contato com o suporte.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Tentar Novamente", callback_data=f"plan_{checkout_data['group_id']}_{checkout_data['plan_id']}"),
                    InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
                ]])
            )
    except Exception as e:
        logger.error(f"Erro ao processar pagamento recorrente: {e}")
        await query.edit_message_text(
            "❌ Erro ao processar pagamento. Tente novamente.\n\n"
            "Se o problema persistir, entre em contato com o suporte.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tentar Novamente", callback_data=f"plan_{checkout_data['group_id']}_{checkout_data['plan_id']}"),
                InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
            ]])
        )


async def handle_payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para quando usuário retorna do pagamento com sucesso"""
    user = update.effective_user
    
    logger.info(f"Usuário {user.id} retornou do pagamento")
    
    # Mensagem de boas-vindas
    text = """
✅ **Obrigado pelo seu pagamento!**

Estamos processando sua transação. Isso pode levar alguns segundos.

Clique no botão abaixo para verificar o status:
"""
    
    keyboard = [[
        InlineKeyboardButton("🔄 Verificar Status", callback_data="check_payment_status"),
        InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
    ]]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_payment_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para quando usuário cancela o pagamento"""
    user = update.effective_user
    
    logger.info(f"Usuário {user.id} cancelou o pagamento")
    
    text = """
❌ **Pagamento Cancelado**

Você cancelou o processo de pagamento. 

Se mudou de ideia, você pode tentar novamente a qualquer momento.
"""
    
    keyboard = [[
        InlineKeyboardButton("🔍 Ver Grupos", callback_data="discover"),
        InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
    ]]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def list_user_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar assinaturas ativas do usuário"""
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
        message = query
    else:
        user = update.effective_user
        message = update
    
    with get_db_session() as session:
        # Buscar assinaturas ativas
        subscriptions = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date > datetime.utcnow()
        ).all()
        
        if not subscriptions:
            text = """
📭 **Você não tem assinaturas ativas**

Explore nossos grupos exclusivos e comece sua jornada!
"""
            keyboard = [[
                InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
                InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
            ]]
        else:
            text = "📱 **SUAS ASSINATURAS ATIVAS**\n\n"
            
            for sub in subscriptions:
                group = sub.group
                days_left = (sub.end_date - datetime.utcnow()).days
                
                text += f"""
📌 **{group.name}**
⏱ Expira em: {days_left} dias ({sub.end_date.strftime('%d/%m/%Y')})
💰 Plano: {sub.plan.name}

"""
            
            keyboard = [
                [InlineKeyboardButton("🔍 Descobrir Mais Grupos", callback_data="discover")],
                [InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")]
            ]
        
        if hasattr(message, 'edit_message_text'):
            await message.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )


# Registrar handlers
def register_payment_handlers(application):
    """Registrar todos os handlers de pagamento"""
    from telegram.ext import CallbackQueryHandler, CommandHandler
    
    # Handlers de callback
    application.add_handler(CallbackQueryHandler(start_payment, pattern=r'^plan_\d+_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_payment_method, pattern='^pay_stripe$'))
    application.add_handler(CallbackQueryHandler(list_user_subscriptions, pattern='^my_subscriptions$'))
    
    # Command handlers
    application.add_handler(CommandHandler('subscriptions', list_user_subscriptions))
    
    logger.info("Handlers de pagamento registrados")

# Funções adicionadas automaticamente

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para seleção de plano"""
    # Alias para start_payment
    await start_payment(update, context)

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callbacks de pagamento"""
    query = update.callback_query
    
    if query.data.startswith('pay_'):
        await handle_payment_method(update, context)
    elif query.data == 'check_payment_status':
        from bot.handlers.payment_verification import check_payment_status
        await check_payment_status(update, context)


# FUNÇÕES ADICIONAIS DE PAGAMENTO

async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verificar status do pagamento"""
    query = update.callback_query
    await query.answer("🔄 Verificando pagamento...")
    
    # Verificar se temos session_id salvo
    session_id = context.user_data.get('stripe_session_id')
    
    if not session_id:
        await query.edit_message_text(
            "❌ Nenhum pagamento pendente encontrado.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
            ]])
        )
        return
    
    # Verificar pagamento
    from bot.utils.stripe_integration import verify_payment
    payment_confirmed = await verify_payment(session_id)
    
    if payment_confirmed:
        # Atualizar no banco
        with get_db_session() as session:
            transaction = session.query(Transaction).filter_by(
                stripe_session_id=session_id
            ).first()
            
            if transaction:
                transaction.status = 'completed'
                transaction.paid_at = datetime.utcnow()
                
                # Ativar assinatura
                subscription = transaction.subscription
                subscription.status = 'active'
                
                session.commit()
                
                # Gerar link de convite unico via Bot API
                group = subscription.group
                invite_link = None

                if group.telegram_id:
                    try:
                        link_obj = await context.bot.create_chat_invite_link(
                            chat_id=int(group.telegram_id),
                            member_limit=1,
                            name=f"sub_{subscription.id}"
                        )
                        invite_link = link_obj.invite_link
                    except Exception as e:
                        logger.error(f"Erro ao gerar invite link: {e}")

                # Fallback para link salvo no banco
                if not invite_link:
                    invite_link = group.invite_link

                if invite_link:
                    text = f"""
✅ **PAGAMENTO CONFIRMADO!**

Bem-vindo ao grupo **{group.name}**!

🔗 **Link de acesso:** {invite_link}

Sua assinatura esta ativa ate {subscription.end_date.strftime('%d/%m/%Y')}.

💡 Salve este link! Ele so pode ser usado uma vez.
"""
                    keyboard = [[InlineKeyboardButton("📱 Entrar no Grupo", url=invite_link)]]
                else:
                    text = f"""
✅ **PAGAMENTO CONFIRMADO!**

Sua assinatura do grupo **{group.name}** esta ativa ate {subscription.end_date.strftime('%d/%m/%Y')}.

⚠️ Nao foi possivel gerar o link automaticamente.
Entre em contato com o criador do grupo para acesso.
"""
                    keyboard = []

                keyboard.append([InlineKeyboardButton("📱 Minhas Assinaturas", callback_data="my_subscriptions")])

                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                # Limpar dados da sessão
                context.user_data.pop('stripe_session_id', None)
                context.user_data.pop('checkout', None)
            else:
                await query.edit_message_text(
                    "❌ Transação não encontrada no sistema.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                    ]])
                )
    else:
        # Pagamento ainda não confirmado
        text = """
⏳ **Pagamento ainda não confirmado**

Por favor, complete o pagamento no Stripe.

Se você já pagou, aguarde alguns segundos e clique em "Verificar Novamente".
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


async def handle_payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para retorno de pagamento bem-sucedido"""
    # Verificar status do pagamento
    await check_payment_status(update, context)


async def handle_payment_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para erro no pagamento"""
    query = update.callback_query
    await query.answer("❌ Erro no pagamento", show_alert=True)
    
    text = """
❌ **Erro no Pagamento**

Houve um problema ao processar seu pagamento.

Possíveis causas:
• Cartão recusado
• Dados inválidos
• Limite excedido

Por favor, tente novamente ou use outro método de pagamento.
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Tentar Novamente", callback_data="retry_payment"),
            InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_payment_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para pagamento cancelado"""
    user = update.effective_user
    
    # Limpar dados da sessão
    context.user_data.pop('checkout', None)
    context.user_data.pop('stripe_session_id', None)
    
    text = """
❌ **Pagamento Cancelado**

Seu pagamento foi cancelado.

Você pode tentar novamente a qualquer momento clicando no link do grupo.
"""
    
    keyboard = [[
        InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover"),
        InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
    ]]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

