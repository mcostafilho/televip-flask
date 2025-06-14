#!/usr/bin/env python3
"""
Script de configuração do Bot TeleVIP
Execute: python setup_bot.py
"""
import os
import sys
from dotenv import load_dotenv

def check_requirements():
    """Verificar se todos os requisitos estão instalados"""
    print("🔍 Verificando requisitos...")
    
    required_packages = [
        'telegram',
        'sqlalchemy',
        'dotenv',
        'qrcode',
        'PIL',
        'stripe'
    ]
    
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"❌ Pacotes faltando: {', '.join(missing)}")
        print("\nInstale com: pip install -r bot/requirements.txt")
        return False
    
    print("✅ Todos os requisitos instalados!")
    return True

def check_env_vars():
    """Verificar variáveis de ambiente necessárias"""
    load_dotenv()
    
    print("\n🔍 Verificando variáveis de ambiente...")
    
    required_vars = {
        'BOT_TOKEN': 'Token do bot do Telegram',
        'BOT_USERNAME': 'Username do bot (sem @)',
        'DATABASE_URL': 'URL do banco de dados',
        'STRIPE_SECRET_KEY': 'Chave secreta do Stripe'
    }
    
    missing = []
    
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"{var} ({description})")
    
    if missing:
        print("❌ Variáveis faltando no .env:")
        for var in missing:
            print(f"  • {var}")
        print("\nConfigure estas variáveis no arquivo .env")
        return False
    
    print("✅ Todas as variáveis configuradas!")
    return True

def create_bot_structure():
    """Criar estrutura de arquivos do bot se não existir"""
    print("\n📁 Verificando estrutura de arquivos...")
    
    # Arquivos que devem existir
    files_to_create = {
        'bot/__init__.py': '',
        'bot/handlers/__init__.py': '',
        'bot/keyboards/__init__.py': '',
        'bot/utils/__init__.py': '',
        'bot/utils/stripe_integration.py': '''"""
Integração com Stripe para o bot
"""
import os
import stripe
from typing import Dict

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def create_checkout_session(
    amount: float,
    group_name: str,
    plan_name: str,
    user_id: str,
    success_url: str,
    cancel_url: str
) -> Dict:
    """Criar sessão de checkout no Stripe"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'brl',
                    'product_data': {
                        'name': f'{group_name} - {plan_name}',
                        'description': f'Assinatura do grupo {group_name}'
                    },
                    'unit_amount': int(amount * 100),  # Stripe usa centavos
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'group_name': group_name,
                'plan_name': plan_name
            }
        )
        
        return {
            'success': True,
            'session_id': session.id,
            'url': session.url
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

async def verify_payment(session_id: str) -> bool:
    """Verificar se pagamento foi completado"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == 'paid'
    except:
        return False
''',
    }
    
    created = 0
    for filepath, content in files_to_create.items():
        if not os.path.exists(filepath):
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            created += 1
            print(f"✅ Criado: {filepath}")
    
    if created == 0:
        print("✅ Todos os arquivos já existem!")
    else:
        print(f"✅ {created} arquivos criados!")
    
    return True

def test_bot_connection():
    """Testar conexão com o Telegram"""
    print("\n🤖 Testando conexão com Telegram...")
    
    try:
        import asyncio
        from telegram import Bot
        
        async def test():
            bot = Bot(token=os.getenv('BOT_TOKEN'))
            me = await bot.get_me()
            print(f"✅ Bot conectado: @{me.username}")
            print(f"   Nome: {me.first_name}")
            print(f"   ID: {me.id}")
            return True
        
        return asyncio.run(test())
        
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        return False

def main():
    """Função principal"""
    print("🚀 Setup do Bot TeleVIP\n")
    
    # Verificar se está no diretório correto
    if not os.path.exists('app') or not os.path.exists('bot'):
        print("❌ Execute este script no diretório raiz do projeto!")
        sys.exit(1)
    
    # Executar verificações
    checks = [
        ("Requisitos", check_requirements),
        ("Variáveis de Ambiente", check_env_vars),
        ("Estrutura de Arquivos", create_bot_structure),
        ("Conexão com Telegram", test_bot_connection)
    ]
    
    all_passed = True
    
    for name, check_func in checks:
        if not check_func():
            all_passed = False
            break
    
    print("\n" + "="*50)
    
    if all_passed:
        print("✅ Bot configurado com sucesso!")
        print("\n📋 Próximos passos:")
        print("1. Execute o bot: python bot/main.py")
        print("2. Configure grupos usando /setup dentro do grupo")
        print("3. Compartilhe o link do bot com os assinantes")
    else:
        print("❌ Configuração incompleta!")
        print("\nResolva os problemas acima e execute novamente.")
        sys.exit(1)

if __name__ == "__main__":
    main()