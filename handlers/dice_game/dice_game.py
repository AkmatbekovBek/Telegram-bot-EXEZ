# handlers/dice_game.py (исправленная версия)

import logging
import asyncio
import random
import re
from typing import Tuple
from aiogram import types, Dispatcher
from database import get_db
from database.crud import UserRepository, TransactionRepository
from contextlib import contextmanager
from config import bot

logger = logging.getLogger(__name__)

# Конфигурация игры
DICE_GAME_CONFIG = {
    'bet_min': 1000,
    'bet_max': 100000000,
    'multiplier': 6,
    'throttle_time': 2
}

# СТИКЕРЫ КУБИКОВ
DICE_STICKERS = {
    1: "CAACAgEAAxkBAAEUPURpKCDg7xC89apo4RPYwnAcrgf2pwACfw4AAoI0egGMUY9GQldDATYE",
    2: "CAACAgEAAxkBAAEUPUZpKCDpXGYBBALH7QiKlpEkYVHMewACgA4AAoI0egEMlvotM7vbaDYE",
    3: "CAACAgEAAxkBAAEUPUppKCDqt26xtPk8KPWnzppQQRUcHQACgQ4AAoI0egHmMZTw4jEsUjYE",
    4: "CAACAgEAAxkBAAEUPUxpKCDtp8yrDuTjlvigAAEb3S9nwswAAoIOAAKCNHoBcXoP6t45cr02BA",
    5: "CAACAgEAAxkBAAEUPU5pKCDvBOd9dHfN52hcyULQPM6aFAACgw4AAoI0egHMmDGMXUyPXzYE",
    6: "CAACAgEAAxkBAAEUPVBpKCDxbZuZ_VcEfiq5kxd5iFrwBAAChA4AAoI0egEyx_5CLNK94DYE"
}


