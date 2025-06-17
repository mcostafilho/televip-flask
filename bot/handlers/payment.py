# bot/handlers/payment.py
"""
Handler para processamento de pagamentos multi-criador
CORREÇÃO: Adicionar stripe_session_id e payment_id na transação
"""
import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import create_checkout_session
from app.models import Group, PricingPlan, Subscription, Transaction, Creator

logger = logging.getLogger(__name__)

# Taxas da plataforma
FIXED_FEE = 0.99  # R$ 0,99 fixo
PERCENTAGE_FEE = 0.0799  # 7,99%

async def handle_payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar retorno de pagamento bem-sucedido"""
    user = update.effective_user
    
    # Verificar se temos os dados do checkout
    checkout_data = context.user_data.get('checkout')
    stripe_session_id = context.user_data.get('stripe_session_id')
    
    if not checkout_data:
        # Tentar recuperar do banco de dados
        await show_payment_success_generic(update, context)
        return
    
    # Criar assinatura no banco
    with get_db_session() as session:
        try:
            # Criar nova assinatura - COMEÇA COMO PENDING
            new_subscription = Subscription(
                group_id=checkout_data['group_id'],
                plan_id=checkout_data['plan_id'],
                telegram_user_id=str(user.id),
                telegram_username=user.username,
                status='pending',  # MUDANÇA: Começa como pending até confirmar pagamento
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=checkout_data['duration_days']),
                auto_renew=False,
                payment_method='stripe'
            )
            session.add(new_subscription)
            session.flush()  # Para obter o ID
            
            # Criar transação com IDs corretos - PARTE CRÍTICA
            transaction = Transaction(
                subscription_id=new_subscription.id,
                group_id=checkout_data['group_id'],
                amount=checkout_data['amount'],
                fee_amount=checkout_data['platform_fee'],
                net_amount=checkout_data['creator_amount'],
                payment_method='stripe',
                payment_id=stripe_session_id,  # ADICIONAR: Campo para busca
                stripe_session_id=stripe_session_id,  # ADICIONAR: Session ID do Stripe
                status='pending'  # MUDANÇA: Começa como pending
            )
            session.add(transaction)
            session.commit()
            
            logger.info(f"Transação criada: ID={transaction.id}, Session={stripe_session_id}")
            
            # Mostrar mensagem de processamento
            text = """
⏳ **Processando seu pagamento...**

Detectamos o seu pagamento, mas houve um pequeno atraso no processamento.

Isso é normal e geralmente leva alguns segundos.

**O que está acontecendo:**
• Confirmando pagamento com o processador
• Ativando sua assinatura
• Preparando seu acesso ao grupo

Clique no botão abaixo para verificar o status:
"""
            
            keyboard = [
                [InlineKeyboardButton("🔄 Verificar Status", callback_data="check_payment_status")],
                [
                    InlineKeyboardButton("❓ Ajuda", callback_data="help"),
                    InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                ]
            ]
            
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Erro ao processar pagamento: {e}")
            await show_payment_error(update, context)

async def show_payment_success_generic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar mensagem genérica de sucesso quando não temos contexto"""
    text = """
✅ **Pagamento Detectado!**

Estamos processando seu pagamento. 

Se você acabou de fazer um pagamento, clique em "Verificar Status" abaixo.

Se não, use /start para ver suas assinaturas ativas.
"""
    
    keyboard = [
        [InlineKeyboardButton("🔄 Verificar Status", callback_data="check_payment_status")],
        [
            InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start"),
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
        ]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_payment_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar erro de pagamento"""
    text = """
❌ **Erro no Processamento**

Houve um erro ao processar seu pagamento.

**O que fazer:**
• Verifique se o pagamento foi debitado
• Tente novamente em alguns minutos
• Entre em contato com o suporte se persistir

Nenhuma cobrança foi realizada se você não concluiu o pagamento.
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Tentar Novamente", callback_data="retry_payment"),
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
        ],
        [
            InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
        ]
    ]
    
    message = update.message if update.message else update.callback_query.message
    
    await message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Manter o resto das funções existentes do arquivo...
async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar seleção de plano"""
    query = update.callback_query
    await query.answer()
    
    # Extrair IDs do callback data: plan_GROUP-ID_PLAN-ID
    try:
        _, group_id, plan_id = query.data.split('_')
        group_id = int(group_id)
        plan_id = int(plan_id)
    except:
        await query.edit_message_text("❌ Erro ao processar seleção.")
        return
    
    user = query.from_user
    
    with get_db_session() as session:
        plan = session.query(PricingPlan).get(plan_id)
        group = session.query(Group).get(group_id)
        
        if not plan or not group:
            await query.edit_message_text("❌ Plano ou grupo não encontrado.")
            return
        
        creator = group.creator
        
        # Verificar novamente se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group_id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if existing_sub:
            days_left = (existing_sub.end_date - datetime.utcnow()).days
            
            text = f"""
