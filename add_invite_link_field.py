#!/usr/bin/env python3
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
