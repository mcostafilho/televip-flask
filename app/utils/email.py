import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import url_for, current_app
from typing import Optional

def send_email(to_email: str, subject: str, html_body: str, text_body: Optional[str] = None):
    """Enviar email usando SMTP"""
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.hostinger.com')
    smtp_port = int(os.getenv('SMTP_PORT', '465'))
    smtp_username = os.getenv('SMTP_USERNAME', 'contato@webflag.com.br')
    smtp_password = os.getenv('SMTP_PASSWORD', '')
    from_email = os.getenv('MAIL_FROM', 'TeleVIP <contato@webflag.com.br>')

    if not smtp_password:
        print(f"[AVISO] SMTP_PASSWORD nao configurado. Email para {to_email} nao enviado.")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))

        msg.attach(MIMEText(html_body, 'html'))

        # Porta 465 = SSL direto, porta 587 = STARTTLS
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)

        print(f"[OK] Email enviado para {to_email}")
        return True

    except Exception as e:
        print(f"[ERRO] Erro ao enviar email para {to_email}: {e}")
        return False

def send_password_reset_email(user, token: str):
    """Enviar email de recuperação de senha"""
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    
    subject = "🔐 Redefinir sua senha - TeleVIP"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #7c5cfc 0%, #38bdf8 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .button {{ display: inline-block; padding: 15px 30px; background: #7c5cfc; color: white; text-decoration: none; border-radius: 25px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Redefinir Senha</h1>
            </div>
            <div class="content">
                <p>Olá <strong>{user.name}</strong>,</p>
                
                <p>Recebemos uma solicitação para redefinir a senha da sua conta TeleVIP.</p>
                
                <p>Clique no botão abaixo para criar uma nova senha:</p>
                
                <div style="text-align: center;">
                    <a href="{reset_url}" class="button">Redefinir Minha Senha</a>
                </div>
                
                <p>Ou copie e cole este link no seu navegador:</p>
                <p style="background: #e9ecef; padding: 10px; border-radius: 5px; word-break: break-all;">
                    {reset_url}
                </p>
                
                <p><strong>⚠️ Importante:</strong></p>
                <ul>
                    <li>Este link expira em 24 horas</li>
                    <li>Se você não solicitou esta alteração, ignore este email</li>
                    <li>Sua senha atual permanecerá a mesma até você criar uma nova</li>
                </ul>
            </div>
            <div class="footer">
                <p>© 2024 TeleVIP - Transforme seu Telegram em uma máquina de lucros</p>
                <p>Este é um email automático, por favor não responda.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
    Redefinir Senha - TeleVIP
    
    Olá {user.name},
    
    Recebemos uma solicitação para redefinir a senha da sua conta TeleVIP.
    
    Para criar uma nova senha, acesse o link abaixo:
    {reset_url}
    
    Este link expira em 24 horas.
    
    Se você não solicitou esta alteração, ignore este email.
    
    Atenciosamente,
    Equipe TeleVIP
    """
    
    return send_email(user.email, subject, html_body, text_body)


def send_confirmation_email(user, token: str):
    """Enviar email de confirmacao de conta"""
    confirm_url = url_for('auth.confirm_email', token=token, _external=True)

    subject = "Confirme seu email - TeleVIP"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #7c5cfc 0%, #38bdf8 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .button {{ display: inline-block; padding: 15px 30px; background: #7c5cfc; color: white; text-decoration: none; border-radius: 25px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Confirme seu Email</h1>
            </div>
            <div class="content">
                <p>Ola <strong>{user.name}</strong>,</p>

                <p>Obrigado por se cadastrar no TeleVIP! Para ativar sua conta, confirme seu email clicando no botao abaixo:</p>

                <div style="text-align: center;">
                    <a href="{confirm_url}" class="button">Confirmar Meu Email</a>
                </div>

                <p>Ou copie e cole este link no seu navegador:</p>
                <p style="background: #e9ecef; padding: 10px; border-radius: 5px; word-break: break-all;">
                    {confirm_url}
                </p>

                <p><strong>Importante:</strong></p>
                <ul>
                    <li>Este link expira em 24 horas</li>
                    <li>Se voce nao criou esta conta, ignore este email</li>
                </ul>
            </div>
            <div class="footer">
                <p>TeleVIP - Transforme seu Telegram em uma maquina de lucros</p>
                <p>Este e um email automatico, por favor nao responda.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_body = f"""
    Confirme seu Email - TeleVIP

    Ola {user.name},

    Obrigado por se cadastrar no TeleVIP! Para ativar sua conta, acesse o link abaixo:
    {confirm_url}

    Este link expira em 24 horas.

    Se voce nao criou esta conta, ignore este email.

    Atenciosamente,
    Equipe TeleVIP
    """

    return send_email(user.email, subject, html_body, text_body)


def send_welcome_email(user):
    """Enviar email de boas-vindas"""
    subject = "🎉 Bem-vindo ao TeleVIP!"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #7c5cfc 0%, #38bdf8 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .button {{ display: inline-block; padding: 15px 30px; background: #7c5cfc; color: white; text-decoration: none; border-radius: 25px; margin: 20px 0; }}
            .feature {{ margin: 15px 0; padding: 15px; background: white; border-radius: 8px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 Bem-vindo ao TeleVIP!</h1>
            </div>
            <div class="content">
                <p>Olá <strong>{user.name}</strong>,</p>
                
                <p>Parabéns! Você acaba de dar o primeiro passo para transformar seu Telegram em uma máquina de lucros! 🚀</p>
                
                <h3>🎯 Próximos Passos:</h3>
                
                <div class="feature">
                    <strong>1️⃣ Crie seu Primeiro Grupo</strong>
                    <p>Configure seu grupo VIP em menos de 2 minutos.</p>
                </div>
                
                <div class="feature">
                    <strong>2️⃣ Defina seus Planos</strong>
                    <p>Escolha preços e durações que fazem sentido para seu público.</p>
                </div>
                
                <div class="feature">
                    <strong>3️⃣ Compartilhe e Lucre</strong>
                    <p>Divulgue o link e veja o dinheiro entrar na conta!</p>
                </div>
                
                <div style="text-align: center;">
                    <a href="{url_for('dashboard.index', _external=True)}" class="button">Acessar Meu Dashboard</a>
                </div>
                
                <h3>💡 Dicas de Sucesso:</h3>
                <ul>
                    <li>Ofereça conteúdo exclusivo e de valor</li>
                    <li>Interaja com seus assinantes regularmente</li>
                    <li>Use o sistema de notificações para engajar</li>
                    <li>Acompanhe suas métricas no dashboard</li>
                </ul>
                
                <p><strong>Precisa de ajuda?</strong> Nossa equipe está sempre disponível!</p>
            </div>
            <div class="footer">
                <p>© 2024 TeleVIP - Transforme seu Telegram em uma máquina de lucros</p>
                <p>Este é um email automático, por favor não responda.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
    Bem-vindo ao TeleVIP!
    
    Olá {user.name},
    
    Parabéns! Você acaba de dar o primeiro passo para transformar seu Telegram em uma máquina de lucros!
    
    Próximos Passos:
    1. Crie seu Primeiro Grupo
    2. Defina seus Planos
    3. Compartilhe e Lucre
    
    Acesse seu dashboard: {url_for('dashboard.index', _external=True)}
    
    Atenciosamente,
    Equipe TeleVIP
    """
    
    return send_email(user.email, subject, html_body, text_body)