@contextmanager
def db_session():
    """Контекстный менеджер для работы с БД"""
    db = next(get_db())
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class DiceGameLogic:
    """Логика игры в кубики"""

    def __init__(self):
        self.logger = logger

    async def _send_dice_sticker(self, chat_id: int, dice_value: int):
        """Отправляет стикер кубика"""
        try:
            sticker_file_id = DICE_STICKERS.get(dice_value)
            if sticker_file_id:
                await bot.send_sticker(chat_id=chat_id, sticker=sticker_file_id)
            else:
                dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
                await bot.send_message(chat_id=chat_id, text=dice_emojis.get(dice_value, "🎲"))
        except Exception as e:
            self.logger.error(f"Error sending dice sticker: {e}")

    def _get_win_emoji(self) -> str:
        """Возвращает эмодзи для выигрыша"""
        win_emojis = ["🎉", "🏆", "✨", "⭐", "🎊", "💫"]
        return random.choice(win_emojis)

    def _get_lose_emoji(self) -> str:
        """Возвращает эмодзи для проигрыша"""
        lose_emojis = ["😔", "😢", "😅", "🤔", "🎲", "🍀"]
        return random.choice(lose_emojis)

    def _get_win_message(self) -> str:
        """Возвращает случайное сообщение о победе"""
        win_messages = [
            "🎊 <b>ФАНТАСТИЧЕСКАЯ ПОБЕДА!</b> 🎊",
            "🔥 <b>НЕВЕРОЯТНАЯ УДАЧА!</b> 🔥",
            "🏆 <b>ВЕЛИКОЛЕПНЫЙ РЕЗУЛЬТАТ!</b> 🏆",
            "✨ <b>БЛЕСТЯЩАЯ ПОБЕДА!</b> ✨",
            "⭐ <b>УДАЧА НА ТВОЕЙ СТОРОНЕ!</b> ⭐",
            "💎 <b>ИДЕАЛЬНОЕ ПОПАДАНИЕ!</b> 💎"
        ]
        return random.choice(win_messages)

    def _get_lose_message(self) -> str:
        """Возвращает случайное сообщение о проигрыше"""
        lose_messages = [
            "😔 <b>ЭТОТ РАЗ НЕ ПОВЕЗЛО</b> 😔",
            "🌀 <b>УДАЧА ОТВЕРНУЛАСЬ</b> 🌀",
            "📉 <b>НЕ СЕГОДНЯШНИЙ ДЕНЬ</b> 📉",
            "🎲 <b>КУБИК БЫЛ ПРОТИВ</b> 🎲",
            "💫 <b>ПОПРОБУЙ ЕЩЁ РАЗ!</b> 💫"
        ]
        return random.choice(lose_messages)

    def _get_encouragement(self) -> str:
        """Возвращает случайное подбадривающее сообщение"""
        encouragements = [
            "Удача уже на подходе! 🍀",
            "Следующий раз будет твоим! ⭐",
            "Повезёт в следующий раз! ✨",
            "Игра продолжается! 🎲",
            "Попробуй ещё! Удача ждёт! 💫",
            "Не сдавайся! Выигрыш близко! 🎯"
        ]
        return random.choice(encouragements)

    async def _get_win_result_text(self, user_name: str, bet: int, selected: int, result: int, win_amount: int,
                                   user_coins: int) -> str:
        """Текст результата для выигрыша"""
        win_emoji = self._get_win_emoji()
        win_message = self._get_win_message()

        decorated_name = f"🎮 {user_name}"

        return (
            f"{win_emoji} {win_message} {win_emoji}\n\n"
            f"👤 Игрок: <b>{decorated_name}</b>\n"
            f"🎲 Результат: <b>{result}</b>\n"
            f"🎯 Ваша ставка: <b>{selected}</b>\n\n"
            f"💰 <b>Ставка:</b> {bet:,} монет\n"
            f"🏆 <b>Выигрыш:</b> {win_amount:,} монет\n"
            f"💎 <b>Множитель:</b> x{DICE_GAME_CONFIG['multiplier']}\n\n"
            f"{win_emoji} <b>Поздравляем с победой!</b> {win_emoji}"
        )

    async def _get_lose_result_text(self, user_name: str, bet: int, selected: int, result: int, user_coins: int) -> str:
        """Текст результата для проигрыша"""
        lose_emoji = self._get_lose_emoji()
        lose_message = self._get_lose_message()
        encouragement = self._get_encouragement()

        decorated_name = f"🎮 {user_name}"

        return (
            f"{lose_emoji} {lose_message} {lose_emoji}\n\n"
            f"👤 Игрок: <b>{decorated_name}</b>\n"
            f"🎲 Результат: <b>{result}</b>\n"
            f"🎯 Ваша ставка: <b>{selected}</b>\n\n"
            f"💰 <b>Ставка:</b> {bet:,} монет\n"
            f"💸 <b>Потеряно:</b> {bet:,} монет\n\n"
            f"✨ {encouragement}"
        )

    async def check_balance(self, user_id: int, bet: int) -> Tuple[bool, int, str]:
        """Проверяет баланс пользователя и возвращает результат"""
        try:
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return False, 0, "❌ Пользователь не найден"

                return user.coins >= bet, user.coins, ""
        except Exception as e:
            self.logger.error(f"Error checking balance: {e}")
            return False, 0, "❌ Ошибка при проверке баланса"

    async def play_dice_game(self, user_id: int, user_name: str, bet: int, selected_number: int, chat_id: int) -> Tuple[
        str, int]:
        """Основная логика игры в кубики. Возвращает текст результата и число кубика."""
        try:
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)

                if not user:
                    return "❌ Пользователь не найден", 0

                if user.coins < bet:
                    return f"❌ Недостаточно монет для ставки. Ваш баланс: {user.coins:,}", 0

                # Снимаем ставку
                user.coins -= bet

                # Генерируем результат
                dice_result = random.randint(1, 6)
                win_amount = await self._calculate_win(bet, selected_number, dice_result)

                # Записываем транзакцию для проигрыша/ставки сразу
                if win_amount == 0:
                    # Проигрыш
                    TransactionRepository.create_transaction(
                        db,
                        from_user_id=user_id,
                        to_user_id=None,  # None для проигрыша в систему
                        amount=bet,
                        description=f"🎲 Проигрыш в кубики (ставка: {selected_number}, выпало: {dice_result})"
                    )

                # Начисляем выигрыш
                if win_amount > 0:
                    user.coins += win_amount

                    # Записываем транзакцию для выигрыша
                    TransactionRepository.create_transaction(
                        db,
                        from_user_id=None,  # None для выигрыша от системы
                        to_user_id=user_id,
                        amount=win_amount,
                        description=f"🎲 Выигрыш в кубики (ставка: {selected_number}, выпало: {dice_result}, множитель: x{DICE_GAME_CONFIG['multiplier']})"
                    )

                # Сохраняем изменения
                db.add(user)
                db.commit()

                # Формируем текст результата
                if win_amount > 0:
                    result_text = await self._get_win_result_text(
                        user_name, bet, selected_number, dice_result, win_amount, user.coins
                    )
                else:
                    result_text = await self._get_lose_result_text(
                        user_name, bet, selected_number, dice_result, user.coins
                    )

                return result_text, dice_result

        except Exception as e:
            self.logger.error(f"Error in play_dice_game: {e}", exc_info=True)
            return "❌ Произошла ошибка во время игры. Попробуйте еще раз.", 0

    async def _calculate_win(self, bet: int, selected: int, result: int) -> int:
        """Рассчитывает выигрыш для кубика"""
        if selected == result:
            return bet * DICE_GAME_CONFIG['multiplier']
        return 0

    async def validate_bet(self, bet: int) -> Tuple[bool, str]:
        """Проверяет валидность ставки"""
        min_bet = DICE_GAME_CONFIG['bet_min']
        max_bet = DICE_GAME_CONFIG['bet_max']

        if bet < min_bet:
            return False, f"❌ Минимальная ставка: {min_bet:,} монет"
        if bet > max_bet:
            return False, f"❌ Максимальная ставка: {max_bet:,} монет"

        return True, "OK"

    async def validate_number(self, number: int) -> Tuple[bool, str]:
        """Проверяет валидность выбранного числа"""
        if number < 1 or number > 6:
            return False, "❌ Выберите число от 1 до 6"
        return True, "OK"

    async def parse_text_command(self, text: str) -> dict:
        """Парсит текстовую команду игры в кубики"""
        try:
            text_lower = text.lower().strip()

            # Разные варианты команд - ТОЛЬКО правильный формат с двумя числами
            patterns = [
                r'^кубик\s+(\d+)\s+(\d+)$',
                r'^кости\s+(\d+)\s+(\d+)$',
                r'^dice\s+(\d+)\s+(\d+)$',
                r'^/кубик\s+(\d+)\s+(\d+)$',
                r'^/кости\s+(\d+)\s+(\d+)$',
                r'^/dice\s+(\d+)\s+(\d+)$',
            ]

            for pattern in patterns:
                match = re.match(pattern, text_lower)
                if match:
                    bet = int(match.group(1))
                    selected_number = int(match.group(2))
                    return {
                        'bet': bet,
                        'selected_number': selected_number,
                        'valid': True
                    }

            return None

        except Exception as e:
            self.logger.error(f"Error parsing dice command: {e}")
            return None


