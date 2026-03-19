# middlewares/roulette_state_middleware.py
import logging
import re
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler

from handlers.roulette.state_manager import state_manager

logger = logging.getLogger(__name__)


class RouletteStateMiddleware(BaseMiddleware):
    """Middleware для проверки состояния рулетки (включена/выключена) по чатам"""

    async def on_pre_process_message(self, message: types.Message, data: dict):
        # Проверяем только текстовые сообщения
        if not message.text:
            return

        text = message.text.lower().strip()

        # Пропускаем команды управления рулеткой
        management_commands = ['!ron', '!roff', '!rstatus']
        if any(text.startswith(cmd) for cmd in management_commands):
            return

        # Пропускаем команды, не связанные с игрой в рулетку
        balance_commands = ['б', 'баланс', 'balance']
        other_commands = ['отмена', 'очистить', 'clear', 'ставки', 'мои ставки', 'bets', 'лог', '!лог', 'лимиты',
                          'лимит', 'limits']

        if text in balance_commands or text in other_commands:
            return

        # Если рулетка включена - пропускаем все
        if state_manager.is_roulette_enabled(message.chat.id):
            return

        # Если рулетка ОТКЛЮЧЕНА, проверяем ставки и игровые действия

        # 1. Проверяем ставки типа "1000 к", "2000 ч", "500 з"
        bet_short_pattern = r'^\d+\s*[кk]?\s+[кчзкрчр]'
        if re.search(bet_short_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 2. Проверяем ставки типа "1000 на красное"
        bet_full_pattern = r'^\d+\s*[кk]?\s+на\s+'
        if re.search(bet_full_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 3. Проверяем числовые ставки (форматы: "1000 4", "4000 12", "500 0")
        # Паттерн для: число (с возможным "к" или "k") пробел число
        numeric_bet_pattern = r'^\d+\s*[кk]?\s+\d+$'
        if re.match(numeric_bet_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 4. Проверяем диапазонные ставки (форматы: "1000 1-4", "5000 10-20", "300 0-3")
        # Паттерн для: число (с возможным "к" или "k") пробел число-число
        range_bet_pattern = r'^\d+\s*[кk]?\s+\d+\s*-\s*\d+$'
        if re.match(range_bet_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 5. Проверяем вабанк с одним числом (форматы: "вабанк 1", "вабанк 12", "вабанк 0")
        vabank_single_number_pattern = r'^ва[-\s]?банк\s+\d+$'
        if re.match(vabank_single_number_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 6. Проверяем вабанк с диапазоном (форматы: "вабанк 1-4", "вабанк 10-20")
        vabank_single_range_pattern = r'^ва[-\s]?банк\s+\d+\s*-\s*\d+$'
        if re.match(vabank_single_range_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 7. Проверяем вабанк без указания суммы (форматы: "вабанк к", "вабанк ч", "вабанк з")
        vabank_short_pattern = r'^ва[-\s]?банк\s+[кчзкрчр]$'
        if re.match(vabank_short_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 8. Проверяем вабанк на число (форматы: "вабанк на 4", "вабанк на 12", "вабанк на 0")
        vabank_numeric_pattern = r'^ва[-\s]?банк\s+на\s+\d+$'
        if re.match(vabank_numeric_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 9. Проверяем вабанк на диапазон (форматы: "вабанк на 1-4", "вабанк на 10-20")
        vabank_range_pattern = r'^ва[-\s]?банк\s+на\s+\d+\s*-\s*\d+$'
        if re.match(vabank_range_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 10. Проверяем вабанк на цвет (форматы: "вабанк на красное", "вабанк на черное", "вабанк на зеленое")
        vabank_color_pattern = r'^ва[-\s]?банк\s+на\s+(красн|черн|зелен)'
        if re.match(vabank_color_pattern, text, re.IGNORECASE):
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        # 11. Проверяем простые команды начала игры
        game_commands = ['го', 'крутить', 'spin']

        # Отдельно обрабатываем "рулетка" - это начало игры, но также может быть просто командой
        if text == 'рулетка':
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

        if text in game_commands:
            await message.answer("❌ Рулетка отключена в этом чате")
            raise CancelHandler()

    async def on_pre_process_callback_query(self, callback_query: types.CallbackQuery, data: dict):
        """Проверяем колбэки рулетки"""
        if not callback_query.data:
            return

        # Если рулетка включена - пропускаем все
        if state_manager.is_roulette_enabled(callback_query.message.chat.id):
            return

        # Проверяем, является ли колбэк от рулетки
        is_roulette_callback = any(
            callback_query.data.startswith(prefix)
            for prefix in ['bet:', 'quick:', 'action:spin', 'action:repeat', 'action:double']
        )

        # Проверяем старые форматы callback
        if not is_roulette_callback:
            is_roulette_callback = any(
                callback_query.data.startswith(prefix)
                for prefix in ['bet_', 'quick_', 'repeat', 'double', 'spin']
            )

        if is_roulette_callback:
            try:
                await callback_query.answer("❌ Рулетка отключена в этом чате", show_alert=True)
            except Exception as e:
                logger.debug(f"Ошибка при ответе на колбэк: {e}")

            raise CancelHandler()