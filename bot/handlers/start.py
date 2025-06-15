"""
Handler para comandos /start e /help com melhorias de UX
"""
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_main_menu, get_plans_menu
from app.models import Group, Creator, PricingPlan

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler do comando /start com experiência melhorada"""
    user = update.effective_user
    args = context.args
    
    # Verificar se veio com parâmetro de grupo
    if args and args[0].startswith('g_'):
        # Extrair ID do grupo
        group_code = args[0][2:]  # Remove 'g_'
        
        # Buscar grupo no banco
        with get_db_session() as session:
            group = session.query(Group).filter_by(telegram_id=group_code).first()
            
            if not group:
                await update.message.reply_text(
                    "❌ Grupo não encontrado. Verifique o link e tente novamente."
                )
                return
            
            if not group.is_active:
                await update.message.reply_text(
                    "❌ Este grupo não está mais aceitando novas assinaturas."
                )
                return
            
            # Buscar informações do criador
            creator = session.query(Creator).get(group.creator_id)
            
            # Buscar planos do grupo
            plans = group.pricing_plans.filter_by(is_active=True).order_by(PricingPlan.duration_days).all()
            
            if not plans:
                await update.message.reply_text(
                    "❌ Este grupo ainda não tem planos configurados."
                )
                return
            
            # Criar mensagem de boas-vindas profissional
            welcome_text = f"""
🎉 **Bem-vindo ao {group.name}!**

_{group.description or 'Grupo VIP exclusivo com conteúdo premium.'}_

━━━━━━━━━━━━━━━━━━━━

✨ **Benefícios Exclusivos:**
• 🔒 Acesso ao conteúdo premium
• 💬 Suporte direto com {creator.name if creator else 'o criador'}
• 🚀 Atualizações em primeira mão
• 👥 Comunidade exclusiva e engajada
• 📈 Conteúdo de alta qualidade

━━━━━━━━━━━━━━━━━━━━

💎 **Planos Disponíveis:**
"""
            
            # Adicionar planos com destaque
            best_value_plan = None
            most_popular_plan = None
            
            # Identificar melhor custo-benefício (maior duração)
            if len(plans) > 1:
                best_value_plan = max(plans, key=lambda p: p.duration_days)
                # Plano mais popular (geralmente o do meio ou mensal)
                for plan in plans:
                    if plan.duration_days == 30:
                        most_popular_plan = plan
                        break
                if not most_popular_plan and len(plans) > 1:
                    most_popular_plan = plans[1] if len(plans) > 2 else plans[0]
            
            for plan in plans:
                # Calcular desconto se houver
                discount_text = ""
                tag = ""
                
                if plan == best_value_plan and len(plans) > 1:
                    tag = " 🏆 **MELHOR CUSTO-BENEFÍCIO**"
                elif plan == most_popular_plan and len(plans) > 1:
                    tag = " ⭐ **MAIS VENDIDO**"
                
                # Calcular desconto baseado no plano mensal
                monthly_plan = next((p for p in plans if p.duration_days == 30), None)
                if monthly_plan and plan != monthly_plan and plan.duration_days > 30:
                    monthly_equivalent = (monthly_plan.price * plan.duration_days) / 30
                    discount = ((monthly_equivalent - plan.price) / monthly_equivalent) * 100
                    if discount > 0:
                        discount_text = f" `(-{discount:.0f}%)`"
                
                # Formatar duração
                if plan.duration_days == 30:
                    duration = "Mensal"
                elif plan.duration_days == 90:
                    duration = "Trimestral"
                elif plan.duration_days == 180:
                    duration = "Semestral"
                elif plan.duration_days == 365:
                    duration = "Anual"
                else:
                    duration = f"{plan.duration_days} dias"
                
                welcome_text += f"\n• **{plan.name}** ({duration}): R$ {plan.price:.2f}{discount_text}{tag}"
            
            welcome_text += "\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
            welcome_text += "🔐 **Garantias:**\n"
            welcome_text += "✅ Pagamento 100% seguro\n"
            welcome_text += "✅ Acesso imediato após pagamento\n"
            welcome_text += "✅ Suporte dedicado\n\n"
            welcome_text += "⚡ **Escolha seu plano e comece agora:**"
            
            # Criar teclado com os planos
            keyboard = []
            for plan in plans:
                # Criar texto do botão
                button_text = f"💳 {plan.name} - R$ {plan.price:.2f}"
                
                # Adicionar emoji especial para planos destacados
                if plan == best_value_plan and len(plans) > 1:
                    button_text = f"🏆 {plan.name} - R$ {plan.price:.2f}"
                elif plan == most_popular_plan and len(plans) > 1:
                    button_text = f"⭐ {plan.name} - R$ {plan.price:.2f}"
                
                keyboard.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"plan_{group.id}_{plan.id}"
                    )
                ])
            
            # Adicionar botão de cancelar
            keyboard.append([
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Enviar mensagem
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            # Mensagem adicional de urgência (opcional)
            await update.message.reply_text(
                "⏰ **Oferta por tempo limitado!**\n"
                "Garanta seu acesso agora e não perca nenhum conteúdo exclusivo.",
                parse_mode=ParseMode.MARKDOWN
            )
            
    else:
        # Mensagem padrão do bot (quando não tem parâmetro de grupo)
        welcome_text = f"""