class DiceMessageHandlers:
    """Обработчики сообщений для игры в кубики"""

    def __init__(self, game_logic: DiceGameLogic):
        self.game_logic = game_logic
        self.logger = logger
        self.user_cooldowns = {}
        self.active_users = set()

    def _check_text_cooldown(self, user_id: int) -> tuple[bool, str]:
        """Проверяет кулдаун для текстовой игры"""
        current_time = asyncio.get_event_loop().time()

        # Проверяем активность пользователя
        if user_id in self.active_users:
            return False, "⏳ Игра уже запущена, подождите завершения"

        if user_id in self.user_cooldowns:
            time_passed = current_time - self.user_cooldowns[user_id]
            if time_passed < DICE_GAME_CONFIG['throttle_time']:
                remaining = DICE_GAME_CONFIG['throttle_time'] - int(time_passed)
                return False, f"⏳ Подождите {remaining} секунд"

        self.user_cooldowns[user_id] = current_time
        return True, ""

    def _add_active_user(self, user_id: int):
        """Добавляет пользователя в список активных"""
        self.active_users.add(user_id)

    def _remove_active_user(self, user_id: int):
        """Удаляет пользователя из списка активных"""
        self.active_users.discard(user_id)

    async def dice_help(self, message: types.Message):
        """Показывает красивую справку по игре"""
        text = (
            "🎲 <b>ИГРА «КУБИК»</b> 🎲\n\n"
            "✨ <b>Добро пожаловать в классическую игру!</b> ✨\n\n"

            "🎯 <b>ПРАВИЛА ИГРЫ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Угадай число от 1 до 6\n"
            "• Выигрыш: <b>x6</b> от ставки\n"
            "• Шанс выигрыша: 1 из 6 (16.67%)\n\n"

            "💰 <b>СТАВКИ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Минимальная: {DICE_GAME_CONFIG['bet_min']:,} монет\n"
            f"• Максимальная: {DICE_GAME_CONFIG['bet_max']:,} монет\n\n"

            "🎮 <b>КОМАНДЫ ДЛЯ ИГРЫ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>кубик 1000 3</code>\n"
            "• <code>кости 5000 5</code>\n"
            "• <code>dice 10000 2</code>\n\n"

            "📋 <b>ПРИМЕРЫ:</b>\n"
            "• <code>кубик 5000 4</code> - ставка 5000 на число 4\n"
            "• <code>кости 10000 6</code> - ставка 10000 на число 6\n\n"

            "🌟 <b>Удачи в игре! Пусть кубик благоволит тебе!</b> 🌟"
        )
        await message.answer(text, parse_mode="HTML")

    async def dice_command(self, message: types.Message):
        """Обработчик команды игры в кубики"""
        text_lower = message.text.lower().strip()

        # ТОЧНОЕ совпадение с командами справки (без чисел)
        help_commands = {
            "кубик", "кости", "dice",
            "/кубик", "/кости", "/dice"
        }

        # Если точное совпадение с командами справки
        if text_lower in help_commands:
            await self.dice_help(message)
            return

        # Пытаемся распарсить игровую команду
        parsed = await self.game_logic.parse_text_command(message.text)
        if parsed:
            await self.dice_game_handler(message)
            return

        # Если не распознано - ничего не делаем (игнорируем)

    async def dice_game_handler(self, message: types.Message):
        """Обрабатывает игровые команды"""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or message.from_user.username or "Игрок"

        # Проверяем кулдаун и активность
        cooldown_ok, cooldown_message = self._check_text_cooldown(user_id)
        if not cooldown_ok:
            await message.answer(cooldown_message)
            return

        # Парсим команду
        parsed = await self.game_logic.parse_text_command(message.text)

        if not parsed:
            # Если команда не распознана, ничего не делаем
            return

        bet = parsed['bet']
        selected_number = parsed['selected_number']

        # Проверяем ставку
        bet_valid, bet_error = await self.game_logic.validate_bet(bet)
        if not bet_valid:
            await message.answer(bet_error)
            return

        # Проверяем число
        number_valid, number_error = await self.game_logic.validate_number(selected_number)
        if not number_valid:
            await message.answer(number_error)
            return

        # Проверяем баланс
        balance_ok, balance, balance_error = await self.game_logic.check_balance(user_id, bet)
        if not balance_ok:
            balance_text = (
                f"❌ <b>{user_name}, ставка не может превышать ваши средства</b>\n\n"
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("💳 Пополнить баланс", url="https://t.me/EXEZ_Kassa"))

            await message.answer(balance_text, reply_markup=keyboard, parse_mode="HTML")
            return

        try:
            # Помечаем пользователя как активного
            self._add_active_user(user_id)

            # Играем и получаем результат
            result_text, dice_result = await self.game_logic.play_dice_game(
                user_id,
                user_name,
                bet,
                selected_number,
                message.chat.id
            )

            # Отправляем стикер кубика с РЕАЛЬНЫМ результатом
            await self.game_logic._send_dice_sticker(message.chat.id, dice_result)

            # Ждем минимальное время для драматизма
            await asyncio.sleep(1.5)

            # Показываем результат
            await message.answer(result_text, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in dice game for user {user_id}: {e}", exc_info=True)
            await message.answer("❌ Произошла ошибка во время игры. Попробуйте еще раз.", parse_mode="HTML")
        finally:
            # Всегда снимаем блокировку
            self._remove_active_user(user_id)


def register_dice_handlers(dp: Dispatcher):
    """Регистрация обработчиков игры в кубики"""
    handler = DiceGameLogic()
    message_handlers = DiceMessageHandlers(handler)

    # Регистрация команд для ЛЮБЫХ чатов
    dp.register_message_handler(
        message_handlers.dice_command,
        commands=["кубик", "dice"],
        state="*"
    )
    dp.register_message_handler(
        message_handlers.dice_command,
        lambda m: m.text and m.text.strip().lower().startswith(("кубики", "кубик", "dice", "кости")),
        state="*"
    )

    logging.info("✅ Игра 'Кубик' зарегистрирована (работает везде + текстовая игра)")