"""
Handler para processamento de pagamentos multi-criador
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
            
            keyboard = []
            if days_left <= 7:
                keyboard.append([
                    InlineKeyboardButton("🔄 Renovar Agora", callback_data=f"renew_{existing_sub.id}")
                ])
            
            keyboard.append([
                InlineKeyboardButton("📊 Ver Status", callback_data="check_status")
            ])
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Calcular taxas da plataforma
        platform_fixed_fee = FIXED_FEE
        platform_percentage_fee = plan.price * PERCENTAGE_FEE
        total_platform_fee = platform_fixed_fee + platform_percentage_fee
        creator_receives = plan.price - total_platform_fee
        
        # Criar dados da sessão de checkout
        context.user_data['checkout'] = {
            'group_id': group_id,
            'group_name': group.name,
            'plan_id': plan_id,
            'plan_name': plan.name,
            'amount': plan.price,
            'duration_days': plan.duration_days,
            'user_id': user.id,
            'username': user.username or user.first_name,
            'creator_id': creator.id,
            'platform_fee': total_platform_fee,
            'creator_amount': creator_receives
        }
        
        # Mostrar resumo e opções de pagamento
        text = f"""
💳 **Resumo do Pedido**

━━━━━━━━━━━━━━━━━━━━━
**Grupo:** {group.name}
**Criador:** @{creator.username or creator.name}
**Plano:** {plan.name}
**Duração:** {plan.duration_days} dias
━━━━━━━━━━━━━━━━━━━━━

💰 **Detalhamento de Valores:**
• Valor do plano: R$ {plan.price:.2f}
• Taxa fixa: R$ {platform_fixed_fee:.2f}
• Taxa %: R$ {platform_percentage_fee:.2f} (7,99%)
• **Taxa total: R$ {total_platform_fee:.2f}**

✅ **Criador recebe: R$ {creator_receives:.2f}**

🔒 **Garantias:**
• Pagamento 100% seguro
• Acesso imediato após confirmação
• Suporte 24/7
• Sem renovação automática

Escolha a forma de pagamento:
"""
        
        keyboard = [
            [
                InlineKeyboardButton("💳 Cartão de Crédito", callback_data="pay_stripe"),
                InlineKeyboardButton("💰 PIX", callback_data="pay_pix")
            ],
            [
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")
            ]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar callback de pagamento"""
    query = update.callback_query
    await query.answer()
    
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text(
            "❌ Sessão expirada. Por favor, comece novamente.\n\n"
            "Use /start para ver suas opções."
        )
        return
    
    if query.data == "pay_stripe":
        await process_stripe_payment(query, context, checkout_data)
    elif query.data == "pay_pix":
        await process_pix_payment(query, context, checkout_data)
    elif query.data == "cancel_payment":
        await cancel_payment(update, context)
    elif query.data.startswith("pay_renewal_"):
        await handle_renewal_payment(update, context)

async def process_stripe_payment(query, context, checkout_data):
    """Processar pagamento via Stripe"""
    bot_username = context.bot.username
    
    # URLs de retorno
    success_url = f"https://t.me/{bot_username}?start=success_{checkout_data['user_id']}"
    cancel_url = f"https://t.me/{bot_username}?start=cancel"
    
    # Criar sessão no Stripe
    result = await create_checkout_session(
        amount=checkout_data['amount'],
        group_name=checkout_data['group_name'],
        plan_name=checkout_data['plan_name'],
        user_id=str(checkout_data['user_id']),
        success_url=success_url,
        cancel_url=cancel_url
    )
    
    if result['success']:
        # Salvar session_id para verificação posterior
        context.user_data['stripe_session_id'] = result['session_id']
        
        text = f"""
💳 **Pagamento via Cartão de Crédito**

Você será redirecionado para uma página segura do Stripe.

🔒 **Informações de Segurança:**
• Seus dados são protegidos com criptografia
• Não armazenamos informações do cartão
• Processamento certificado PCI-DSS
• Você pode cancelar a qualquer momento

📋 **Resumo:**
• Valor: R$ {checkout_data['amount']:.2f}
• Grupo: {checkout_data['group_name']}
• Plano: {checkout_data['plan_name']}

Clique no botão abaixo para prosseguir:
"""
        keyboard = [[
            InlineKeyboardButton(
                "💳 Ir para Pagamento Seguro",
                url=result['url']
            )
        ]]
        
        # Adicionar instruções
        text += "\n\n📱 **Após o pagamento:**"
        text += "\n1. Você será redirecionado de volta ao bot"
        text += "\n2. Receberá o link de acesso ao grupo"
        text += "\n3. Será adicionado automaticamente"
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            f"❌ Erro ao criar sessão de pagamento.\n\n"
            f"Detalhes: {result.get('error', 'Erro desconhecido')}\n\n"
            f"Por favor, tente novamente ou contate o suporte."
        )

