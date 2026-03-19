# handlers/police/__init__.py
"""
Модуль полицейских команд для бота
Обработка арестов, проверок статуса и управления полицейскими функциями
"""

from .handlers import register_police_handlers, PoliceHandlers
from .service import PoliceService

__all__ = [
    'register_police_handlers',
    'PoliceHandlers', 
    'PoliceService'
]