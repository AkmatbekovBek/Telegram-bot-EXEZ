# handlers/roulette/__init__.py
from .admin_commands import register_roulette_admin_commands
from .handlers import RouletteHandler, register_roulette_handlers


# Функция для регистрации ВСЕХ обработчиков рулетки
def register_all_roulette_handlers(dp):
    """Регистрирует все обработчики рулетки (основные + команды управления)"""
    # 1. Регистрируем основные обработчики рулетки
    handler = register_roulette_handlers(dp)

    # 2. Регистрируем команды управления рулеткой (!ron, !roff, !rstatus)
    register_roulette_admin_commands(dp)

    return handler


__all__ = [
    "RouletteHandler",
    "register_roulette_handlers",
    "register_roulette_admin_commands",
    "register_all_roulette_handlers"  # Добавьте эту строку
]