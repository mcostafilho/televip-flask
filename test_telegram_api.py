#!/usr/bin/env python3
"""
Script para testar a API do Telegram e verificar problemas
Execute: python test_telegram_api.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_telegram_api():
    """Testar conexão com API do Telegram"""
    print("🔍 Testando API do Telegram...\n")
    
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        print("❌ BOT_TOKEN não encontrado no .env!")
        return
    
    print(f"📱 Token do bot: {bot_token[:10]}...{bot_token[-5:]}")
    
    # 1. Testar getMe
    print("\n1️⃣ Testando getMe (informações do bot)...")
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data['result']
                print(f"   ✅ Bot: @{bot_info.get('username')}")
                print(f"   Nome: {bot_info.get('first_name')}")
                print(f"   ID: {bot_info.get('id')}")
            else:
                print(f"   ❌ Erro: {data.get('description')}")
        else:
            print(f"   ❌ Erro HTTP: {response.status_code}")
            print(f"   Resposta: {response.text}")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
    
    # 2. Pedir ID do grupo para testar
    print("\n2️⃣ Testar verificação de grupo")
    print("   Para obter o ID do grupo:")
    print("   1. Adicione o bot ao grupo")
    print("   2. Promova o bot a administrador")
    print("   3. Envie /setup no grupo")
    print("   4. O bot responderá com o ID\n")
    
    group_id = input("Digite o ID do grupo (ou ENTER para pular): ").strip()
    
    if group_id:
        print(f"\n🔍 Verificando grupo {group_id}...")
        
        # Testar getChat
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getChat",
                params={"chat_id": group_id}
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    chat = data['result']
                    print(f"   ✅ Grupo encontrado!")
                    print(f"   Nome: {chat.get('title')}")
                    print(f"   Tipo: {chat.get('type')}")
                    print(f"   ID: {chat.get('id')}")
                    
                    # Verificar se o bot é admin
                    print("\n   🔍 Verificando se o bot é admin...")
                    bot_id = bot_token.split(':')[0]
                    
                    member_response = requests.get(
                        f"https://api.telegram.org/bot{bot_token}/getChatMember",
                        params={
                            "chat_id": group_id,
                            "user_id": bot_id
                        }
                    )
                    
                    if member_response.status_code == 200:
                        member_data = member_response.json()
                        if member_data.get('ok'):
                            member = member_data['result']
                            status = member.get('status')
                            print(f"   Status do bot: {status}")
                            
                            if status in ['administrator', 'creator']:
                                print("   ✅ Bot é administrador!")
                            else:
                                print("   ❌ Bot NÃO é administrador!")
                                print("   ⚠️  Promova o bot a admin no grupo")
                else:
                    print(f"   ❌ Erro: {data.get('description')}")
            else:
                print(f"   ❌ Erro HTTP: {response.status_code}")
                print(f"   Resposta: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Erro ao verificar grupo: {e}")
            import traceback
            traceback.print_exc()

def create_debug_route():
    """Criar rota de debug temporária"""
    print("\n📝 Criando correção temporária...")
    
    code = '''# Adicione esta rota temporariamente em app/routes/groups.py para debug

@bp.route('/test-telegram')
@login_required
def test_telegram():
    """Rota de teste para verificar conexão com Telegram"""
    import requests
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        return jsonify({"error": "BOT_TOKEN não configurado"}), 500
    
    try:
        # Testar API
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe")
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "success": True,
                "bot_info": data.get('result'),
                "message": "Bot conectado com sucesso!"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Erro HTTP: {response.status_code}",
                "details": response.text
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })
'''
    
    print(code)

def suggest_fix():
    """Sugerir correção para o problema"""
    print("\n💡 POSSÍVEIS SOLUÇÕES:\n")
    
    print("1. Verifique o BOT_TOKEN no arquivo .env:")
    print("   - Certifique-se que está correto")
    print("   - Não deve ter espaços extras")
    print("   - Formato: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
    
    print("\n2. Verifique se o bot está ativo:")
    print("   - Abra o Telegram")
    print("   - Procure seu bot")
    print("   - Envie /start")
    print("   - Se não responder, pode estar inativo")
    
    print("\n3. Para criar grupo SEM verificação do Telegram:")
    print("   - Comente temporariamente a verificação")
    print("   - Ou use um ID de grupo fictício como: -1001234567890")
    
    print("\n4. Se o erro persistir, modifique temporariamente app/routes/groups.py:")
    print("   - Na função create(), comente a seção de validação do Telegram")
    print("   - Linha ~30 até ~60 aproximadamente")

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════╗
║   🔍 Teste de API do Telegram        ║
╚══════════════════════════════════════╝
    """)
    
    test_telegram_api()
    
    print("\n" + "="*50)
    suggest_fix()
    
    if input("\n❓ Ver código de debug? (s/n): ").lower() == 's':
        create_debug_route()