✅ **Você já possui uma assinatura ativa!**

**Grupo:** {group.name}
**Plano:** {existing_sub.plan.name}
**Dias restantes:** {days_left}
**Expira em:** {existing_sub.end_date.strftime('%d/%m/%Y')}

Use /status para ver todas suas assinaturas.
"""
            keyboard = [
                [
                    InlineKeyboardButton("📊 Ver Status", callback_data="check_status"),
                    InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                ]
            ]
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Calcular valores com taxas
        gross_amount = float(plan.price)
        fixed_fee = FIXED_FEE
        percentage_fee = gross_amount * PERCENTAGE_FEE
        total_fee = fixed_fee + percentage_fee
        creator_amount = gross_amount - total_fee
        
        # Salvar dados do checkout no contexto
        context.user_data['checkout'] = {
            'group_id': group_id,
            'plan_id': plan_id,
            'creator_id': creator.id,
            'amount': gross_amount,
            'platform_fee': total_fee,
            'creator_amount': creator_amount,
            'duration_days': plan.duration_days
        }
        
        # Mostrar resumo do pedido
        text = f"""
📋 **Resumo do Pedido**

**Grupo:** {group.name}
**Criador:** {creator.name}
**Plano:** {plan.name}
**Duração:** {plan.duration_days} dias

💰 **Valores:**
• Valor: R$ {gross_amount:.2f}
• Taxa da plataforma: R$ {total_fee:.2f}
• Criador recebe: R$ {creator_amount:.2f}

**Descrição do plano:**
{plan.description}

Escolha sua forma de pagamento:
"""
        
        keyboard = [
            [
                InlineKeyboardButton("💳 Cartão de Crédito", callback_data="pay_stripe"),
                InlineKeyboardButton("📱 PIX", callback_data="pay_pix")
            ],
            [
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
            ]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar callback de método de pagamento"""
    query = update.callback_query
    await query.answer()
    
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text(
            "❌ Sessão expirada. Por favor, comece novamente.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
            ]])
        )
        return
    
    if query.data == "pay_stripe":
        await process_stripe_payment(query, context, checkout_data)
    elif query.data == "pay_pix":
        await query.edit_message_text(
            "📱 PIX em breve! Por enquanto, use cartão de crédito.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data=f"plan_{checkout_data['group_id']}_{checkout_data['plan_id']}")
            ]])
        )

async def process_stripe_payment(query, context, checkout_data):
    """Processar pagamento via Stripe"""
    user = query.from_user
    
    # URLs de retorno
    bot_username = context.bot.username
    success_url = f"https://t.me/{bot_username}?start=success_{user.id}"
    cancel_url = f"https://t.me/{bot_username}?start=cancel"
    
    # Criar sessão no Stripe
    with get_db_session() as session:
        group = session.query(Group).get(checkout_data['group_id'])
        plan = session.query(PricingPlan).get(checkout_data['plan_id'])
        
        result = await create_checkout_session(
            amount=checkout_data['amount'],
            group_name=group.name,
            plan_name=plan.name,
            user_id=str(user.id),
            success_url=success_url,
            cancel_url=cancel_url
        )
    
    if result['success']:
        # Salvar session_id no contexto
        context.user_data['stripe_session_id'] = result['session_id']
        
        text = """
🔐 **Redirecionando para pagamento seguro...**

Você será direcionado para a página de pagamento do Stripe.

✅ **Pagamento 100% seguro**
🔒 Seus dados são protegidos
💳 Aceitamos todas as bandeiras

Após o pagamento, você voltará automaticamente para o Telegram.
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 Pagar com Stripe", url=result['url'])],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            f"❌ Erro ao criar sessão de pagamento: {result.get('error', 'Erro desconhecido')}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data=f"plan_{checkout_data['group_id']}_{checkout_data['plan_id']}")
            ]])
        )

async def add_user_to_group(bot, group_telegram_id: str, user_id: int):
    """Adicionar usuário ao grupo após pagamento"""
    try:
        # Tentar adicionar usuário ao grupo
        await bot.add_chat_member(
            chat_id=group_telegram_id,
            user_id=user_id
        )
        logger.info(f"Usuário {user_id} adicionado ao grupo {group_telegram_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário ao grupo: {e}")
        return False