"""
Handler para processar pagamentos com UX melhorada
"""
import os
import qrcode
import io
import stripe
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import create_checkout_session
from bot.keyboards.menus import get_payment_keyboard, get_cancel_keyboard
from app.models import Group, PricingPlan, Subscription, Transaction, Creator
from app.services.stripe_service import StripeService

logger = logging.getLogger(__name__)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler quando usuário seleciona um plano - Melhorado"""
    query = update.callback_query
    await query.answer()
    
    # Extrair dados do callback
    data = query.data.split('_')
    group_id = int(data[1])
    plan_id = int(data[2])
    
    user = query.from_user
    
    with get_db_session() as session:
        # Buscar plano e grupo
        plan = session.query(PricingPlan).get(plan_id)
        group = session.query(Group).get(group_id)
        
        if not plan or not group:
            await query.edit_message_text("❌ Plano não encontrado.")
            return
        
        # Verificar se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group_id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if existing_sub:
            days_left = (existing_sub.end_date - datetime.utcnow()).days
            
            renewal_text = f"""
✅ **Você já possui uma assinatura ativa!**

📱 Grupo: {group.name}
📅 Válida até: {existing_sub.end_date.strftime('%d/%m/%Y')}
⏱️ Dias restantes: {days_left}

💡 **Opções:**
• Use /status para ver todos os detalhes
• Aguarde próximo ao vencimento para renovar com desconto
• Entre em contato com o suporte se precisar de ajuda
"""
            
            keyboard = [[
                InlineKeyboardButton("📊 Ver Status", callback_data="check_status"),
                InlineKeyboardButton("❌ Fechar", callback_data="close")
            ]]
            
            await query.edit_message_text(
                renewal_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Criar sessão de checkout
        checkout_data = {
            'user_id': user.id,
            'username': user.username,
            'group_id': group_id,
            'plan_id': plan_id,
            'amount': plan.price
        }
        
        # Armazenar dados temporariamente
        context.user_data['checkout'] = checkout_data
        
        # Formatar duração
        if plan.duration_days == 30:
            duration_text = "1 mês"
        elif plan.duration_days == 90:
            duration_text = "3 meses"
        elif plan.duration_days == 180:
            duration_text = "6 meses"
        elif plan.duration_days == 365:
            duration_text = "1 ano"
        else:
            duration_text = f"{plan.duration_days} dias"
        
        # Calcular valor por dia
        daily_value = plan.price / plan.duration_days
        
        # Oferecer opções de pagamento
        payment_text = f"""
💳 **Confirmar Assinatura**

📱 **Grupo:** {group.name}
📋 **Plano:** {plan.name}
⏱️ **Duração:** {duration_text}
💰 **Valor:** R$ {plan.price:.2f}
📊 **Valor por dia:** R$ {daily_value:.2f}

━━━━━━━━━━━━━━━━━━━━