async def process_pix_payment(query, context, checkout_data):
    """Processar pagamento via PIX"""
    # Por enquanto, mostrar mensagem de desenvolvimento
    # TODO: Integrar com provedor de PIX (Mercado Pago, PagSeguro, etc)
    
    text = f"""
💰 **Pagamento via PIX**

🚧 **Em Desenvolvimento**

O pagamento via PIX estará disponível em breve!

Por enquanto, você pode usar:
• 💳 Cartão de Crédito (Stripe)
• 💵 Transferência direta para o criador

**Valor:** R$ {checkout_data['amount']:.2f}
**Grupo:** {checkout_data['group_name']}

Deseja usar outro método de pagamento?
"""
    
    keyboard = [
        [
            InlineKeyboardButton("💳 Pagar com Cartão", callback_data="pay_stripe")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data=f"plan_{checkout_data['group_id']}_{checkout_data['plan_id']}")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar processo de pagamento"""
    query = update.callback_query
    
    # Limpar dados de checkout
    if 'checkout' in context.user_data:
        del context.user_data['checkout']
    if 'stripe_session_id' in context.user_data:
        del context.user_data['stripe_session_id']
    
    text = """
❌ **Pagamento Cancelado**

Seu processo de pagamento foi cancelado.
Nenhuma cobrança foi realizada.

O que você pode fazer agora:
• Ver suas assinaturas atuais
• Descobrir outros grupos
• Tentar novamente mais tarde

Use /start para voltar ao menu principal.
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start"),
            InlineKeyboardButton("🔍 Descobrir Grupos", callback_data="discover")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
            # Criar nova assinatura
            new_subscription = Subscription(
                group_id=checkout_data['group_id'],
                plan_id=checkout_data['plan_id'],
                telegram_user_id=str(user.id),
                telegram_username=user.username,
                status='active',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=checkout_data['duration_days']),
                auto_renew=False,
                payment_method='stripe'
            )
            session.add(new_subscription)
            session.flush()  # Para obter o ID
            
            # Criar transação com taxas corretas
            transaction = Transaction(
                subscription_id=new_subscription.id,
                group_id=checkout_data['group_id'],
                amount=checkout_data['amount'],
                fee_amount=checkout_data['platform_fee'],
                net_amount=checkout_data['creator_amount'],
                payment_method='stripe',
                payment_id=stripe_session_id,
                status='completed'
            )
            session.add(transaction)
            
            # Atualizar saldo do criador
            creator = session.query(Creator).get(checkout_data['creator_id'])
            if creator:
                creator.available_balance += checkout_data['creator_amount']
            
            session.commit()
            
            # Buscar grupo para gerar link
            group = session.query(Group).get(checkout_data['group_id'])
            
            # Gerar link de convite único
            try:
                # Criar link de convite que expira em 24h
                invite_link_obj = await context.bot.create_chat_invite_link(
                    chat_id=group.telegram_id,
                    member_limit=1,  # Apenas 1 uso
                    expire_date=datetime.utcnow() + timedelta(hours=24)
                )
                invite_link = invite_link_obj.invite_link
            except:
                # Fallback se não conseguir criar link
                invite_link = f"https://t.me/{group.telegram_id}"
            
            text = f"""
✅ **Pagamento Confirmado!**

🎉 Parabéns! Sua assinatura foi ativada com sucesso.

**📋 Detalhes da Assinatura:**
• Grupo: {checkout_data['group_name']}
• Plano: {checkout_data['plan_name']}
• Duração: {checkout_data['duration_days']} dias
• Válida até: {new_subscription.end_date.strftime('%d/%m/%Y')}
• ID da assinatura: #{new_subscription.id}

**💰 Valores:**
• Pago: R$ {checkout_data['amount']:.2f}
• Taxa plataforma: R$ {checkout_data['platform_fee']:.2f}
• Criador recebeu: R$ {checkout_data['creator_amount']:.2f}

**🔗 Acesso ao Grupo:**
{invite_link}

**⚠️ IMPORTANTE:**
• Este link é válido por 24 horas
• Use o link apenas uma vez
• Salve o link do grupo após entrar

**📧 Comprovante:**
Um email com o comprovante foi enviado.

**💡 Dicas:**
• Ative as notificações do grupo
• Leia as regras ao entrar
• Aproveite o conteúdo exclusivo!

Bem-vindo à comunidade! 🚀
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("🔗 Entrar no Grupo", url=invite_link)
                ],
                [
                    InlineKeyboardButton("📊 Ver Minhas Assinaturas", callback_data="check_status")
                ],
                [
                    InlineKeyboardButton("🔍 Descobrir Mais Grupos", callback_data="discover")
                ]
            ]
            
            # Limpar dados temporários
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Erro ao processar pagamento: {e}")
            text = """
