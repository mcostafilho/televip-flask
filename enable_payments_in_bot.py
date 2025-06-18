#!/usr/bin/env python3
"""
Script para habilitar o bot a criar links de convite automaticamente
Execute: python enable_bot_invite_links.py
"""
import os
import shutil
from datetime import datetime

def update_payment_verification():
    """Atualizar payment_verification.py para criar links automaticamente"""
    print("🔧 Atualizando sistema para criar links automaticamente...")
    print("=" * 50)
    
    verification_file = "bot/handlers/payment_verification.py"
    
    if not os.path.exists(verification_file):
        print(f"❌ Arquivo {verification_file} não encontrado!")
        return False
    
    # Fazer backup
    backup_file = f"{verification_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"📋 Criando backup: {backup_file}")
    shutil.copy2(verification_file, backup_file)
    
    # Ler conteúdo atual
    with open(verification_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Encontrar a função handle_payment_confirmed
    if 'async def handle_payment_confirmed' in content:
        print("📝 Atualizando função handle_payment_confirmed...")
        
        # Novo código para a função
        new_function = '''async def handle_payment_confirmed(query, context, transaction, db_session):
    """Processar pagamento confirmado - COM CRIAÇÃO AUTOMÁTICA DE LINK"""
    logger.info(f"Pagamento confirmado para transação {transaction.id}")
    
    # Atualizar transação
    transaction.status = 'completed'
    transaction.paid_at = datetime.utcnow()
    
    # Ativar assinatura
    subscription = transaction.subscription
    subscription.status = 'active'
    
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
        logger.warning(f"⚠️ Não foi possível enviar acesso para usuário {user.id}")'''
        
        # Encontrar e substituir a função
        import re
        pattern = r'async def handle_payment_confirmed\(.*?\):\s*""".*?""".*?(?=\n\nasync def|\n\n#|\Z)'
        
        # Se encontrar, substituir
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, new_function, content, flags=re.DOTALL)
            print("✅ Função atualizada com sucesso!")
        else:
            # Adicionar no final se não encontrar
            print("📝 Adicionando função ao final do arquivo...")
            content = content.rstrip() + '\n\n\n' + new_function + '\n'
        
        # Garantir imports necessários
        if 'from datetime import datetime, timedelta' not in content:
            content = content.replace(
                'from datetime import datetime',
                'from datetime import datetime, timedelta'
            )
        
        # Salvar arquivo atualizado
        with open(verification_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Arquivo atualizado com sucesso!")
        return True
    
    else:
        print("❌ Função handle_payment_confirmed não encontrada!")
        return False

def add_invite_link_field():
    """Adicionar campo invite_link_used nas subscriptions"""
    print("\n🔧 Verificando campo invite_link_used...")
    
    migration_script = '''#!/usr/bin/env python3
"""Adicionar campo invite_link_used"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db

app = create_app()
with app.app_context():
    try:
        db.engine.execute('ALTER TABLE subscriptions ADD COLUMN invite_link_used VARCHAR(200)')
        print("✅ Campo invite_link_used adicionado!")
    except:
        print("ℹ️ Campo já existe ou erro ao adicionar")
'''
    
    with open('add_invite_link_field.py', 'w', encoding='utf-8') as f:
        f.write(migration_script)
    
    print("✅ Script de migração criado: add_invite_link_field.py")
    print("   Execute se necessário: python add_invite_link_field.py")

def create_bot_setup_instructions():
    """Criar instruções detalhadas para configurar o bot como admin"""
    instructions = '''CONFIGURAÇÃO DO BOT COMO ADMINISTRADOR
======================================

Para o bot criar links automaticamente, ele PRECISA ser administrador do grupo.

1. ADICIONAR O BOT COMO ADMIN:
   ✅ Abra o grupo no Telegram
   ✅ Toque no nome do grupo (no topo)
   ✅ Toque em "Administradores" ou "Admins"
   ✅ Toque em "Adicionar Administrador"
   ✅ Procure por: @televipbra_bot
   ✅ Adicione o bot

2. PERMISSÕES NECESSÁRIAS (marque estas):
   ✅ Adicionar novos membros (OBRIGATÓRIA)
   ✅ Convidar usuários via link (OBRIGATÓRIA)
   ✅ Excluir mensagens (opcional)
   ✅ Banir usuários (opcional)

3. TESTAR SE FUNCIONOU:
   No grupo, envie: /setup
   O bot deve responder com as informações do grupo

4. FLUXO APÓS PAGAMENTO:
   
   Quando alguém pagar, o bot vai:
   
   a) Tentar adicionar a pessoa diretamente ao grupo
      - Funciona se a pessoa já iniciou conversa com o bot
      - É instantâneo
   
   b) Se não conseguir, criar um link único:
      - Válido para 1 pessoa apenas
      - Expira em 7 dias
      - Uso único (mais seguro)

5. VANTAGENS DO BOT COMO ADMIN:
   ✅ Links únicos por pessoa (mais seguro)
   ✅ Controle de quem entra
   ✅ Pode remover automaticamente quem não pagou
   ✅ Estatísticas de membros
   ✅ Adiciona pessoas instantaneamente

6. SE O BOT NÃO FOR ADMIN:
   ❌ Não consegue criar links
   ❌ Não consegue adicionar pessoas
   ❌ Você terá que enviar links manualmente

PROBLEMAS COMUNS:
================

"Bot can't initiate conversation with a user"
- Normal, o bot cria um link ao invés de adicionar direto

"Not enough rights to invite users"
- Bot não tem permissão de admin
- Verifique as permissões

"Chat not found"
- ID do grupo está errado
- Use /setup no grupo para pegar o ID correto

COMANDO /setup:
==============
Envie /setup no seu grupo para o bot mostrar:
- ID do grupo
- Se ele é admin
- Quantos membros tem
- Se está tudo configurado
'''
    
    with open('bot_admin_setup_guide.txt', 'w', encoding='utf-8') as f:
        f.write(instructions)
    
    print("\n📋 Guia criado: bot_admin_setup_guide.txt")

def main():
    """Função principal"""
    print("🚀 HABILITANDO BOT PARA CRIAR LINKS AUTOMATICAMENTE")
    print("=" * 50)
    
    # 1. Atualizar código
    code_ok = update_payment_verification()
    
    # 2. Criar script de migração
    add_invite_link_field()
    
    # 3. Criar guia
    create_bot_setup_instructions()
    
    # Resumo
    print("\n📊 RESUMO")
    print("=" * 50)
    
    if code_ok:
        print("✅ Sistema atualizado com sucesso!")
        print("\n🎯 O QUE FOI IMPLEMENTADO:")
        print("1. Bot tenta adicionar usuário diretamente ao grupo")
        print("2. Se não conseguir, cria link único de convite")
        print("3. Link válido para 1 pessoa por 7 dias")
        print("4. Fallback para links manuais se necessário")
        
        print("\n📋 PRÓXIMOS PASSOS:")
        print("1. Torne o bot ADMIN em seus grupos")
        print("2. Dê permissão de 'Adicionar membros'")
        print("3. Teste com /setup no grupo")
        print("4. Reinicie o bot: python bot.py")
        print("5. Faça um teste de pagamento")
        
        print("\n⚠️ IMPORTANTE:")
        print("- O bot PRECISA ser admin do grupo")
        print("- Veja o guia: bot_admin_setup_guide.txt")
    else:
        print("❌ Houve problemas na atualização")
        print("Verifique os arquivos manualmente")

if __name__ == "__main__":
    main()