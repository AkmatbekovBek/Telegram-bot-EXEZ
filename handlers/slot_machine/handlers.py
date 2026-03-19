# handlers/slot_machine/handlers.py (исправленная версия)
import logging
import asyncio
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .game_logic import SlotGameLogic
from .config import SLOT_MACHINE_CONFIG

logger = logging.getLogger(__name__)


class SlotMessageHandlers:
    """Обработчики сообщений для игрового автомата"""

    def __init__(self, game_logic: SlotGameLogic):
        self.game_logic = game_logic
        self.logger = logger
        self.user_cooldowns = {}
        self.active_users = set()
        self.config = SLOT_MACHINE_CONFIG

    def _check_text_cooldown(self, user_id: int) -> tuple[bool, str]:
        """Проверяет кулдаун для текстовой игры"""
        current_time = asyncio.get_event_loop().time()

        # Проверяем активность пользователя
        if user_id in self.active_users:
            return False, "⏳ Игра уже запущена, подождите завершения"

        if user_id in self.user_cooldowns:
            time_passed = current_time - self.user_cooldowns[user_id]
            if time_passed < self.config['throttle_time']:
                remaining = self.config['throttle_time'] - int(time_passed)
                return False, f"⏳ Подождите {remaining} секунд"

        self.user_cooldowns[user_id] = current_time
        return True, ""

    def _add_active_user(self, user_id: int):
        """Добавляет пользователя в список активных"""
        self.active_users.add(user_id)

    def _remove_active_user(self, user_id: int):
        """Удаляет пользователя из списка активных"""
        self.active_users.discard(user_id)

    def _get_deposit_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура для пополнения баланс"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                "💳 Пополнить баланс",
                url="https://t.me/EXEZ_Kassa"
            )
        )
        return keyboard

    async def _get_insufficient_balance_text(self, user_name: str, bet: int, balance: int) -> str:
        """Текст сообщения о недостаточном балансе"""
        needed = bet - balance
        return (
            f"🎰 <b>{user_name}</b>, недостаточно средств для ставки!\n\n"
            f"💰 <b>Ваш баланс:</b> {balance:,} монет\n"
            f"🎯 <b>Ставка:</b> {bet:,} монет\n"
            f"❌ <b>Не хватает:</b> {needed:,} монет\n\n"
            f"<i>Пополните баланс и попробуйте снова!</i>"
        )

    async def slot_main_handler(self, message: types.Message):
        """Главный обработчик всех сообщений для слотов"""
        text = message.text.strip().lower() if message.text else ""

        # Если сообщение пустое или не текст
        if not text:
            return

        # Команды для показа справки (без чисел)
        help_commands = [
            "слот", "автомат", "slot", "slots",
            "игровой автомат", "игровой слот",
            "слоты", "автоматы",
            "/слот", "/автомат", "/slot", "/slots"
        ]

        # Если команда для справки (без чисел)
        if text in help_commands:
            await self.slot_help(message)
            return

        # Если это игровая команда (с числом)
        parsed = await self.game_logic.parse_text_command(message.text)
        if parsed:
            await self.slot_game_handler(message)
            return

        # Если команда не распознана, но начинается с игровых слов
        if any(text.startswith(word) for word in ['слот ', 'автомат ', 'slot ', 'slots ', 'игра ']):
            await self.slot_help(message)
            return

    async def slot_help(self, message: types.Message):
        """Показывает красивую справку по игре"""
        payouts = self.config['payouts']
        text = (
            "🎰 <b>ИГРОВОЙ АВТОМАТ</b> 🎰\n\n"
            "✨ <b>Добро пожаловать в захватывающую игру!</b> ✨\n\n"

            "💎 <b>ВЫИГРЫШНЫЕ КОМБИНАЦИИ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎊 <b>7️⃣7️⃣7️⃣</b> — ДЖЕКПОТ x{payouts['three_sevens']}\n"
            f"💎 <b>BAR BAR BAR</b> — x{payouts['three_bars']}\n"
            f"🍇 <b>🍇🍇🍇</b> — x{payouts['three_grapes']}\n"
            f"🍋 <b>🍋🍋🍋</b> — x{payouts['three_lemons']}\n"
            f"⭐ <b>7️⃣7️⃣ + любой</b> — x{payouts['two_sevens']}\n\n"

            "💰 <b>СТАВКИ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Минимальная: {self.config['bet_min']:,} монет\n"
            f"• Максимальная: {self.config['bet_max']:,} монет\n\n"

            "🎮 <b>КОМАНДЫ ДЛЯ ИГРЫ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <code>слот {self.config['bet_min']:,}</code>\n"
            f"• <code>автомат {self.config['bet_min']*10:,}</code>\n"
            f"• <code>slot {self.config['bet_min']*50:,}</code>\n"
            f"• <code>slots {self.config['bet_min']*100:,}</code>\n\n"

            f"⏱ <b>Кулдаун:</b> {self.config['throttle_time']} секунды между играми\n\n"

            "🌟 <b>Удачи в игре! Пусть фортуна улыбнется вам!</b> 🌟"
        )
        await message.answer(text, parse_mode="HTML")

    async def slot_game_handler(self, message: types.Message):
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
            # Если команда не распознана, показываем справку
            await self.slot_help(message)
            return

        bet = parsed['bet']

        # Проверяем ставку
        bet_valid, bet_error = await self.game_logic.validate_bet(bet)
        if not bet_valid:
            await message.answer(bet_error)
            return

        # Проверяем баланс
        balance_ok, balance, balance_error = await self.game_logic.check_balance(user_id, bet)
        if not balance_ok:
            balance_text = await self._get_insufficient_balance_text(user_name, bet, balance)
            await message.answer(
                balance_text,
                reply_markup=self._get_deposit_keyboard(),
                parse_mode="HTML"
            )
            return

        try:
            # Помечаем пользователя как активного
            self._add_active_user(user_id)

            # Отправляем dice
            dice_message = await message.answer_dice(emoji="🎰")

            # Ждем минимальное время
            await asyncio.sleep(1.5)

            # Получаем результат игры
            result_text = await self.game_logic.play_slot_game(
                user_id,
                user_name,
                bet,
                dice_message.dice.value
            )

            # Показываем результат
            await message.answer(result_text, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in slot game for user {user_id}: {e}", exc_info=True)
            await message.answer("❌ Произошла ошибка во время игры. Попробуйте еще раз.", parse_mode="HTML")
        finally:
            # Всегда снимаем блокировку
            self._remove_active_user(user_id)