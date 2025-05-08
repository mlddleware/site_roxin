def add_security_headers(response):
    """
    Добавляет заголовки безопасности к HTTP-ответу
    для защиты от различных типов атак (XSS, Clickjacking, MIME-sniffing)
    """
    # Защита от XSS
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Запрет встраивания сайта в iframe (защита от clickjacking)
    response.headers['X-Frame-Options'] = 'DENY'
    
    # Запрет определения типа контента браузером (защита от MIME-sniffing)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Обновленная политика CSP с разрешением для шрифтов Font Awesome
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data:;"
    )
    
    # Строгие HTTPS (рекомендуется только когда HTTPS настроен)
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response