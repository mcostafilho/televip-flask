"""
Comandos administrativos para criadores
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
from telegram.constants import ParseMode
from sqlalchemy import func

from bot.utils.database import get_db_session
from bot.utils.format_utils import (
    format_remaining_text, format_date, format_date_code,
    format_currency, escape_html
)
from app.models import Group, Creator, Subscription, Transaction, PricingPlan

logger = logging.getLogger(__name__)


async def _reply_private(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Responde no privado do admin e deleta o comando do grupo.
    Adiciona nota de contexto indicando o grupo de origem.
    Se não conseguir enviar no privado (usuário não iniciou o bot), avisa no grupo."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return

    # Adicionar nota de contexto ao texto
    group_name = escape_html(chat.title or 'Grupo')
    private_note = (
        f"\n\n<i>Respondido no privado para nao expor no grupo "
        f"<b>{group_name}</b>.</i>"
    )
    text_with_note = text + private_note

    # Tentar deletar o comando do grupo
    try:
        await update.message.delete()
    except Exception:
        pass  # Sem permissão para deletar

    # Enviar no privado
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=text_with_note,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    except Exception:
        # Usuário não iniciou o bot no privado — avisar no grupo sem revelar dados
        bot_me = await context.bot.get_me()
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"{user.mention_html()}, te enviei uma mensagem no privado. "
                 f"Se nao recebeu, inicie o bot primeiro: @{bot_me.username}",
            parse_mode=ParseMode.HTML,
        )


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configurar bot no grupo"""
    chat = update.effective_chat
    user = update.effective_user

    # Verificar se é um grupo
    if chat.type == 'private':
        text = (
            "<b>Comando /setup</b>\n\n"
            "Este comando deve ser usado diretamente no grupo.\n\n"
            "<i>Passo a passo:</i>\n"
            "1. Adicione o bot como administrador do grupo\n"
            "2. Envie <code>/setup</code> no grupo\n"
            "3. Copie o ID exibido e cole no painel web"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    # Verificar se o bot é admin
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            await _reply_private(update, context,
                "<b>Bot sem permissao</b>\n\n"
                "O bot precisa ser administrador deste grupo.\n\n"
                "<i>Promova o bot a administrador e tente novamente.</i>"
            )
            return
    except Exception:
        return

    # Verificar se o usuário é admin do grupo
    try:
        user_member = await context.bot.get_chat_member(chat.id, user.id)
        if user_member.status not in ['administrator', 'creator']:
            return  # Silencioso — não é admin, não mostra nada
    except Exception:
        return

    with get_db_session() as session:
        # Verificar se o usuário é um criador cadastrado
        creator = session.query(Creator).filter_by(
            telegram_id=str(user.id)
        ).first()

        if not creator:
            text = (
                f"<b>Informacoes do grupo</b>\n\n"
                f"<pre>"
                f"Grupo:       {chat.title}\n"
                f"Telegram ID: {chat.id}"
                f"</pre>\n\n"
                f"Copie o ID acima e cole no formulario de criacao de grupo no site.\n\n"
                f"<i>Conta Telegram nao vinculada.\n"
                f"Seu Telegram ID: <code>{user.id}</code>\n"
                f"Acesse seu perfil no site e adicione seu Telegram ID.</i>"
            )
            await _reply_private(update, context, text)
            return

        # Buscar ou criar grupo
        group = session.query(Group).filter_by(
            telegram_id=str(chat.id)
        ).first()

        if group:
            # Grupo já existe - mostrar status
            active_subs = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()

            # Receita total
            total_revenue = session.query(func.sum(Transaction.net_amount)).filter(
                Transaction.group_id == group.id,
                Transaction.status == 'completed'
            ).scalar() or 0

            text = (
                f"<b>Painel do grupo</b>\n\n"
                f"<pre>"
                f"Grupo:       {group.name}\n"
                f"Telegram ID: {chat.id}\n"
                f"Status:      {'Ativo' if group.is_active else 'Inativo'}\n"
                f"─────────────────────────\n"
                f"Assinantes:  {active_subs} ativos\n"
                f"Receita:     {format_currency(total_revenue)}"
                f"</pre>\n\n"
                f"<i>Desative TODOS os links de convite permanentes do grupo.\n"
                f"Use apenas os links gerados pelo bot para cada assinante.</i>"
            )

            keyboard = [
                [InlineKeyboardButton("Dashboard", url="https://televip.app/dashboard")]
            ]

        else:
            # Criar novo grupo
            group = Group(
                creator_id=creator.id,
                name=chat.title,
                telegram_id=str(chat.id),
                description=f"Grupo VIP de @{creator.username or creator.name}",
                is_active=True
            )
            session.add(group)
            session.commit()

            text = (
                f"<b>Grupo configurado!</b>\n\n"
                f"<pre>"
                f"Grupo:       {chat.title}\n"
                f"Telegram ID: {chat.id}"
                f"</pre>\n\n"
                f"<b>Proximos passos:</b>\n"
                f"1. Crie planos de assinatura no painel web\n"
                f"2. Compartilhe o link de convite com seus clientes"
            )

            keyboard = [
                [InlineKeyboardButton("Dashboard", url="https://televip.app/dashboard")]
            ]

        await _reply_private(update, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estatísticas — redireciona para o dashboard"""
    chat = update.effective_chat
    user = update.effective_user

    # Se for no privado, mostrar resumo com link
    if chat.type == 'private':
        text = (
            "<b>Relatorios e Estatisticas</b>\n\n"
            "Acesse o painel completo com graficos, receita, "
            "assinantes e historico de transacoes pelo portal:"
        )
        keyboard = [
            [InlineKeyboardButton("Abrir Dashboard", url="https://televip.app/dashboard")]
        ]
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # No grupo, verificar permissões
    try:
        user_member = await context.bot.get_chat_member(chat.id, user.id)
        if user_member.status not in ['administrator', 'creator']:
            return  # Silencioso
    except Exception:
        return

    # Responder no privado com link pro dashboard
    group_title = escape_html(chat.title or 'Grupo')
    text = (
        f"<b>Relatorios — {group_title}</b>\n\n"
        "Acesse o painel completo com graficos, receita, "
        "assinantes e historico de transacoes pelo portal:"
        f"\n\n<i>Respondido no privado para nao expor no grupo "
        f"<b>{group_title}</b>.</i>"
    )
    keyboard = [
        [InlineKeyboardButton("Abrir Dashboard", url="https://televip.app/dashboard")]
    ]

    # Deletar comando do grupo
    try:
        await update.message.delete()
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        bot_me = await context.bot.get_me()
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"{user.mention_html()}, te enviei no privado. "
                 f"Se nao recebeu, inicie o bot: @{bot_me.username}",
            parse_mode=ParseMode.HTML,
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar mensagem para todos os assinantes"""
    chat = update.effective_chat
    user = update.effective_user

    # Verificar se é admin
    if chat.type != 'private':
        try:
            user_member = await context.bot.get_chat_member(chat.id, user.id)
            if user_member.status not in ['administrator', 'creator']:
                return  # Silencioso
        except Exception:
            return

        # Deletar comando do grupo
        try:
            await update.message.delete()
        except Exception:
            pass

    # Verificar se tem texto
    if not context.args:
        # Salvar grupo de origem para o fluxo conversacional
        if chat.type != 'private':
            context.user_data['awaiting_broadcast_from_group'] = str(chat.id)

        text = (
            "<b>Broadcast</b>\n\n"
            "Escreva a mensagem que deseja enviar para todos os assinantes ativos.\n\n"
            "<i>Basta digitar sua mensagem aqui neste chat e enviar.</i>"
        )
        keyboard = [[InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")]]

        if chat.type == 'private':
            await update.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            group_title = escape_html(chat.title or 'Grupo')
            text += (
                f"\n\n<i>Respondido no privado para nao expor no grupo "
                f"<b>{group_title}</b>.</i>"
            )
            try:
                await context.bot.send_message(
                    chat_id=user.id, text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                bot_me = await context.bot.get_me()
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"{user.mention_html()}, te enviei no privado. "
                         f"Se nao recebeu, inicie o bot: @{bot_me.username}",
                    parse_mode=ParseMode.HTML,
                )

        context.user_data['awaiting_broadcast'] = True
        return

    # Pegar mensagem
    broadcast_text = ' '.join(context.args)

    # Se no privado, perguntar qual grupo
    if chat.type == 'private':
        await select_group_for_broadcast(update, context, broadcast_text)
    else:
        # Broadcast para o grupo atual — confirmar no privado
        await confirm_broadcast_private(update, context, chat.id, broadcast_text)

async def select_group_for_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    """Selecionar grupo para broadcast quando no privado"""
    user = update.effective_user

    with get_db_session() as session:
        creator = session.query(Creator).filter_by(
            telegram_id=str(user.id)
        ).first()

        if not creator:
            await update.message.reply_text("Você não é um criador cadastrado!")
            return

        groups = session.query(Group).filter_by(
            creator_id=creator.id,
            is_active=True
        ).all()

        if not groups:
            await update.message.reply_text("Você não tem grupos configurados!")
            return

        # Salvar mensagem no contexto
        context.user_data['broadcast_message'] = message

        text = "<b>Selecione o grupo para broadcast:</b>\n"
        keyboard = []

        for group in groups:
            active_subs = session.query(Subscription).filter_by(
                group_id=group.id,
                status='active'
            ).count()
            group_name = escape_html(group.name)

            text += f"\n{group_name} ({active_subs} assinantes)"

            keyboard.append([
                InlineKeyboardButton(
                    f"{group.name} ({active_subs})",
                    callback_data=f"broadcast_to_{group.id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")
        ])

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, group_telegram_id: str, message: str):
    """Confirmar envio de broadcast"""
    context.user_data['broadcast_message'] = message
    context.user_data['broadcast_group_telegram_id'] = str(group_telegram_id)

    escaped_message = escape_html(message)

    text = (
        f"<b>Confirmar Broadcast</b>\n\n"
        f"<b>Mensagem:</b>\n{escaped_message}\n\n"
        f"Deseja enviar esta mensagem para todos os assinantes ativos?"
    )
    keyboard = [
        [
            InlineKeyboardButton("Enviar", callback_data="broadcast_confirm"),
            InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")
        ]
    ]
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_broadcast_private(update: Update, context: ContextTypes.DEFAULT_TYPE, group_telegram_id: str, message: str):
    """Confirmar envio de broadcast — envia confirmação no privado do admin"""
    user = update.effective_user
    chat = update.effective_chat
    context.user_data['broadcast_message'] = message
    context.user_data['broadcast_group_telegram_id'] = str(group_telegram_id)

    escaped_message = escape_html(message)
    group_title = escape_html(chat.title or 'Grupo')

    # Buscar nome do grupo do banco
    with get_db_session() as session:
        group = session.query(Group).filter_by(telegram_id=str(group_telegram_id)).first()
        if group:
            group_title = escape_html(group.name)

    text = (
        f"<b>Confirmar Broadcast — {group_title}</b>\n\n"
        f"<b>Mensagem:</b>\n{escaped_message}\n\n"
        f"Deseja enviar esta mensagem para todos os assinantes ativos?"
        f"\n\n<i>Respondido no privado para nao expor no grupo "
        f"<b>{group_title}</b>.</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("Enviar", callback_data="broadcast_confirm"),
            InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")
        ]
    ]
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        # Avisar no grupo sem expor a mensagem
        bot_me = await context.bot.get_me()
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"{user.mention_html()}, te enviei a confirmacao no privado. "
                 f"Se nao recebeu, inicie o bot: @{bot_me.username}",
            parse_mode=ParseMode.HTML,
        )


async def handle_broadcast_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback broadcast_to_GROUPID"""
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.replace("broadcast_to_", ""))
    message = context.user_data.get('broadcast_message', '')

    if not message:
        await query.edit_message_text("Nenhuma mensagem para enviar. Use /broadcast <mensagem>")
        return

    context.user_data['broadcast_group_id'] = group_id

    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        group_name = escape_html(group.name) if group else 'Desconhecido'
        active_count = session.query(Subscription).filter_by(
            group_id=group_id, status='active'
        ).count()

    escaped_message = escape_html(message)

    text = (
        f"<b>Confirmar Broadcast</b>\n\n"
        f"<b>Grupo:</b> {group_name}\n"
        f"<b>Assinantes ativos:</b> {active_count}\n\n"
        f"<b>Mensagem:</b>\n{escaped_message}\n\n"
        f"Confirma o envio?"
    )
    keyboard = [
        [
            InlineKeyboardButton("Enviar", callback_data="broadcast_confirm"),
            InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")
        ]
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enviar broadcast para todos os assinantes ativos do grupo"""
    query = update.callback_query
    await query.answer("Enviando...")

    message = context.user_data.get('broadcast_message', '')
    group_id = context.user_data.get('broadcast_group_id')
    group_telegram_id = context.user_data.get('broadcast_group_telegram_id')

    if not message:
        await query.edit_message_text("Nenhuma mensagem para enviar.")
        return

    with get_db_session() as session:
        if group_id:
            group = session.query(Group).get(group_id)
        elif group_telegram_id:
            group = session.query(Group).filter_by(telegram_id=str(group_telegram_id)).first()
        else:
            await query.edit_message_text("Grupo não identificado.")
            return

        if not group:
            await query.edit_message_text("Grupo não encontrado.")
            return

        # Buscar assinantes ativos
        subs = session.query(Subscription).filter_by(
            group_id=group.id, status='active'
        ).all()

        if not subs:
            await query.edit_message_text("Nenhum assinante ativo neste grupo.")
            return

        group_name = escape_html(group.name)
        escaped_message = escape_html(message)
        anti_leak = group.anti_leak_enabled

        sent = 0
        failed = 0
        for sub in subs:
            try:
                msg_text = f"<b>Mensagem de {group_name}</b>\n\n{escaped_message}"

                if anti_leak:
                    msg_text += (
                        "\n\n<i>&#9888; Conteudo exclusivo e confidencial. "
                        "Nao salve, copie ou compartilhe. "
                        "Temos rastreamento avancado que identifica vazamentos. "
                        "Vazadores serao removidos permanentemente.</i>"
                    )
                    from bot.utils.watermark import watermark_text
                    msg_text = watermark_text(msg_text, sub.id)

                await context.bot.send_message(
                    chat_id=int(sub.telegram_user_id),
                    text=msg_text,
                    parse_mode=ParseMode.HTML,
                    protect_content=anti_leak,
                )
                sent += 1
            except Exception as e:
                logger.warning(f"Falha ao enviar broadcast para {sub.telegram_user_id}: {e}")
                failed += 1

        # Atualizar last_broadcast_at
        group.last_broadcast_at = datetime.utcnow()
        session.commit()

    # Limpar dados do contexto
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('broadcast_group_id', None)
    context.user_data.pop('broadcast_group_telegram_id', None)

    await query.edit_message_text(
        f"<b>Broadcast enviado</b>\n\n"
        f"Mensagens enviadas: <code>{sent}</code>\n"
        f"Falhas: <code>{failed}</code>",
        parse_mode=ParseMode.HTML
    )


async def handle_cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar broadcast"""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('broadcast_group_id', None)
    context.user_data.pop('broadcast_group_telegram_id', None)
    await query.edit_message_text("Broadcast cancelado.")

async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para capturar texto do broadcast quando awaiting_broadcast está ativo.
    Roda em group=-1 para interceptar antes dos botões fixos.
    Quando NÃO está esperando broadcast, retorna sem ApplicationHandlerStop
    para que os handlers normais (group=0) processem."""
    if not context.user_data.get('awaiting_broadcast'):
        return  # Não está esperando broadcast — deixa handlers normais processarem

    # Limpar flag
    context.user_data.pop('awaiting_broadcast', None)

    broadcast_text = update.message.text
    group_telegram_id = context.user_data.pop('awaiting_broadcast_from_group', None)

    if group_telegram_id:
        # Veio de um grupo — confirmar diretamente para aquele grupo
        await confirm_broadcast_private_from_text(update, context, group_telegram_id, broadcast_text)
    else:
        # Veio do privado — selecionar grupo
        await select_group_for_broadcast(update, context, broadcast_text)

    # Impedir que handlers do group=0 (botões fixos) processem esta mensagem
    raise ApplicationHandlerStop


async def confirm_broadcast_private_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, group_telegram_id: str, message: str):
    """Confirmar broadcast quando a mensagem foi digitada no privado após /broadcast no grupo"""
    context.user_data['broadcast_message'] = message
    context.user_data['broadcast_group_telegram_id'] = str(group_telegram_id)

    escaped_message = escape_html(message)

    with get_db_session() as session:
        group = session.query(Group).filter_by(telegram_id=str(group_telegram_id)).first()
        group_title = escape_html(group.name) if group else 'Grupo'
        active_count = 0
        if group:
            active_count = session.query(Subscription).filter_by(
                group_id=group.id, status='active'
            ).count()

    text = (
        f"<b>Confirmar Broadcast — {group_title}</b>\n"
        f"<i>{active_count} assinantes ativos</i>\n\n"
        f"<b>Mensagem:</b>\n{escaped_message}\n\n"
        f"Deseja enviar?"
    )
    keyboard = [
        [
            InlineKeyboardButton("Enviar", callback_data="broadcast_confirm"),
            InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")
        ]
    ]
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================== FUNÇÕES EXTRAS ADICIONADAS ====================

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler quando usuário tenta entrar no grupo"""
    chat = update.effective_chat
    user = update.effective_user

    # Verificar se é um grupo
    if chat.type not in ['group', 'supergroup']:
        return

    with get_db_session() as session:
        # Verificar se o usuário tem assinatura ativa
        group = session.query(Group).filter_by(
            telegram_id=str(chat.id)
        ).first()

        if not group:
            return

        subscription = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()

        if not subscription or subscription.end_date < datetime.utcnow():
            # Remover usuário não autorizado
            try:
                await context.bot.ban_chat_member(
                    chat_id=chat.id,
                    user_id=user.id
                )
                await context.bot.unban_chat_member(
                    chat_id=chat.id,
                    user_id=user.id
                )
                logger.warning(f"Usuário {user.id} removido do grupo {chat.id} - sem assinatura")

                group_name = escape_html(group.name)

                # Enviar mensagem privada ao usuário
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"<b>Acesso negado</b>\n\n"
                            f"Você foi removido de <b>{group_name}</b>.\n"
                            f"Para acessar, é necessário ter uma assinatura ativa."
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass  # Usuário pode ter bloqueado o bot

            except Exception as e:
                logger.error(f"Erro ao remover usuário do grupo: {e}")
        else:
            # Usuário autorizado - enviar mensagem de boas-vindas
            logger.info(f"Usuário {user.id} autorizado no grupo {chat.id}")

            remaining = format_remaining_text(subscription.end_date)
            group_name = escape_html(group.name)
            plan_name = escape_html(subscription.plan.name) if subscription.plan else "N/A"

            try:
                welcome_text = (
                    f"Bem-vindo ao <b>{group_name}</b>!\n\n"
                    f"Plano: <code>{plan_name}</code>\n"
                    f"Acesso até: {format_date_code(subscription.end_date)}\n\n"
                    f"<i>Respeite as regras do grupo.</i>"
                )

                # Enviar como mensagem privada para não poluir o grupo
                await context.bot.send_message(
                    chat_id=user.id,
                    text=welcome_text,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass  # Não é crítico se falhar

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para novos membros no chat - verificacao rapida de assinatura"""
    message = update.message

    if not message or not message.new_chat_members:
        return

    chat = message.chat

    for new_member in message.new_chat_members:
        # Ignorar se for o proprio bot
        if new_member.id == context.bot.id:
            continue

        # Ignorar bots (admins podem adicionar bots livremente)
        if new_member.is_bot:
            continue

        with get_db_session() as session:
            group = session.query(Group).filter_by(
                telegram_id=str(chat.id)
            ).first()

            if not group:
                continue

            # Verificar se esta na lista de excecao (whitelist criador ou system)
            if group.is_whitelisted(str(new_member.id)) or group.is_system_whitelisted(str(new_member.id)):
                logger.info(f"Usuario {new_member.id} na whitelist do grupo {chat.id} - permitido")
                continue

            # Verificar se é admin/creator do grupo (moderadores)
            try:
                member_info = await context.bot.get_chat_member(chat.id, new_member.id)
                if member_info.status in ['administrator', 'creator']:
                    logger.info(f"Usuario {new_member.id} e admin do grupo {chat.id} - permitido")
                    continue
            except Exception:
                pass  # Se falhar, continua verificacao normal

            subscription = session.query(Subscription).filter_by(
                group_id=group.id,
                telegram_user_id=str(new_member.id),
                status='active'
            ).first()

            if not subscription or subscription.end_date < datetime.utcnow():
                # UNAUTHORIZED — kick FIRST, then notify (minimize access window)
                try:
                    await context.bot.ban_chat_member(
                        chat_id=chat.id,
                        user_id=new_member.id
                    )
                    await context.bot.unban_chat_member(
                        chat_id=chat.id,
                        user_id=new_member.id,
                        only_if_banned=True
                    )
                    logger.warning(f"Usuario {new_member.id} removido do grupo {chat.id} - sem assinatura")

                    # Delete the "joined" system message to avoid confusion
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    group_name = escape_html(group.name)

                    # Notify user AFTER removal (non-blocking)
                    try:
                        await context.bot.send_message(
                            chat_id=new_member.id,
                            text=(
                                f"<b>Acesso negado</b>\n\n"
                                f"Você foi removido de <b>{group_name}</b>.\n"
                                f"Para acessar, é necessário ter uma assinatura ativa."
                            ),
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass  # User may have blocked bot

                except Exception as e:
                    logger.error(f"Erro ao remover usuario nao autorizado: {e}")
            else:
                # Authorized — send welcome privately
                logger.info(f"Usuario {new_member.id} autorizado no grupo {chat.id}")
                remaining = format_remaining_text(subscription.end_date)
                group_name = escape_html(group.name)
                plan_name = escape_html(subscription.plan.name) if subscription.plan else "N/A"

                try:
                    await context.bot.send_message(
                        chat_id=new_member.id,
                        text=(
                            f"Bem-vindo ao <b>{group_name}</b>!\n\n"
                            f"Plano: <code>{plan_name}</code>\n"
                            f"Acesso até: {format_date_code(subscription.end_date)}\n\n"
                            f"<i>Respeite as regras do grupo.</i>"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass


async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para ChatMemberUpdated — detecta entrada em canais"""
    member_update = update.chat_member
    if not member_update:
        return

    chat = member_update.chat

    # Processar apenas canais (grupos já são tratados por NEW_CHAT_MEMBERS)
    if chat.type != 'channel':
        return

    new_status = member_update.new_chat_member.status
    user = member_update.new_chat_member.user

    # Só processar quando alguém ENTRA no canal (status muda para 'member')
    if new_status != 'member':
        return

    # Ignorar bots
    if user.is_bot:
        return

    with get_db_session() as session:
        group = session.query(Group).filter_by(
            telegram_id=str(chat.id)
        ).first()

        if not group:
            return

        # Verificar whitelists
        if group.is_whitelisted(str(user.id)) or group.is_system_whitelisted(str(user.id)):
            logger.info(f"Usuario {user.id} na whitelist do canal {chat.id} - permitido")
            return

        # Verificar se é admin/creator
        try:
            member_info = await context.bot.get_chat_member(chat.id, user.id)
            if member_info.status in ['administrator', 'creator']:
                return
        except Exception:
            pass

        # Verificar assinatura ativa
        subscription = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()

        if not subscription or subscription.end_date < datetime.utcnow():
            # Não autorizado — remover do canal
            try:
                await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
                await context.bot.unban_chat_member(chat_id=chat.id, user_id=user.id, only_if_banned=True)
                logger.warning(f"Usuario {user.id} removido do canal {chat.id} - sem assinatura")

                group_name = escape_html(group.name)

                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"<b>Acesso negado</b>\n\n"
                            f"Você foi removido de <b>{group_name}</b>.\n"
                            f"Para acessar, é necessário ter uma assinatura ativa."
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Erro ao remover usuario de canal: {e}")
        else:
            # Autorizado — enviar boas-vindas no privado
            logger.info(f"Usuario {user.id} autorizado no canal {chat.id}")
            group_name = escape_html(group.name)
            plan_name = escape_html(subscription.plan.name) if subscription.plan else "N/A"
            remaining = format_remaining_text(subscription.end_date)

            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        f"Bem-vindo ao canal <b>{group_name}</b>!\n\n"
                        f"Plano: <code>{plan_name}</code>\n"
                        f"Acesso até: {format_date_code(subscription.end_date)}\n\n"
                        f"<i>Aproveite o conteúdo!</i>"
                    ),
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass  # Usuário pode ter bloqueado o bot
