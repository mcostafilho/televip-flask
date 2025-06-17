#!/usr/bin/env python3
"""
Script para verificar e corrigir versão do python-telegram-bot
"""
import subprocess
import sys

def check_ptb_version():
    """Verificar versão instalada do python-telegram-bot"""
    try:
        import telegram
        version = telegram.__version__
        print(f"📦 python-telegram-bot versão: {version}")
        
        # Verificar se é versão 20.x
        major_version = int(version.split('.')[0])
        if major_version >= 20:
            print("✅ Versão compatível")
            return True
        else:
            print("⚠️  Versão antiga detectada")
            return False
            
    except ImportError:
        print("❌ python-telegram-bot não instalado")
        return False

def fix_installation():
    """Reinstalar versão correta"""
    print("\n🔧 Corrigindo instalação...\n")
    
    # Desinstalar versão atual
    print("1️⃣ Desinstalando versão atual...")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "python-telegram-bot", "-y"])
    
    # Instalar versão específica que funciona
    print("\n2️⃣ Instalando versão compatível...")
    subprocess.run([
        sys.executable, "-m", "pip", "install", 
        "python-telegram-bot==20.3"  # Versão estável conhecida
    ])
    
    print("\n✅ Instalação concluída!")

def main():
    print("""
╔══════════════════════════════════════╗
║    🔧 VERIFICAR PTB                 ║
╚══════════════════════════════════════╝
""")
    
    if not check_ptb_version():
        response = input("\nDeseja corrigir a instalação? (s/N): ")
        if response.lower() == 's':
            fix_installation()
            
            # Verificar novamente
            if check_ptb_version():
                print("\n✅ Tudo pronto! Execute:")
                print("   python bot/main_v2.py")
            else:
                print("\n❌ Ainda há problemas. Tente manualmente:")
                print("   pip install python-telegram-bot==20.3")
    else:
        print("\n✅ Versão já está correta!")
        print("\nExecute o bot:")
        print("   python bot/main_v2.py")

if __name__ == "__main__":
    main()