⚠️ **Processando Pagamento**

Detectamos seu pagamento, mas houve um pequeno atraso no processamento.

Não se preocupe! Seu pagamento foi recebido e sua assinatura será ativada em instantes.

Se não receber o acesso em 5 minutos, entre em contato com o suporte.
"""
            keyboard = [
                [
                    InlineKeyboardButton("📞 Suporte", url="https://t.me/suporte_televip")
                ],
                [
                    InlineKeyboardButton("🔄 Verificar Novamente", callback_data="check_payment_status")
                ]
            ]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_payment_success_generic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar mensagem genérica de sucesso quando não temos os dados"""
    text = """
✅ **Pagamento Processado!**

Seu pagamento foi recebido com sucesso.

⏳ **O que acontece agora:**
1. Estamos verificando seu pagamento
2. Você receberá o link de acesso em instantes
3. Será adicionado automaticamente ao grupo

📊 Use /status para ver suas assinaturas ativas.

Se precisar de ajuda, use /help
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Ver Assinaturas", callback_data="check_status"),
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
        ]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Handlers para renovação (complemento do subscription.py)
async def handle_renewal_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar pagamento de renovação"""
    query = update.callback_query
    await query.answer()
    
    renewal_data = context.user_data.get('renewal')
    if not renewal_data:
        await query.edit_message_text(
            "❌ Sessão expirada. Use /status para ver suas assinaturas."
        )
        return
    
    if query.data == "pay_renewal_stripe":
        await process_renewal_stripe(query, context, renewal_data)
    elif query.data == "pay_renewal_pix":
        await process_renewal_pix(query, context, renewal_data)

async def process_renewal_stripe(query, context, renewal_data):
    """Processar renovação via Stripe"""
    bot_username = context.bot.username
    
    # Calcular taxa com desconto se aplicável
    amount = renewal_data['amount']
    platform_fixed_fee = FIXED_FEE
    platform_percentage_fee = amount * PERCENTAGE_FEE
    total_platform_fee = platform_fixed_fee + platform_percentage_fee
    creator_receives = amount - total_platform_fee
    
    # URLs de retorno
    success_url = f"https://t.me/{bot_username}?start=renewal_success_{renewal_data['subscription_id']}"
    cancel_url = f"https://t.me/{bot_username}?start=cancel"
    
    # Criar sessão no Stripe
    result = await create_checkout_session(
        amount=amount,
        group_name=f"Renovação - Grupo {renewal_data['group_id']}",
        plan_name="Renovação de Assinatura",
        user_id=str(query.from_user.id),
        success_url=success_url,
        cancel_url=cancel_url
    )
    
    if result['success']:
        context.user_data['stripe_renewal_session'] = result['session_id']
        
        text = f"""
🔄 **Renovação de Assinatura**

📋 **Detalhes:**
• Valor: R$ {amount:.2f}
• Taxa plataforma: R$ {total_platform_fee:.2f}
• Criador recebe: R$ {creator_receives:.2f}

{f"✨ Desconto aplicado: {renewal_data['discount']*100:.0f}%" if renewal_data.get('discount', 0) > 0 else ""}

Clique abaixo para prosseguir:
"""
        
        keyboard = [[
            InlineKeyboardButton(
                "💳 Pagar Renovação",
                url=result['url']
            )
        ]]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            "❌ Erro ao processar renovação. Tente novamente."
        )

async def process_renewal_pix(query, context, renewal_data):
    """Processar renovação via PIX"""
    # Similar ao pagamento normal, mas para renovação
    text = """
💰 **Renovação via PIX**

🚧 Em desenvolvimento...

Use o pagamento via cartão por enquanto.
"""
    
    keyboard = [
        [
            InlineKeyboardButton("💳 Pagar com Cartão", callback_data="pay_renewal_stripe")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="check_renewals")
        ]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )