# handlers/slot_machine/game_logic (исправленная версия)

import logging
import asyncio
import random
import re
from typing import List, Tuple
from aiogram import types
from database import get_db
from database.crud import UserRepository, TransactionRepository
from contextlib import contextmanager
from .config import SLOT_MACHINE_CONFIG, SLOT_SYMBOLS

logger = logging.getLogger(__name__)


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


class SlotGameLogic:
    """Логика игры в игровой автомат"""

    def __init__(self):
        self.logger = logger
        self.config = SLOT_MACHINE_CONFIG

    def _calculate_win(self, combo: List[str], bet: int) -> Tuple[bool, int, int, str]:
        """Рассчитывает выигрыш для комбинации и возвращает множитель + тип выигрыша"""
        payouts = self.config['payouts']

        # Три одинаковых символа
        if combo[0] == combo[1] == combo[2]:
            if combo[0] == "7️⃣":
                multiplier = payouts['three_sevens']
                win_type = "ДЖЕКПОТ! 🎰 ТРИ СЕМЁРКИ!"
                return True, bet * multiplier, multiplier, win_type
            elif combo[0] == "BAR":
                multiplier = payouts['three_bars']
                win_type = "БОЛЬШОЙ ВЫИГРЫШ! 💎 ТРИ БАРА!"
                return True, bet * multiplier, multiplier, win_type
            elif combo[0] == "🍇":
                multiplier = payouts['three_grapes']
                win_type = "ВКУСНАЯ ПОБЕДА! 🍇 ТРИ ВИНОГРАДА!"
                return True, bet * multiplier, multiplier, win_type
            elif combo[0] == "🍋":
                multiplier = payouts['three_lemons']
                win_type = "ОСВЕЖАЮЩИЙ ВЫИГРЫШ! 🍋 ТРИ ЛИМОНА!"
                return True, bet * multiplier, multiplier, win_type

        # Две семёрки + любой
        elif combo.count("7️⃣") == 2:
            multiplier = payouts['two_sevens']
            win_type = "ОТЛИЧНАЯ УДАЧА! ✨ ДВЕ СЕМЁРКИ!"
            return True, bet * multiplier, multiplier, win_type

        # Проигрыш
        return False, 0, 0, ""

    def _get_combo_values(self, dice_value: int) -> List[str]:
        """Возвращает комбинацию символов по значению dice"""
        # dice_value от 1 до 64 для emoji 🎰
        dice_value -= 1  # Приводим к диапазону 0-63
        result = []
        for _ in range(3):
            result.append(SLOT_SYMBOLS[dice_value % len(SLOT_SYMBOLS)])
            dice_value //= len(SLOT_SYMBOLS)
        return result

    def _get_win_emoji(self, multiplier: int) -> str:
        """Возвращает эмодзи в зависимости от размера выигрыша"""
        if multiplier >= 7:
            return "💰🎉🏆"
        elif multiplier >= 5:
            return "💰✨🎊"
        elif multiplier >= 4:
            return "💰🎯⭐"
        else:
            return "💰🎰"

    def _get_lose_emoji(self) -> str:
        """Возвращает эмодзи для проигрыша"""
        lose_emojis = ["😔", "😢", "😅", "🤔", "🎰", "🍀"]
        return random.choice(lose_emojis)

    def _get_encouragement(self) -> str:
        """Возвращает случайное подбадривающее сообщение"""
        encouragements = [
            "Удача уже на подходе! 🍀",
            "Следующий раз будет твоим! ⭐",
            "Повезёт в следующий раз! ✨",
            "Игра продолжается! 🎰",
            "Попробуй ещё! Удача ждёт! 💫",
            "Не сдавайся! Выигрыш близко! 🎯"
        ]
        return random.choice(encouragements)

    def _get_win_message(self, win_type: str) -> str:
        """Возвращает красивое сообщение о победе"""
        win_messages = {
            "ДЖЕКПОТ! 🎰 ТРИ СЕМЁРКИ!": [
                "🎊 <b>ДЖЕКПОТ! Невероятная удача!</b> 🎊",
                "🔥 <b>ФЕЕРИЧЕСКИЙ ВЫИГРЫШ! ДЖЕКПОТ!</b> 🔥",
                "🏆 <b>ВЕЛИКОЛЕПНО! ЗАХВАТЫВАЮЩИЙ ДЖЕКПОТ!</b> 🏆"
            ],
            "БОЛЬШОЙ ВЫИГРЫШ! 💎 ТРИ БАРА!": [
                "💎 <b>БРИЛЛИАНТОВАЯ ПОБЕДА! ТРИ БАРА!</b> 💎",
                "✨ <b>БЛЕСТЯЩИЙ РЕЗУЛЬТАТ! ТРИ БАРА!</b> ✨",
                "🎯 <b>ПОПАДАНИЕ В ЦЕЛЬ! ТРИ БАРА!</b> 🎯"
            ],
            "ВКУСНАЯ ПОБЕДА! 🍇 ТРИ ВИНОГРАДА!": [
                "🍇 <b>СЛАДКАЯ ПОБЕДА! ТРИ ВИНОГРАДА!</b> 🍇",
                "🎉 <b>ВКУСНЫЙ ВЫИГРЫШ! ТРИ ВИНОГРАДА!</b> 🎉",
                "⭐ <b>ФРУКТОВЫЙ УСПЕХ! ТРИ ВИНОГРАДА!</b> ⭐"
            ],
            "ОСВЕЖАЮЩИЙ ВЫИГРЫШ! 🍋 ТРИ ЛИМОНА!": [
                "🍋 <b>ОСВЕЖАЮЩАЯ ПОБЕДА! ТРИ ЛИМОНА!</b> 🍋",
                "💫 <b>ЦИТРУСОВЫЙ УСПЕХ! ТРИ ЛИМОНА!</b> 💫",
                "🎊 <b>КИСЛО-СЛАДКАЯ ПОБЕДА! ТРИ ЛИМОНА!</b> 🎊"
            ],
            "ОТЛИЧНАЯ УДАЧА! ✨ ДВЕ СЕМЁРКИ!": [
                "✨ <b>БЛИСТАТЕЛЬНАЯ УДАЧА! ДВЕ СЕМЁРКИ!</b> ✨",
                "🎯 <b>ОТЛИЧНЫЙ РЕЗУЛЬТАТ! ДВЕ СЕМЁРКИ!</b> 🎯",
                "⭐ <b>ВЕЗЕНИЕ НА ТВОЕЙ СТОРОНЕ! ДВЕ СЕМЁРКИ!</b> ⭐"
            ]
        }

        messages = win_messages.get(win_type, ["🎉 <b>ПОБЕДА!</b> 🎉"])
        return random.choice(messages)

    async def _get_result_text(self, user_name: str, bet: int, combo: List[str], is_win: bool,
                               win_amount: int, multiplier: int, user_coins: int, win_type: str = "") -> str:
        """Текст результата игры с красивым оформлением"""
        combo_text = " | ".join(combo)

        # Красивое оформление имени пользователя
        decorated_name = f"🎮 {user_name}"

        if is_win:
            win_emoji = self._get_win_emoji(multiplier)
            win_message = self._get_win_message(win_type)

            return (
                f"{win_emoji} {win_message} {win_emoji}\n\n"
                f"👤 Игрок: <b>{decorated_name}</b>\n"
                f"🎰 Комбинация: <b>{combo_text}</b>\n\n"
                f"💰 <b>Ставка:</b> {bet:,} монет\n"
                f"🏆 <b>Выигрыш:</b> {win_amount:,} монет\n"
                f"💎 <b>Множитель:</b> x{multiplier}\n"
                f"💳 <b>Новый баланс:</b> {user_coins:,} монет\n\n"
                f"{win_emoji} <b>Поздравляем с победой!</b> {win_emoji}"
            )
        else:
            lose_emoji = self._get_lose_emoji()
            encouragement = self._get_encouragement()

            return (
                f"{lose_emoji} <b>ЭТОТ РАЗ НЕ ПОВЕЗЛО</b> {lose_emoji}\n\n"
                f"👤 Игрок: <b>{decorated_name}</b>\n"
                f"🎰 Комбинация: <b>{combo_text}</b>\n\n"
                f"💰 <b>Ставка:</b> {bet:,} монет\n"
                f"💸 <b>Потеряно:</b> {bet:,} монет\n"
                f"💳 <b>Новый баланс:</b> {user_coins:,} монет\n\n"
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

    async def play_slot_game(self, user_id: int, user_name: str, bet: int, dice_value: int = None) -> str:
        """Основная логика игры - исправленная версия с правильным обновлением баланса"""
        try:
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)

                if not user:
                    return "❌ Пользователь не найден"

                if user.coins < bet:
                    return f"❌ Недостаточно монет для ставки. Ваш баланс: {user.coins:,}"

                # Если dice_value не передан, используем случайное значение
                if dice_value is None:
                    dice_value = random.randint(1, 64)

                # Получаем комбинацию
                combo = self._get_combo_values(dice_value)
                is_win, win_amount, multiplier, win_type = self._calculate_win(combo, bet)

                # Обновляем баланс пользователя
                # Сначала снимаем ставку
                user.coins -= bet

                # Записываем транзакцию для ставки/проигрыша
                TransactionRepository.create_transaction(
                    db,
                    from_user_id=user_id,
                    to_user_id=None,  # None для проигрыша в систему
                    amount=bet,
                    description=f"🎰 Ставка в слотах (комбинация: {' | '.join(combo)})"
                )

                # Если выиграл - добавляем выигрыш
                if is_win:
                    user.coins += win_amount

                    # Записываем транзакцию для выигрыша
                    TransactionRepository.create_transaction(
                        db,
                        from_user_id=None,  # None для выигрыша от системы
                        to_user_id=user_id,
                        amount=win_amount,
                        description=f"🎰 Выигрыш в слотах (комбинация: {' | '.join(combo)}, множитель: x{multiplier})"
                    )

                # Сохраняем изменения в базе данных
                db.add(user)
                db.commit()

                # Формируем текст результата
                result_text = await self._get_result_text(
                    user_name, bet, combo, is_win, win_amount, multiplier, user.coins, win_type
                )

                return result_text

        except Exception as e:
            self.logger.error(f"Error in play_slot_game: {e}", exc_info=True)
            return "❌ Произошла ошибка во время игры. Попробуйте еще раз."

    async def validate_bet(self, bet: int) -> Tuple[bool, str]:
        """Проверяет валидность ставки"""
        min_bet = self.config['bet_min']
        max_bet = self.config['bet_max']

        if bet < min_bet:
            return False, f"❌ Минимальная ставка: {min_bet:,} монет"
        if bet > max_bet:
            return False, f"❌ Максимальная ставка: {max_bet:,} монет"

        return True, "OK"

    async def parse_text_command(self, text: str) -> dict:
        """Парсит текстовую команду игрового автомата"""
        try:
            text_lower = text.lower().strip()

            # Разные варианты команд
            patterns = [
                r'^слот\s+(\d+)$',
                r'^автомат\s+(\d+)$',
                r'^игра\s+(\d+)$',
                r'^/slot\s+(\d+)$',
                r'^slot\s+(\d+)$',
                r'^/slots\s+(\d+)$',
                r'^slots\s+(\d+)$',
                r'^/автомат\s+(\d+)$',
                r'^игровой\s+автомат\s+(\d+)$',
                r'^игровой\s+слот\s+(\d+)$',
            ]

            for pattern in patterns:
                match = re.match(pattern, text_lower)
                if match:
                    bet = int(match.group(1))
                    return {
                        'bet': bet,
                        'valid': True
                    }

            return None

        except Exception as e:
            self.logger.error(f"Error parsing slot command: {e}")
            return None