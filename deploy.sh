#!/bin/bash
# deploy.sh - Script de deploy TeleVIP para GCP VM Ubuntu 22.04
# Uso: sudo bash deploy.sh

set -e

DOMAIN="televip.app"
APP_DIR="/opt/televip"
APP_USER="televip"
REPO="https://github.com/mcostafilho/televip-flask.git"

echo "========================================="
echo "  TeleVIP Deploy - $DOMAIN"
echo "========================================="

# 1. Atualizar sistema
echo "[1/10] Atualizando sistema..."
apt update && apt upgrade -y

# 2. Instalar dependencias
echo "[2/10] Instalando dependencias..."
apt install -y python3 python3-pip python3-venv python3-dev \
    nginx certbot python3-certbot-nginx \
    git ufw fail2ban

# 3. Criar usuario da aplicacao
echo "[3/10] Criando usuario..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -d $APP_DIR -s /bin/bash $APP_USER
fi

# 4. Clonar repositorio
echo "[4/10] Clonando repositorio..."
if [ -d "$APP_DIR/app" ]; then
    cd $APP_DIR
    git pull origin main
else
    rm -rf $APP_DIR
    git clone $REPO $APP_DIR
fi
chown -R $APP_USER:$APP_USER $APP_DIR

# 5. Configurar virtualenv e dependencias
echo "[5/10] Configurando Python..."
cd $APP_DIR
sudo -u $APP_USER python3 -m venv venv
sudo -u $APP_USER $APP_DIR/venv/bin/pip install --upgrade pip
sudo -u $APP_USER $APP_DIR/venv/bin/pip install -r requirements.txt
sudo -u $APP_USER $APP_DIR/venv/bin/pip install gunicorn

# 6. Criar .env de producao
echo "[6/10] Configurando .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > $APP_DIR/.env << ENVEOF
# Flask
SECRET_KEY=$SECRET
FLASK_ENV=production
FLASK_DEBUG=false

# Banco de Dados (Cloud SQL PostgreSQL)
DATABASE_URL=postgresql://televip:SENHA@CLOUD_SQL_IP/televip

# URLs
APP_URL=https://$DOMAIN

# Telegram Bot
BOT_TOKEN=SEU_BOT_TOKEN
TELEGRAM_BOT_USERNAME=SEU_BOT_USERNAME

# Stripe
STRIPE_SECRET_KEY=SEU_STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET=

# Email SMTP
SMTP_SERVER=smtp.hostinger.com
SMTP_PORT=465
SMTP_USERNAME=SEU_EMAIL
SMTP_PASSWORD=SUA_SENHA_SMTP
MAIL_FROM=TeleVIP <SEU_EMAIL>
ENVEOF
    chown $APP_USER:$APP_USER $APP_DIR/.env
    chmod 600 $APP_DIR/.env
    echo "  -> .env criado. Verifique as credenciais!"
else
    echo "  -> .env ja existe, mantendo."
fi

# Criar diretorio instance
sudo -u $APP_USER mkdir -p $APP_DIR/instance

# Inicializar banco
cd $APP_DIR
sudo -u $APP_USER $APP_DIR/venv/bin/python -c "
from dotenv import load_dotenv
load_dotenv('$APP_DIR/.env')
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print('Banco de dados inicializado')
"

# 7. Configurar Gunicorn (systemd)
echo "[7/10] Configurando Gunicorn..."
cat > /etc/systemd/system/televip.service << 'SVCEOF'
[Unit]
Description=TeleVIP Flask App
After=network.target

[Service]
User=televip
Group=televip
WorkingDirectory=/opt/televip
Environment="PATH=/opt/televip/venv/bin"
EnvironmentFile=/opt/televip/.env
ExecStart=/opt/televip/venv/bin/gunicorn --workers 3 --bind unix:/opt/televip/televip.sock --timeout 120 "app:create_app()"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

# 8. Configurar Bot Telegram (systemd)
echo "[8/10] Configurando Bot Telegram..."
cat > /etc/systemd/system/televip-bot.service << 'BOTEOF'
[Unit]
Description=TeleVIP Telegram Bot
After=network.target televip.service

[Service]
User=televip
Group=televip
WorkingDirectory=/opt/televip
Environment="PATH=/opt/televip/venv/bin"
EnvironmentFile=/opt/televip/.env
ExecStart=/opt/televip/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
BOTEOF

# 9. Configurar Nginx
echo "[9/10] Configurando Nginx..."
cat > /etc/nginx/sites-available/televip << NGXEOF
server {
    listen 80;
    server_name $DOMAIN;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css text/xml application/json application/javascript text/javascript;
    gzip_comp_level 6;
    gzip_min_length 1000;
    gzip_proxied any;
    gzip_vary on;

    location / {
        proxy_pass http://unix:/opt/televip/televip.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /static {
        alias /opt/televip/app/static;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
NGXEOF

ln -sf /etc/nginx/sites-available/televip /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 10. Firewall + SSL + Iniciar servicos
echo "[10/10] Finalizando..."

# Firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# Configurar Fail2ban
echo "Configurando Fail2ban..."
cat > /etc/fail2ban/jail.local << 'F2BEOF'
[sshd]
enabled = true
maxretry = 5

[nginx-limit-req]
enabled = true
maxretry = 10
findtime = 600
bantime = 3600
logpath = /var/log/nginx/error.log
F2BEOF

systemctl enable fail2ban
systemctl restart fail2ban

# Backup automatico do .env e configs criticos
echo "Configurando backup semanal..."
BACKUP_DIR="/opt/televip/backups"
mkdir -p $BACKUP_DIR
chown $APP_USER:$APP_USER $BACKUP_DIR

cat > /opt/televip/backup.sh << 'BKPEOF'
#!/bin/bash
BACKUP_DIR="/opt/televip/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
tar czf "$BACKUP_DIR/televip_config_$TIMESTAMP.tar.gz" \
    /opt/televip/.env \
    /etc/nginx/sites-available/televip \
    /etc/systemd/system/televip.service \
    /etc/systemd/system/televip-bot.service \
    /etc/fail2ban/jail.local \
    2>/dev/null
# Manter apenas os ultimos 4 backups
ls -t "$BACKUP_DIR"/televip_config_*.tar.gz | tail -n +5 | xargs -r rm
BKPEOF

chmod +x /opt/televip/backup.sh
chown $APP_USER:$APP_USER /opt/televip/backup.sh

# Cron semanal (domingo 3h)
(crontab -u $APP_USER -l 2>/dev/null | grep -v backup.sh; echo "0 3 * * 0 /opt/televip/backup.sh") | crontab -u $APP_USER -

# Iniciar servicos
systemctl daemon-reload
systemctl enable televip televip-bot
systemctl start televip
systemctl start televip-bot

echo ""
echo "========================================="
echo "  Deploy concluido!"
echo "========================================="
echo ""
echo "Agora execute o SSL (depois do DNS propagar):"
echo "  sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m contato@webflag.com.br"
echo ""
echo "Comandos uteis:"
echo "  sudo systemctl status televip        # Status da app"
echo "  sudo systemctl status televip-bot    # Status do bot"
echo "  sudo journalctl -u televip -f        # Logs da app"
echo "  sudo journalctl -u televip-bot -f    # Logs do bot"
echo "  sudo systemctl restart televip       # Reiniciar app"
echo ""
echo "Acesse: http://$DOMAIN"
echo "Apos SSL: https://$DOMAIN"
