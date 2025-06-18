#!/usr/bin/env python3
"""
Script para ativar e verificar o sistema de pagamentos
Execute: python fix_payment_system.py
"""
import os
import sys
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def check_stripe_config():
    """Verificar configuração do Stripe"""
    print("🔍 Verificando configuração do Stripe...")
    print("=" * 50)
    
    # Verificar chaves do Stripe
    stripe_secret = os.getenv('STRIPE_SECRET_KEY')
    stripe_webhook = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    issues = []
    
    if not stripe_secret:
        issues.append("❌ STRIPE_SECRET_KEY não configurada")
    else:
        if stripe_secret.startswith('sk_test_'):
            print("✅ STRIPE_SECRET_KEY configurada (modo TESTE)")
        elif stripe_secret.startswith('sk_live_'):
            print("✅ STRIPE_SECRET_KEY configurada (modo PRODUÇÃO)")
        else:
            issues.append("⚠️  STRIPE_SECRET_KEY com formato inválido")
    
    if not stripe_webhook:
        issues.append("⚠️  STRIPE_WEBHOOK_SECRET não configurada (opcional mas recomendada)")
    else:
        print("✅ STRIPE_WEBHOOK_SECRET configurada")
    
    # Verificar outras configs necessárias
    bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME')
    
    if not bot_token:
        issues.append("❌ BOT_TOKEN não configurado")
    else:
        print("✅ BOT_TOKEN configurado")
    
    if not bot_username:
        issues.append("⚠️  TELEGRAM_BOT_USERNAME não configurado (recomendado)")
    else:
        print(f"✅ TELEGRAM_BOT_USERNAME: @{bot_username}")
    
    return issues

def update_payment_handler():
    """Atualizar o handler de pagamento para funcionar corretamente"""
    print("\n📝 Verificando handler de pagamento...")
    
    handler_path = "bot/handlers/payment.py"
    
    if not os.path.exists(handler_path):
        print(f"❌ Arquivo {handler_path} não encontrado!")
        return False
    
    # Ler o arquivo atual
    with open(handler_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificar se está mostrando "em desenvolvimento"
    if '"🚧 Sistema de pagamento em desenvolvimento"' in content:
        print("❌ Handler ainda mostra 'em desenvolvimento'")
        print("✅ O código correto já existe no arquivo!")
        print("\n⚠️  AÇÃO NECESSÁRIA:")
        print("1. Abra o arquivo: bot/handlers/payment.py")
        print("2. Procure a função 'handle_payment_method'")
        print("3. Verifique se está chamando 'process_stripe_payment' corretamente")
        return False
    else:
        print("✅ Handler de pagamento parece estar correto")
        return True

def create_env_example():
    """Criar arquivo .env.example atualizado"""
    print("\n📄 Criando .env.example atualizado...")
    
    env_example = """# Configurações do Bot Telegram
BOT_TOKEN=seu_bot_token_aqui
TELEGRAM_BOT_USERNAME=seu_bot_username_aqui

# Configurações do Stripe
STRIPE_SECRET_KEY=sk_test_... # Obtenha em https://dashboard.stripe.com/apikeys
STRIPE_WEBHOOK_SECRET=whsec_... # Opcional, configure webhook em https://dashboard.stripe.com/webhooks

# Banco de Dados
DATABASE_URL=sqlite:///instance/televip.db

# Flask
SECRET_KEY=sua-chave-secreta-aqui
FLASK_ENV=development

# URLs da aplicação
APP_URL=http://localhost:5000
"""
    
    with open('.env.example', 'w', encoding='utf-8') as f:
        f.write(env_example)
    
    print("✅ Arquivo .env.example criado/atualizado")

def show_stripe_setup_guide():
    """Mostrar guia de configuração do Stripe"""
    print("\n📚 GUIA DE CONFIGURAÇÃO DO STRIPE")
    print("=" * 50)
    print("""
1. CRIAR CONTA NO STRIPE:
   - Acesse: https://dashboard.stripe.com/register
   - Complete o cadastro

2. OBTER CHAVES API:
   - Acesse: https://dashboard.stripe.com/test/apikeys
   - Copie a "Secret key" (começa com sk_test_...)
   - Cole no .env como STRIPE_SECRET_KEY

3. CONFIGURAR WEBHOOK (Opcional mas recomendado):
   - Acesse: https://dashboard.stripe.com/test/webhooks
   - Clique em "Add endpoint"
   - URL: http://seu-dominio.com/webhooks/stripe
   - Eventos: checkout.session.completed, payment_intent.succeeded
   - Copie o "Signing secret" (começa com whsec_...)
   - Cole no .env como STRIPE_WEBHOOK_SECRET

4. TESTAR LOCALMENTE:
   - Use o Stripe CLI: https://stripe.com/docs/stripe-cli
   - Comando: stripe listen --forward-to localhost:5000/webhooks/stripe

5. MODO PRODUÇÃO:
   - Troque sk_test_ por sk_live_ quando estiver pronto
   - Configure webhook com URL real do servidor
""")

def test_stripe_connection():
    """Testar conexão com Stripe"""
    print("\n🧪 Testando conexão com Stripe...")
    
    try:
        import stripe
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        
        if not stripe.api_key:
            print("❌ Não foi possível testar - STRIPE_SECRET_KEY não configurada")
            return False
        
        # Tentar listar produtos (teste simples)
        stripe.Product.list(limit=1)
        print("✅ Conexão com Stripe funcionando!")
        return True
        
    except ImportError:
        print("❌ Biblioteca stripe não instalada. Execute: pip install stripe")
        return False
    except stripe.error.AuthenticationError:
        print("❌ Chave do Stripe inválida. Verifique STRIPE_SECRET_KEY")
        return False
    except Exception as e:
        print(f"❌ Erro ao conectar com Stripe: {e}")
        return False

def main():
    """Função principal"""
    print("🚀 ATIVAÇÃO DO SISTEMA DE PAGAMENTOS TELEVIP")
    print("=" * 50)
    
    # 1. Verificar configuração
    issues = check_stripe_config()
    
    # 2. Verificar handler
    handler_ok = update_payment_handler()
    
    # 3. Criar .env.example
    create_env_example()
    
    # 4. Testar conexão
    if not issues or (len(issues) == 1 and 'WEBHOOK' in issues[0]):
        stripe_ok = test_stripe_connection()
    else:
        stripe_ok = False
    
    # 5. Resumo final
    print("\n📊 RESUMO FINAL")
    print("=" * 50)
    
    if issues:
        print("\n⚠️  PROBLEMAS ENCONTRADOS:")
        for issue in issues:
            print(f"  {issue}")
        
        print("\n💡 SOLUÇÕES:")
        if any('STRIPE_SECRET_KEY' in i for i in issues):
            print("  1. Configure STRIPE_SECRET_KEY no arquivo .env")
            show_stripe_setup_guide()
    else:
        print("✅ Todas as configurações essenciais estão OK!")
    
    if handler_ok and stripe_ok and not any('STRIPE_SECRET_KEY' in i for i in issues):
        print("\n🎉 SISTEMA DE PAGAMENTOS PRONTO PARA USO!")
        print("\nPRÓXIMOS PASSOS:")
        print("1. Reinicie o bot: python bot.py")
        print("2. Teste um pagamento no bot")
        print("3. Verifique no dashboard do Stripe")
    else:
        print("\n❌ Sistema ainda precisa de configuração")
        print("\nACÕES NECESSÁRIAS:")
        print("1. Configure as variáveis faltantes no .env")
        print("2. Execute este script novamente")
        print("3. Reinicie o bot quando tudo estiver OK")

if __name__ == "__main__":
    main()