🔐 **Formas de Pagamento:**
Escolha como prefere pagar:
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 Cartão de Crédito (Stripe)", callback_data=f"stripe_{plan_id}")],
            [InlineKeyboardButton("🔄 PIX - Pagamento Instantâneo", callback_data=f"pix_{plan_id}")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")]
        ]
        
        await query.edit_message_text(
            payment_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_pix_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar pagamento via PIX - Melhorado"""
    query = update.callback_query
    await query.answer()
    
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text("❌ Sessão expirada. Por favor, comece novamente.")
        return
    
    with get_db_session() as session:
        plan = session.query(PricingPlan).get(checkout_data['plan_id'])
        group = session.query(Group).get(checkout_data['group_id'])
        creator = session.query(Creator).get(group.creator_id)
        
        # Criar pré-assinatura para reservar o lugar
        end_date = datetime.utcnow() + timedelta(days=plan.duration_days)
        
        subscription = Subscription(
            group_id=group.id,
            plan_id=plan.id,
            telegram_user_id=str(checkout_data['user_id']),
            telegram_username=checkout_data['username'],
            start_date=datetime.utcnow(),
            end_date=end_date,
            status='pending'
        )
        
        session.add(subscription)
        session.flush()
        
        # Criar transação pendente
        transaction = Transaction(
            subscription_id=subscription.id,
            amount=plan.price,
            fee=plan.price * 0.01,
            net_amount=plan.price * 0.99,
            status='pending',
            payment_method='pix'
        )
        
        session.add(transaction)
        session.commit()
        
        # Gerar dados do PIX
        pix_data = generate_pix_data(plan.price, creator)
        
        # Criar QR Code
        qr_image = generate_qr_code(pix_data['qr_code_data'])
        
        # Salvar ID da transação no contexto
        context.user_data['pending_transaction_id'] = transaction.id
        
        # Mensagem com instruções detalhadas
        payment_text = f"""
💳 **Pagamento via PIX**

━━━━━━━━━━━━━━━━━━━━

📱 **Resumo do Pedido:**
• Grupo: {group.name}
• Plano: {plan.name}
• Valor: **R$ {plan.price:.2f}**

━━━━━━━━━━━━━━━━━━━━

📋 **Instruções (Passo a Passo):**

1️⃣ **Abra o app do seu banco**
2️⃣ **Escolha pagar com PIX**
3️⃣ **Escaneie o QR Code acima** ou copie o código
4️⃣ **Confirme o pagamento**
5️⃣ **Envie o comprovante aqui**

━━━━━━━━━━━━━━━━━━━━

📱 **Chave PIX (Copia e Cola):**
```
{pix_data['pix_key']}
```

⏰ **Importante:**
• Este código expira em 30 minutos
• Após pagar, envie o comprovante
• Acesso liberado em até 2 minutos

🔐 Pagamento 100% seguro
"""
        
        keyboard = [[
            InlineKeyboardButton("✅ Já fiz o pagamento", callback_data=f"confirm_pix_{transaction.id}"),
        ], [
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")
        ]]
        
        # Enviar QR Code
        await query.message.reply_photo(
            photo=qr_image,
            caption=payment_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Deletar mensagem anterior
        await query.message.delete()

async def handle_pix_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para quando usuário confirma que fez o PIX"""
    query = update.callback_query
    await query.answer()
    
    # Extrair ID da transação
    transaction_id = int(query.data.split('_')[-1])
    
    # Atualizar mensagem
    await query.edit_message_caption(
        caption="""
📸 **Envie o comprovante do PIX**

Por favor, envie uma foto clara do comprovante de pagamento.

✅ O comprovante deve mostrar:
• Valor pago
• Data/hora
• Destinatário

⏳ Processamento em até 2 minutos...
""",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=None
    )
    
    # Salvar estado esperando comprovante
    context.user_data['waiting_receipt'] = True
    context.user_data['transaction_id'] = transaction_id

async def process_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar comprovante de pagamento - Melhorado"""
    user = update.effective_user
    
    # Verificar se está esperando comprovante
    if not context.user_data.get('waiting_receipt'):
        return
    
    # Verificar se enviou foto
    if not update.message.photo:
        await update.message.reply_text(
            "📸 Por favor, envie uma **foto** do comprovante de pagamento.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    transaction_id = context.user_data.get('transaction_id')
    if not transaction_id:
        await update.message.reply_text("❌ Erro ao processar pagamento. Tente novamente.")
        return
    
    # Mostrar que está processando
    processing_msg = await update.message.reply_text(
        "⏳ **Verificando pagamento...**\n\nIsso pode levar alguns segundos.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    with get_db_session() as session:
        # Buscar transação
        transaction = session.query(Transaction).get(transaction_id)
        if not transaction:
            await processing_msg.edit_text("❌ Transação não encontrada.")
            return
        
        subscription = transaction.subscription
        group = subscription.group
        plan = subscription.plan
        
        # Simular verificação (em produção, aqui verificaria o pagamento real)
        import asyncio
        await asyncio.sleep(2)  # Simular delay de verificação
        
        # Aprovar pagamento
        transaction.status = 'completed'
        transaction.paid_at = datetime.utcnow()
        
        subscription.status = 'active'
        
        # Atualizar saldo do criador
        creator = session.query(Creator).get(group.creator_id)
        creator.balance += transaction.net_amount
        creator.total_earned += transaction.net_amount
        
        # Incrementar contador
        group.total_subscribers += 1
        
        session.commit()
        
        # Limpar dados do contexto
        context.user_data.pop('waiting_receipt', None)
        context.user_data.pop('transaction_id', None)
        context.user_data.pop('checkout', None)
        
        # Deletar mensagem de processamento
        await processing_msg.delete()
        
        # Gerar link de convite único
        try:
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=group.telegram_id,
                member_limit=1,
                expire_date=datetime.now() + timedelta(hours=24)
            )
            invite_url = invite_link.invite_link
        except:
            invite_url = group.invite_link or "Link será enviado pelo administrador"
        
        # Mensagem de sucesso elaborada
        success_text = f"""
✅ **Pagamento Aprovado!**

🎉 **Parabéns! Você agora é membro VIP!**

━━━━━━━━━━━━━━━━━━━━

📱 **{group.name}**
📋 Plano: {plan.name}
📅 Válido até: {subscription.end_date.strftime('%d/%m/%Y')}

━━━━━━━━━━━━━━━━━━━━

🔗 **Seu link exclusivo de acesso:**
{invite_url}

⚠️ **Importante:**
• Este link é válido por 24 horas
• Use apenas uma vez
• Não compartilhe com outras pessoas

━━━━━━━━━━━━━━━━━━━━

💡 **Próximos passos:**
1. Clique no link acima
2. Entre no grupo
3. Leia as regras fixadas
4. Aproveite o conteúdo!

Bem-vindo à nossa comunidade exclusiva! 🚀

_Dúvidas? Use /help_
"""
        
        await update.message.reply_text(
            success_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        # Notificar o criador (opcional)
        if creator.telegram_id:
            try:
                creator_notification = f"""
💰 **Nova Assinatura!**

👤 Usuário: @{subscription.telegram_username or 'Sem username'}
📱 Grupo: {group.name}
📋 Plano: {plan.name}
💵 Valor: R$ {transaction.net_amount:.2f} (líquido)

Total de assinantes: {group.total_subscribers}
"""
                await context.bot.send_message(
                    chat_id=creator.telegram_id,
                    text=creator_notification,
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass

async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar processo de pagamento - Melhorado"""
    query = update.callback_query
    await query.answer()
    
    # Limpar dados do checkout
    context.user_data.pop('checkout', None)
    context.user_data.pop('waiting_receipt', None)
    context.user_data.pop('transaction_id', None)
    
    await query.edit_message_text(
        "❌ **Pagamento cancelado**\n\n"
        "Que pena! Esperamos você em breve.\n\n"
        "💡 Lembre-se: nossos grupos oferecem conteúdo exclusivo e de alta qualidade!\n\n"
        "Use /start quando quiser tentar novamente.",
        parse_mode=ParseMode.MARKDOWN
    )

def generate_pix_data(amount: float, creator: Creator) -> dict:
    """Gerar dados do PIX"""
    # Em produção, integrar com API de pagamento real
    return {
        'pix_key': creator.email if creator else "pix@televip.com.br",
        'qr_code_data': f"00020126580014BR.GOV.BCB.PIX0136{creator.email}-{amount:.2f}",
        'transaction_id': f"TXN{int(datetime.now().timestamp())}"
    }

def generate_qr_code(data: str) -> io.BytesIO:
    """Gerar imagem do QR Code"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Adicionar logo ou texto (opcional)
    bio = io.BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    
    return bio