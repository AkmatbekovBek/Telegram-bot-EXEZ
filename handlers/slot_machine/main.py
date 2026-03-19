# handlers/slot_machine/main
import logging
from aiogram import Dispatcher
from .game_logic import SlotGameLogic
from .handlers import SlotMessageHandlers

logger = logging.getLogger(__name__)


def register_slot_handlers(dp: Dispatcher):
    """Регистрация обработчиков игрового автомата"""
    # Инициализация компонентов
    game_logic = SlotGameLogic()
    message_handlers = SlotMessageHandlers(game_logic)

    # Регистрация справки по командам
    dp.register_message_handler(
        message_handlers.slot_help,
        commands=["slot", "slots", "автомат", "слот", "слоты"],
        state="*"
    )

    # Регистрация справки по текстовым запросам (без чисел)
    dp.register_message_handler(
        message_handlers.slot_help,
        lambda m: m.text and m.text.lower().strip() in [
            "слот", "автомат", "slot", "slots",
            "игровой автомат", "игровой слот",
            "слоты", "автоматы"
        ],
        state="*"
    )

    # Регистрация игровых команд (только с числами)
    dp.register_message_handler(
        message_handlers.slot_game_handler,
        lambda m: m.text and any(char.isdigit() for char in m.text) and (
            m.text.lower().startswith(('слот ', 'автомат ', 'slot ', 'slots ', 'игра ')) or
            m.text.lower().startswith(('/слот ', '/автомат ', '/slot ', '/slots ')) or
            'игровой автомат ' in m.text.lower() or
            'игровой слот ' in m.text.lower()
        ),
        state="*"
    )

    logging.info("✅ Игра 'Игровой автомат' зарегистрирована (только текстовая версия)")