👋 Olá {user.first_name}!

Eu sou o **TeleVIP Bot**, seu assistente para gerenciar assinaturas de grupos VIP no Telegram.

🤖 **O que eu posso fazer:**
• Processar pagamentos de assinaturas
• Adicionar você aos grupos automaticamente
• Notificar sobre renovações
• Gerenciar seus acessos

💡 **Como funciona:**
1. Você recebe um link de um criador
2. Escolhe o plano desejado
3. Faz o pagamento de forma segura
4. É adicionado automaticamente ao grupo

Use /help para ver todos os comandos disponíveis.
"""
        
        keyboard = get_main_menu()
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler do comando /help com informações detalhadas"""
    help_text = """
📋 **Comandos Disponíveis:**

👤 **Para Assinantes:**
/start - Iniciar conversa com o bot
/planos - Ver seus planos ativos
/status - Verificar status das assinaturas
/renovar - Renovar assinaturas próximas do vencimento
/help - Mostrar esta mensagem

👨‍💼 **Para Criadores:**
/setup - Configurar bot no grupo
/stats - Ver estatísticas do grupo
/broadcast - Enviar mensagem aos assinantes
/saques - Ver histórico de saques

💡 **Dicas:**
• Guarde sempre o comprovante de pagamento
• Ative as notificações para não perder avisos
• Renovações podem ter desconto especial
• Em caso de problemas, contate o suporte

🆘 **Suporte:**
Em caso de dúvidas ou problemas:
1. Verifique se seguiu todos os passos
2. Entre em contato com o criador do grupo
3. Use /suporte para mais opções

📱 **Sobre o TeleVIP:**
Plataforma segura e confiável para monetização de grupos no Telegram.
• Taxa única de 1% por transação
• Pagamentos via PIX e Cartão
• Saque rápido via PIX
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )


async def start_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para quando o pagamento foi bem-sucedido via link"""
    user = update.effective_user
    args = context.args
    
    if args and args[0].startswith('success_'):
        subscription_id = args[0].replace('success_', '')
        
        with get_db_session() as session:
            from app.models import Subscription
            
            subscription = session.query(Subscription).get(subscription_id)
            if subscription and subscription.telegram_user_id == str(user.id):
                group = subscription.group
                plan = subscription.plan
                
                success_text = f"""
✅ **Pagamento Confirmado!**

🎉 Parabéns! Você agora faz parte do **{group.name}**!

📋 **Detalhes da sua assinatura:**
• Plano: {plan.name}
• Válida até: {subscription.end_date.strftime('%d/%m/%Y')}
• Status: Ativa

🔗 **Acesse o grupo agora:**
{group.invite_link if group.invite_link else 'Link será enviado em breve'}

💡 **Primeiros passos:**
1. Entre no grupo pelo link acima
2. Leia as regras na mensagem fixada
3. Ative as notificações
4. Aproveite o conteúdo exclusivo!

Bem-vindo à comunidade! 🚀
"""
                
                await update.message.reply_text(
                    success_text,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )