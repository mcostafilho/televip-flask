"""
Sistema Anti-Vazamento (Anti-Leak)
Comando /antileak, monitoramento de mensagens e toggle de proteção.
"""
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.format_utils import escape_html
from app.models import Group

logger = logging.getLogger(__name__)

INVITE_LINK_PATTERN = re.compile(r't\.me/(\+|joinchat/)\S+', re.IGNORECASE)


async def enforce_antileak_permissions(bot, group):
    """Aplicar restrições de permissão no grupo (bloquear convites)."""
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=False,
        can_change_info=False,
        can_pin_messages=False,
    )
    await bot.set_chat_permissions(
        chat_id=int(group.telegram_id),
        permissions=permissions,
    )


async def restore_default_permissions(bot, group):
    """Restaurar permissões padrão do grupo."""
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
        can_change_info=False,
        can_pin_messages=False,
    )
    await bot.set_chat_permissions(
        chat_id=int(group.telegram_id),
        permissions=permissions,
    )


async def antileak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /antileak — mostra status e permite ativar/desativar."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        await update.message.reply_text(
            "Este comando deve ser usado dentro de um grupo ou canal.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Verificar se é admin
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                "Apenas administradores podem usar este comando."
            )
            return
    except Exception:
        return

    with get_db_session() as session:
        group = session.query(Group).filter_by(telegram_id=str(chat.id)).first()
        if not group:
            await update.message.reply_text(
                "Grupo não configurado. Use /setup primeiro."
            )
            return

        # Verificar proteção nativa do Telegram
        try:
            chat_info = await context.bot.get_chat(chat.id)
            has_protected = getattr(chat_info, 'has_protected_content', False)
        except Exception:
            has_protected = False

        # Verificar permissões atuais
        try:
            chat_info = await context.bot.get_chat(chat.id)
            perms = chat_info.permissions
            invite_blocked = not perms.can_invite_users if perms else False
        except Exception:
            invite_blocked = False

        enabled = group.anti_leak_enabled
        group_name = escape_html(group.name)
        status_icon = "ON" if enabled else "OFF"
        status_text = "Ativado" if enabled else "Desativado"

        layer1 = "ON" if has_protected else "OFF"
        layer1_text = "ativada no grupo" if has_protected else "desativada"
        layer2 = "ON" if invite_blocked else "OFF"
        layer2_text = "membros nao podem convidar" if invite_blocked else "membros podem convidar"
        layer3 = "ON" if enabled else "OFF"
        layer3_text = "bot envia com protecao" if enabled else "desativado"
        layer4 = "ON" if enabled else "OFF"
        layer4_text = "ativa em broadcasts" if enabled else "desativada"

        text = (
            f"<b>Anti-Vazamento — {group_name}</b>\n"
            f"Status: <b>[{status_icon}] {status_text}</b>\n\n"
            f"<b>Camadas de protecao:</b>\n"
            f"[{layer1}] Protecao de conteudo (Telegram) — {layer1_text}\n"
            f"[{layer2}] Bloqueio de convites — {layer2_text}\n"
            f"[{layer3}] Mensagens protegidas — {layer3_text}\n"
            f"[{layer4}] Marca d'agua — {layer4_text}\n"
        )

        if not has_protected:
            text += (
                "\n<i>Para ativar a protecao nativa do Telegram:\n"
                "Configuracoes do grupo > Permissoes > Restringir salvar conteudo</i>\n"
            )

        btn_label = "Desativar Anti-Leak" if enabled else "Ativar Anti-Leak"
        keyboard = [[
            InlineKeyboardButton(btn_label, callback_data=f"antileak_toggle_{group.id}")
        ]]

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_antileak_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para ativar/desativar anti-leak."""
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.replace("antileak_toggle_", ""))

    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        if not group:
            await query.edit_message_text("Grupo nao encontrado.")
            return

        # Toggle
        group.anti_leak_enabled = not group.anti_leak_enabled
        enabled = group.anti_leak_enabled
        session.commit()

        group_name = escape_html(group.name)

        # Aplicar ou restaurar permissões
        try:
            if enabled:
                await enforce_antileak_permissions(context.bot, group)
            else:
                await restore_default_permissions(context.bot, group)
        except Exception as e:
            logger.warning(f"Erro ao alterar permissoes do grupo {group.id}: {e}")

        status = "ativado" if enabled else "desativado"
        btn_label = "Desativar Anti-Leak" if enabled else "Ativar Anti-Leak"

        text = (
            f"<b>Anti-Vazamento — {group_name}</b>\n\n"
            f"Anti-leak <b>{status}</b> com sucesso!\n\n"
        )

        if enabled:
            text += (
                "<b>Protecoes ativas:</b>\n"
                "- Membros nao podem convidar outros\n"
                "- Mensagens do bot protegidas contra copia\n"
                "- Marca d'agua invisivel em broadcasts\n"
                "- Forwards e links de convite detectados e removidos\n"
            )
        else:
            text += "Todas as protecoes foram desativadas.\n"

        keyboard = [[
            InlineKeyboardButton(btn_label, callback_data=f"antileak_toggle_{group.id}")
        ]]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def antileak_message_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitorar mensagens no grupo para detectar forwards e links de convite."""
    message = update.message
    if not message or not message.chat:
        return

    chat = message.chat
    if chat.type not in ['group', 'supergroup']:
        return

    with get_db_session() as session:
        group = session.query(Group).filter_by(telegram_id=str(chat.id)).first()
        if not group or not group.anti_leak_enabled:
            return
        group_name = group.name

    # Admins são isentos
    try:
        member = await context.bot.get_chat_member(chat.id, message.from_user.id)
        if member.status in ['administrator', 'creator']:
            return
    except Exception:
        return

    violations = []

    # 1. Detectar forwards
    if message.forward_from or message.forward_from_chat:
        violations.append('forward')

    # 2. Detectar links de convite Telegram
    text = message.text or message.caption or ''
    if INVITE_LINK_PATTERN.search(text):
        violations.append('invite_link')

    if not violations:
        return

    # Deletar a mensagem
    try:
        await message.delete()
    except Exception:
        pass

    # Avisar no privado
    try:
        safe_name = escape_html(group_name)
        reason_map = {
            'forward': 'encaminhamento de mensagem',
            'invite_link': 'link de convite',
        }
        reasons = ', '.join(reason_map.get(v, v) for v in violations)
        await context.bot.send_message(
            chat_id=message.from_user.id,
            text=(
                f"<b>Mensagem removida</b>\n\n"
                f"Sua mensagem em <b>{safe_name}</b> foi removida.\n"
                f"Motivo: conteudo protegido ({reasons}).\n\n"
                f"<i>Este grupo tem protecao anti-vazamento ativada.</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    logger.info(
        f"Anti-leak: mensagem removida de {message.from_user.id} "
        f"no grupo {chat.id} ({', '.join(violations)})"
    )
