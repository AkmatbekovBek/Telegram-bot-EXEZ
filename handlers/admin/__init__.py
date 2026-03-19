"""
Инициализация админских обработчиков
"""
from .link_texts_admin import register_link_texts_admin
from .user_data_display import register_user_info_handlers

try:
    from .main_admin_handler import register_admin_handlers
    from .mute_ban import register_handlers as register_mute_ban_handlers
    from .cleanup_handler import register_cleanup_handlers
    from .donate_texts_admin import register_donate_texts_admin

    # Экспортируем функции напрямую
    register_admin_handlers = register_admin_handlers
    register_mute_ban_handlers = register_mute_ban_handlers
    register_cleanup_handlers = register_cleanup_handlers
    register_donate_texts_admin = register_donate_texts_admin
    register_link_texts_admin = register_link_texts_admin
    __all__ = [
        'register_admin_handlers',
        'register_mute_ban_handlers',
        'register_cleanup_handlers',
        'register_user_info_handlers',
        'register_donate_texts_admin'

    ]


    def register_all_admin_handlers(dp):
        """Регистрирует ВСЕ админские обработчики"""
        register_admin_handlers(dp)
        register_mute_ban_handlers(dp)
        register_user_info_handlers(dp)
        register_cleanup_handlers(dp)
        register_donate_texts_admin(dp)
        register_link_texts_admin(dp)
        print("✅ Все админские обработчики зарегистрированы")

except ImportError as e:
    print(f"Warning: Could not import admin handlers: {e}")
    __all__ = []