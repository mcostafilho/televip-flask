def test_app_exists():
    """Testa se a aplicação pode ser criada"""
    from app import create_app
    app = create_app()
    assert app is not None
