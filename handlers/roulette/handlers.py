# handlers/roulette/handlers.py
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.utils.exceptions import BadRequest

from database.crud import UserRepository, RouletteRepository
from handlers.modroul.roulette_logs import RouletteLogger
import logging
logger = logging.getLogger(__name__)

# Локальные импорты из модульной структуры
from .config import CONFIG
from .models import Bet, UserBetSession, ChatSession, SessionManager
from .validators import BetValidator, BetParser, DatabaseManager
from .game_logic import RouletteGame, RouletteKeyboard, AntiFloodManager
from .utils import (
    get_display_name,
    format_username_with_link,
    get_plain_username,
    delete_bet_messages,
    delete_spin_message,
    format_wait_time,
    get_bet_display_value,
    calculate_bet_result,
    parse_vabank_bet,
)
from ..record import RecordCore, RecordService


class RouletteHandler:
    """Основной обработчик рулетки"""
    def __init__(self):
        self.game = RouletteGame()
        self.session_manager = SessionManager()
        self.logger = RouletteLogger()
        self.anti_flood = AntiFloodManager()
        self._cleanup_task = None
        self._command_handlers = self._setup_command_handlers()
        self.record_core = RecordCore()
        self.record_service = RecordService(self.record_core)

    async def initialize(self):
        """Инициализация обработчика"""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def shutdown(self):
        """Остановка обработчика"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self):
        """Периодическая очистка старых записей"""
        while True:
            await asyncio.sleep(60)
            self.anti_flood.cleanup_old_entries()
            self.session_manager.cleanup_old_sessions()

    def _setup_command_handlers(self) -> Dict[str, callable]:
        """Настраивает обработчики текстовых команд"""
        return {
            "го": self.spin_roulette,
            "крутить": self.spin_roulette,
            "spin": self.spin_roulette,
            "отмена": self.clear_bets_command,
            "очистить": self.clear_bets_command,
            "clear": self.clear_bets_command,
            "ставки": self.show_my_bets,
            "мои ставки": self.show_my_bets,
            "bets": self.show_my_bets,
            "лог": lambda m: self.show_logs_command(m, False),
            "!лог": lambda m: self.show_logs_command(m, True),
            "повторить": lambda m: self._repeat_last_bets(m.from_user.id, m.chat.id, m),
            "repeat": lambda m: self._repeat_last_bets(m.from_user.id, m.chat.id, m),
            "удвоить": lambda m: self._double_bets(m.from_user.id, m.chat.id, m),
            "удвой": lambda m: self._double_bets(m.from_user.id, m.chat.id, m),
            "double": lambda m: self._double_bets(m.from_user.id, m.chat.id, m),
        }

    # -------------------------------------------------------------------------
    # ОСНОВНЫЕ КОМАНДЫ
    # -------------------------------------------------------------------------
    async def start_roulette(self, message: types.Message):
        """Обработчик команды старта рулетки с авторегистрацией"""
        user_id = message.from_user.id
        first_name = message.from_user.first_name or ""
        username = message.from_user.username or ""

        # Автоматически создаем/получаем пользователя
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id, username, first_name)

            if not user:
                await message.answer("❌ Ошибка при создании профиля")
                return

        examples = (
            "🎰 Минирулетка\n"
            "Угадайте число из\n"
            "0💚\n"
            "1🔴 2⚫ 3🔴 4⚫ 5🔴 6⚫\n"
            "7🔴 8⚫ 9🔴10⚫11🔴12⚫\n"
            "Ставки можно текстом\n"
            "1000 на красное | 5000 на 12"
        )
        keyboard = RouletteKeyboard.create_roulette_keyboard()
        await message.answer(examples, reply_markup=keyboard)

    async def quick_start_roulette(self, message: types.Message):
        """Быстрый старт рулетки - только если есть ставки"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)
        user_session = session.get_user_session(user_id, get_display_name(message.from_user))
        if user_session.has_bets:
            await self.spin_roulette(message)

    async def clear_bets_command(self, message: types.Message):
        """Очистка ставки"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        success, result = await self._clear_bets(user_id, chat_id, message)
        await message.answer(result)

    async def show_my_bets(self, message: types.Message):
        """Показать мои ставки"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)
        if user_id not in session.user_sessions or not session.user_sessions[user_id].has_bets:
            await message.answer("❌ У вас нет активных ставок")
            return
        user_session = session.user_sessions[user_id]
        await message.answer(
            f"📋 Ваши активные ставки:\n{user_session.get_bets_info()}",
            parse_mode="Markdown"
        )

    async def show_balance(self, message: types.Message):
        """Показать баланс с авторегистрацией"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        first_name = message.from_user.first_name or ""
        username = message.from_user.username or ""

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id, username, first_name)

            if not user:
                await message.answer("❌ Ошибка при создании профиля")
                return

            coins = user.coins
            display_name = get_plain_username(get_display_name(message.from_user))
            session = self.session_manager.get_session(chat_id)
            active_bets_amount = 0
            if user_id in session.user_sessions and session.user_sessions[user_id].has_bets:
                active_bets_amount = session.user_sessions[user_id].total_amount
            balance_text = f"{display_name} \nмонеты: {coins}🪙"
            if active_bets_amount > 0:
                balance_text += f" +{active_bets_amount}"
            await message.answer(balance_text, parse_mode="Markdown")

    async def show_logs_command(self, message: types.Message, show_all: bool = False):
        """Команда показа логов"""
        chat_id = message.chat.id
        logs_count = self.logger.get_logs_count(chat_id)
        if logs_count == 0:
            await message.answer("📊 Логи рулетки этого чата:\nПока нет записей о играх")
            return
        limit = CONFIG.MAX_GAME_LOGS if show_all else 10
        logs = self.logger.get_recent_logs(chat_id, limit)
        if not logs:
            await message.answer("📊 Логи рулетки этого чата:\nПока нет записей о играх")
            return
        logs_text = "".join(f"{log['color_emoji']}{log['result']}\n" for log in logs)
        await message.answer(logs_text)

    # -------------------------------------------------------------------------
    # ОБРАБОТКА СТАВОК
    # -------------------------------------------------------------------------
    async def _place_multiple_bets(self, user_id: int, chat_id: int, bets: List[Tuple[int, str, str]],
                                   username: str, reply_target: types.Message) -> Tuple[bool, str, int]:
        """Размещает несколько ставок"""
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return False, "❌ Сначала зарегистрируйтесь через /start", 0
            coins = user.coins
            session = self.session_manager.get_session(chat_id)
            user_session = session.get_user_session(user_id, username)
            successful_bets = []
            total_amount = 0
            errors = []
            for amount, bet_type, bet_value in bets:
                is_valid, error_msg = BetValidator.validate_bet(amount, coins, user_session.total_amount)
                if not is_valid:
                    errors.append(error_msg)
                    continue
                bet = Bet(amount, bet_type, bet_value, username, user_id)
                if user_session.add_bet(bet):
                    coins -= amount
                    total_amount += amount
                    successful_bets.append(bet)
                    UserRepository.update_user_balance(db, user_id, coins)
                    UserRepository.update_max_bet(db, user_id, amount)

                    # --- СОХРАНЯЕМ СТАВКУ В БД (для краш-протекции) ---
                    try:
                        from database.models import ActiveRouletteBet
                        active_bet = ActiveRouletteBet(
                            user_id=user_id,
                            chat_id=chat_id,
                            amount=amount,
                            bet_type=bet_type,
                            bet_value=str(bet_value)
                        )
                        db.add(active_bet)
                        db.commit()
                    except Exception as e:
                        logger.error(f"Failed to save active bet: {e}")
                    # --------------------------------------------------

                    # --- СОХРАНЯЕМ СТАВКУ В БД (для краш-протекции) ---
                    try:
                        from database.models import ActiveRouletteBet
                        active_bet = ActiveRouletteBet(
                            user_id=user_id,
                            chat_id=chat_id,
                            amount=amount,
                            bet_type=bet_type,
                            bet_value=str(bet_value)
                        )
                        db.add(active_bet)
                        db.commit()
                    except Exception as e:
                        logger.error(f"Failed to save active bet: {e}")
                    # --------------------------------------------------

                    # --- СОХРАНЯЕМ СТАВКУ В БД (для краш-протекции) ---
                    try:
                        from database.models import ActiveRouletteBet
                        active_bet = ActiveRouletteBet(
                            user_id=user_id,
                            chat_id=chat_id,
                            amount=amount,
                            bet_type=bet_type,
                            bet_value=str(bet_value)
                        )
                        db.add(active_bet)
                        db.commit()
                    except Exception as e:
                        logger.error(f"Failed to save active bet: {e}")
                    # --------------------------------------------------

                    # --- СОХРАНЯЕМ СТАВКУ В БД (для краш-протекции) ---
                    try:
                        from database.models import ActiveRouletteBet
                        active_bet = ActiveRouletteBet(
                            user_id=user_id,
                            chat_id=chat_id,
                            amount=amount,
                            bet_type=bet_type,
                            bet_value=str(bet_value)
                        )
                        db.add(active_bet)
                        db.commit() 
                    except Exception as e:
                        logger.error(f"Failed to save active bet: {e}")
                    # --------------------------------------------------

                    # --- СОХРАНЯЕМ СТАВКУ В БД (для краш-протекции) ---
                    try:
                        from database.models import ActiveRouletteBet
                        active_bet = ActiveRouletteBet(
                            user_id=user_id,
                            chat_id=chat_id,
                            amount=amount,
                            bet_type=bet_type,
                            bet_value=str(bet_value)
                        )
                        db.add(active_bet)
                        db.commit() 
                    except Exception as e:
                        logger.error(f"Failed to save active bet: {e}")
                    # --------------------------------------------------

            if not successful_bets:
                error_message = "\n".join(errors) if errors else "❌ Не удалось разместить ни одну ставку"
                return False, error_message, 0

            if not getattr(session, 'is_doubling_operation', False):
                session.last_user_bets[user_id] = bets
            session.is_doubling_operation = False

            user_link = format_username_with_link(user_id, username)
            success_text = self._format_success_message(successful_bets, total_amount, user_link, errors)
            try:
                msg = await reply_target.answer(success_text, parse_mode="Markdown")
                user_session.bet_message_ids.append(msg.message_id)
            except Exception as e:
                logger.error(f"Ошибка при создании сообщения: {e}")

            return True, success_text, total_amount

    def _format_success_message(self, successful_bets: List[Bet], total_amount: int,
                                user_link: str, errors: List[str]) -> str:
        """Форматирует сообщение об успешной ставке"""
        if len(successful_bets) == 1:
            bet = successful_bets[0]
            text = f"Ставка принята: {user_link} {total_amount} монет на {bet.value}"
        else:
            bet_details = [f" ᅠ{bet.amount} на {bet.value}" for bet in successful_bets]
            text = f"Ставки приняты:\n" + "\n".join(bet_details) + f"\n💰 Общая сумма: {total_amount}"
        if errors:
            text += f"\nОшибки:\n" + "\n".join(errors)
        return text

    async def _clear_bets(self, user_id: int, chat_id: int, message: types.Message) -> Tuple[bool, str]:
        """Очищает все ставки пользователя"""
        session = self.session_manager.get_session(chat_id)
        if user_id not in session.user_sessions or not session.user_sessions[user_id].has_bets:
            return False, "❌ У вас нет активных ставок для очистки"

        user_session = session.user_sessions[user_id]
        total_amount = user_session.clear_bets()

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                UserRepository.update_user_balance(db, user_id, user.coins + total_amount)

        await delete_bet_messages(chat_id, user_session.bet_message_ids)
        return True, f"✅ Все ставки очищены. Возвращено {total_amount} монет"

    # -------------------------------------------------------------------------
    # ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
    # -------------------------------------------------------------------------
    async def place_bet(self, message: types.Message):
        """Обработка текстовых ставок с авторегистрацией"""
        text = (message.text or "").strip()
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = get_display_name(message.from_user)
        first_name = message.from_user.first_name or ""

        # Авторегистрация
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id, username, first_name)
            if not user:
                await message.answer("❌ Ошибка при создании профиля")
                return

        if await self._handle_special_commands(text, message, user_id, chat_id, username):
            return

        if text.upper() == "Б" or text.startswith("/"):
            return

        session = self.session_manager.get_session(chat_id)
        if user_id in session.waiting_for_bet:
            await self._handle_waiting_bet(user_id, chat_id, text, username, message, session)
            return

        bets = BetParser.parse_multiple_bets(text)
        if bets:
            ok, result_msg, total = await self._place_multiple_bets(user_id, chat_id, bets, username, message)
            if not ok:
                await message.answer(result_msg)
            return

        amount, bet_type, bet_value = BetParser.parse_single_bet(text)
        if amount and bet_type and bet_value:
            ok, result_msg, total = await self._place_multiple_bets(
                user_id, chat_id, [(amount, bet_type, bet_value)], username, message
            )
            if not ok:
                await message.answer(result_msg)

    async def _handle_special_commands(self, text: str, message: types.Message,
                                       user_id: int, chat_id: int, username: str) -> bool:
        """Обрабатывает специальные команды"""
        text_lower = text.lower().strip()
        if text_lower in ['лимиты', 'лимит', 'limits']:
            from handlers.transfer_limit import transfer_limit
            limit_info = transfer_limit.get_limit_info(user_id)
            await message.answer(limit_info)
            return True

        if text_lower.startswith(("ва-банк", "вабанк", "ва банк")):
            parts = text_lower.split()
            if len(parts) < 2:
                await message.answer("❌ Укажите тип ставки для вабанка\nПример: вабанк красное")
                return True
            bet_type = parts[1]
            await self._handle_vabank(user_id, chat_id, bet_type, message)
            return True

        if text_lower in self._command_handlers:
            await self._command_handlers[text_lower](message)
            return True

        return False

    async def _handle_vabank(self, user_id: int, chat_id: int, bet_value: str, message: types.Message):
        """Обработка ва-банка с проверкой некорректных диапазонов"""
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id,
                                                     message.from_user.username or "",
                                                     message.from_user.first_name or "")
            if not user:
                await message.answer("❌ Ошибка при создании профиля")
                return

            session = self.session_manager.get_session(chat_id)
            username = get_display_name(message.from_user)
            user_session = session.get_user_session(user_id, username)
            current_balance = user.coins

            if current_balance <= 0:
                await message.answer("❌ Недостаточно средств для ва-банка")
                return
            if current_balance < CONFIG.MIN_BET:
                await message.answer(f"❌ Минимальная ставка для ва-банка: {CONFIG.MIN_BET}")
                return

            bet_data = parse_vabank_bet(bet_value)
            if not bet_data:
                await message.answer("❌ Неверный тип ставки для вабанка")
                return

            bet_type, full_bet_value = bet_data

            # ПРОВЕРКА: Запрещаем некорректные диапазоны типа 5-5, 6-6 и т.д.
            if bet_type == "группа" and isinstance(full_bet_value, str) and '-' in full_bet_value:
                try:
                    start, end = map(int, full_bet_value.split('-'))
                    if start == end:
                        await message.answer(
                            "❌ Некорректный диапазон ставки. Используйте разные числа (например: 1-3, 4-6)")
                        return
                    if start > end:
                        await message.answer("❌ Некорректный диапазон ставки. Первое число должно быть меньше второго")
                        return
                except (ValueError, TypeError):
                    pass

            vabank_bet = Bet(current_balance, bet_type, full_bet_value, username, user_id)
            if not user_session.add_bet(vabank_bet):
                await message.answer("❌ Не удалось разместить ва-банк ставку")
                return

            UserRepository.update_user_balance(db, user_id, 0)
            total_all_bets = user_session.total_amount
            UserRepository.update_max_bet(db, user_id, max(getattr(user, 'max_bet', 0), total_all_bets))

            user_link = format_username_with_link(user_id, username)
            vabank_text = f"🎲 ВА-БАНК! {user_link} поставил все {current_balance:,} монет на {full_bet_value}"
            try:
                msg = await message.answer(vabank_text, parse_mode="Markdown")
                user_session.bet_message_ids.append(msg.message_id)
            except Exception as e:
                logger.error(f"Ошибка при создании сообщения: {e}")

    async def _handle_waiting_bet(self, user_id: int, chat_id: int, text: str, username: str,
                                  message: types.Message, session: ChatSession):
        """Обработка ожидаемой ставки"""
        bet_type, bet_value = session.waiting_for_bet[user_id]
        amount = BetParser.parse_amount(text.split()[0])
        if amount is None:
            await message.answer("❌ Введите корректную сумму (пример: 1000 или 1k)")
            return
        ok, result_msg, total = await self._place_multiple_bets(
            user_id, chat_id, [(amount, bet_type, bet_value)], username, message
        )
        del session.waiting_for_bet[user_id]
        if not ok:
            await message.answer(result_msg)

    # -------------------------------------------------------------------------
    # ОБРАБОТКА CALLBACK-ОВ
    # -------------------------------------------------------------------------
    async def handle_callback(self, call: types.CallbackQuery):
        """Обработчик callback-ов от инлайн-кнопок"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        data = call.data
        if not data:
            await call.answer("❌ Недействительная кнопка!")
            return

        # Обработка кнопки "back_to_shop"
        if data == "back_to_shop":
            await self._handle_shop_callback(call, user_id, chat_id)
            return

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                await call.answer("❌ Сначала зарегистрируйтесь через /start")
                return

            try:
                if ':' in data:
                    prefix, callback_data = data.split(':', 1)
                    await self._route_callback(prefix, callback_data, call, user_id, chat_id)
                else:
                    await self._handle_legacy_callback(data, call, user_id, chat_id)
            except Exception as e:
                logger.error(f"❌ Ошибка обработки callback: {e}")
                await call.answer("❌ Ошибка обработки кнопки")

    async def _handle_shop_callback(self, call: types.CallbackQuery, user_id: int, chat_id: int):
        """Обработка перехода в магазин"""
        try:
            from handlers.modroul.shop import shop_handler
            await call.message.delete()
            await shop_handler.show_shop(call.message)
        except ImportError:
            await call.answer("❌ Магазин временно недоступен")
        except Exception as e:
            logger.error(f"Ошибка при переходе в магазин: {e}")
            await call.answer("❌ Ошибка при переходе в магазин")

    async def _route_callback(self, prefix: str, callback_data: str, call: types.CallbackQuery,
                              user_id: int, chat_id: int):
        """Маршрутизирует callback по префиксам"""
        handlers = {
            "bet": self._handle_bet_callback,
            "quick": self._handle_quick_bet_callback,
            "action": self._handle_action_callback
        }
        handler = handlers.get(prefix)
        if handler:
            await handler(call, user_id, chat_id, callback_data)
        else:
            await call.answer("❌ Неизвестный тип кнопки")

    async def _handle_bet_callback(self, call: types.CallbackQuery, user_id: int,
                                   chat_id: int, callback_data: str):
        """Обработка callback-ов ставок"""
        bet_type_mapping = {
            "1-3": ("группа", "1-3"),
            "4-6": ("группа", "4-6"),
            "7-9": ("группа", "7-9"),
            "10-12": ("группа", "10-12"),
        }
        if callback_data in bet_type_mapping:
            session = self.session_manager.get_session(chat_id)
            bet_type, bet_value = bet_type_mapping[callback_data]
            session.waiting_for_bet[user_id] = (bet_type, bet_value)
            await call.answer(f"Выбрано: {bet_value}. Введите сумму ставки")
        else:
            await call.answer("❌ Неизвестный тип ставки")

    async def _handle_quick_bet_callback(self, call: types.CallbackQuery, user_id: int,
                                         chat_id: int, callback_data: str):
        """Обработка callback-ов быстрых ставок"""
        try:
            amount_str, color_type = callback_data.split("_")
            amount = int(amount_str)
            color_map = {
                "red": ("цвет", "красное"),
                "black": ("цвет", "черное"),
                "green": ("цвет", "зеленое")
            }
            if color_type in color_map:
                bet_type, bet_value = color_map[color_type]
                username = get_display_name(call.from_user)
                ok, result_msg, total = await self._place_multiple_bets(
                    user_id, chat_id, [(amount, bet_type, bet_value)], username, call.message
                )
                if ok:
                    await call.answer(f"Ставка {amount} на {bet_value} принята!")
                else:
                    await call.answer(f"❌ {result_msg}")
            else:
                await call.answer("❌ Неизвестный тип ставки")
        except Exception as e:
            logger.error(f"❌ Ошибка быстрой ставки: {e}")
            await call.answer("❌ Ошибка размещения ставки")

    # В методе _handle_action_callback в handlers/roulette/handlers.py
    async def _handle_action_callback(self, call: types.CallbackQuery, user_id: int,
                                      chat_id: int, callback_data: str):
        """Обработка callback-ов действий"""
        username = get_display_name(call.from_user)
        session = self.session_manager.get_session(chat_id)

        if callback_data == "spin":
            if session.is_spinning:
                await call.answer("🎰 Рулетка уже крутится! Подождите...")
                return

            # Сначала отвечаем на callback
            await call.answer("🎰 Крутим рулетку!")

            # Затем запускаем кручение рулетки
            # Нужно создать объект сообщения для передачи в spin_roulette
            class FakeMessage:
                def __init__(self, original_call):
                    self.from_user = original_call.from_user
                    self.chat = original_call.message.chat
                    self.answer = original_call.message.answer

            fake_message = FakeMessage(call)
            await self.spin_roulette(fake_message)

        elif callback_data == "repeat":
            await self._repeat_last_bets(user_id, chat_id, call)
            await call.answer("🔄 Повторяем последние ставки")
        elif callback_data == "double":
            await self._double_bets(user_id, chat_id, call)
            await call.answer("⚡ Удваиваем ставки")

    async def _handle_legacy_callback(self, data: str, call: types.CallbackQuery,
                                      user_id: int, chat_id: int):
        """Обработка старых форматов callback"""
        username = get_display_name(call.from_user)
        session = self.session_manager.get_session(chat_id)
        if data.startswith("bet_"):
            bet_value = data.replace("bet_", "")
            session.waiting_for_bet[user_id] = ("группа", bet_value)
            await call.answer(f"Выбрано: {bet_value}. Введите сумму ставки")
        elif data.startswith("quick_"):
            quick_data = data.replace("quick_", "")
            await self._handle_quick_bet_callback(call, user_id, chat_id, quick_data)
        elif data in ["repeat", "double", "spin"]:
            await self._handle_action_callback(call, user_id, chat_id, data)

    # -------------------------------------------------------------------------
    # ИГРОВАЯ МЕХАНИКА
    # -------------------------------------------------------------------------
    async def spin_roulette(self, message: types.Message):
        """Кручение рулетки и расчет результатов"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)

        # Проверяем, включена ли рулетка
        if not CONFIG.is_roulette_enabled(message.chat.id):
            chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"
            await message.answer(
                f"🚫 <b>Рулетка временно отключена администратором в {chat_name}.</b>\n\n"
                "Для включения используйте команду <code>!ron</code>",
                parse_mode="HTML"
            )
            return

        try:
            # Проверяем блокировку
            try:
                await asyncio.wait_for(session.spin_lock.acquire(), timeout=5.0)
            except asyncio.TimeoutError:
                await message.answer("🎰 Рулетка уже крутится!")
                return

            try:
                if session.is_spinning:
                    await message.answer("🎰 Рулетка уже крутится!")
                    return

                can_spin, wait_time = self.anti_flood.can_spin(user_id, chat_id)
                if not can_spin:
                    time_text = format_wait_time(wait_time)
                    await message.answer(f"⏳ Подождите {time_text} перед следующим запуском.")
                    return

                active_users = session.active_users
                if not active_users:
                    await message.answer("❌ Нет активных ставок для игры!")
                    return

                # 1. ГЕНЕРИРУЕМ СЛУЧАЙНОЕ ВРЕМЯ ОТ 3 ДО 15 СЕКУНД
                import random
                spin_duration = random.randint(3, 15)  # От 3 до 15 секунд

                # Получаем имя пользователя для отображения
                username = get_display_name(message.from_user)

                # Создаем кликабельную ссылку на пользователя
                user_link = format_username_with_link(user_id, username)

                # 2. Отправляем сообщение о начале кручения
                spin_msg = await message.answer(
                    f"{user_link} крутит (через {spin_duration} сек.)",
                    parse_mode="Markdown"
                )
                session.spin_message_id = spin_msg.message_id
                session.is_spinning = True

                # 3. Обратный отсчет с обновлением сообщения
                for i in range(spin_duration):
                    remaining = spin_duration - i
                    try:
                        if remaining <= 3:  # Последние 3 секунды показываем каждый раз
                            await spin_msg.edit_text(
                                f"🎰 Крутим рулетку... (осталось {remaining} сек.)",
                                parse_mode="Markdown"
                            )
                        elif i % 2 == 0:  # Обновляем каждые 2 секунды
                            await spin_msg.edit_text(
                                f"🎰 Крутим рулетку... (осталось {remaining} сек.)",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.debug(f"Не удалось обновить сообщение: {e}")

                    await asyncio.sleep(1)

                # 4. Удаляем сообщение о прокруте
                try:
                    await spin_msg.delete()
                except Exception as e:
                    logger.debug(f"Не удалось удалить сообщение: {e}")
                session.spin_message_id = None

                # 5. ОТПРАВЛЯЕМ ГИФКУ (КОРРЕКТНЫЙ МЕТОД ДЛЯ ВАШЕЙ ВЕРСИИ aiogram)
                gif_message = None
                try:
                    BASE_DIR = Path(__file__).resolve().parent.parent.parent
                    gif_path = BASE_DIR / "media" / "rlt2.gif"

                    if gif_path.exists():
                        logger.info(f"✅ Отправляем GIF: {gif_path}")

                        # Проверяем размер файла
                        file_size = gif_path.stat().st_size
                        logger.info(f"Размер файла: {file_size} байт ({file_size / 1024 / 1024:.2f} МБ)")

                        # Для старых версий aiogram используем InputFile с явным открытием файла
                        with open(gif_path, 'rb') as gif_file:
                            # Создаем InputFile с правильными параметрами
                            input_file = InputFile(gif_file, filename="roulette.gif")

                            # Отправляем как анимацию
                            gif_message = await message.answer_animation(
                                animation=input_file
                            )

                            # Ждем для отображения анимации
                            await asyncio.sleep(1.0)

                            # Удаляем GIF
                            if gif_message:
                                try:
                                    await gif_message.delete()
                                except Exception as e:
                                    logger.debug(f"Не удалось удалить GIF: {e}")
                    else:
                        logger.warning(f"GIF не найден: {gif_path}")
                        # Альтернатива: текстовый спиннер
                        fallback_msg = await message.answer("🎰")
                        await asyncio.sleep(0.8)
                        try:
                            await fallback_msg.delete()
                        except:
                            pass

                except BadRequest as e:
                    # Обрабатываем специфические ошибки Telegram
                    error_msg = str(e).lower()
                    if "file is too big" in error_msg:
                        logger.warning(f"GIF слишком большой: {e}")
                    elif "wrong file identifier" in error_msg:
                        logger.warning(f"Неверный идентификатор файла: {e}")
                    elif "not supported file type" in error_msg:
                        logger.warning(f"Файл не поддерживается как анимация: {e}")
                        # Проверяем, действительно ли это GIF
                        import mimetypes
                        mime_type, _ = mimetypes.guess_type(str(gif_path))
                        logger.info(f"MIME type файла: {mime_type}")
                        if mime_type != 'image/gif':
                            logger.warning("Файл не является настоящим GIF! Попробуйте переконвертировать.")

                    # Продолжаем без GIF
                    fallback_msg = await message.answer("🎰 Крутим...")
                    await asyncio.sleep(0.8)
                    try:
                        await fallback_msg.delete()
                    except:
                        pass

                except Exception as e:
                    logger.error(f"❌ Общая ошибка при отправке GIF: {e}")
                    # Продолжаем без GIF
                    fallback_msg = await message.answer("🎰")
                    await asyncio.sleep(0.5)
                    try:
                        await fallback_msg.delete()
                    except:
                        pass

                # 6. Генерируем результат и обрабатываем
                result = self.game.spin(chat_id)
                color_emoji = self.game.get_color_emoji(result)
                self.logger.add_game_log(chat_id, result, color_emoji)

                # 7. Обрабатываем результаты
                result_text = await self._process_game_results(active_users, result, color_emoji, chat_id, session)

                try:
                    # Формируем итоговое сообщение
                    final_message = f"🎰 Рулетка: {result}{color_emoji}"
                    if result_text.strip():
                        final_message += f"\n{result_text}"

                    await message.answer(final_message, parse_mode="Markdown")
                except BadRequest as e:
                    if "Message to be replied not found" in str(e):
                        await message.answer(final_message, parse_mode="Markdown")
                    else:
                        try:
                            await message.answer(final_message, parse_mode="Markdown")
                        except Exception:
                            logger.error(f"Failed to send roulette result: {e}")

            except Exception as e:
                logger.error(f"❌ Ошибка при кручении рулетки: {e}")
                await message.answer("❌ Произошла ошибка при кручении рулетки")
            finally:
                session.is_spinning = False
                if session.spin_lock.locked():
                    session.spin_lock.release()

        except Exception as e:
            logger.error(f"❌ Общая ошибка в spin_roulette: {e}")

    async def _process_game_results(self, active_users: Dict[int, UserBetSession], result: int,
                                    color_emoji: str, chat_id: int, session: ChatSession) -> str:
        """Обрабатывает результаты игры для всех пользователей"""
        # Просто показываем результат
        result_text = f""

        user_updates = {}
        user_stats_updates = {}

        # Сохраняем ставки для повторения
        for user_id, user_session in active_users.items():
            if user_session.bets:
                bets_for_repeat = [(bet.amount, bet.type, bet.value) for bet in user_session.bets]
                session.last_user_bets[user_id] = bets_for_repeat

        # Обрабатываем каждого пользователя
        for user_id, user_session in active_users.items():
            async with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    continue
                user_result_text = await self._process_user_results(
                    user_id, user_session, result, user, user_updates, user_stats_updates, chat_id
                )
                result_text += user_result_text + "\n"
                # Удаляем сообщения о ставках
                await delete_bet_messages(chat_id, user_session.bet_message_ids)

        # Выполняем пакетное обновление БД
        if user_updates:
            await self._update_database_batch(user_updates, user_stats_updates)

        # Очищаем ставки всех активных пользователей
        for user_id in active_users:
            if user_id in session.user_sessions:
                session.user_sessions[user_id].clear_bets()

        # --- УДАЛЯЕМ АКТИВНЫЕ СТАВКИ ИЗ БД (игра завершена) ---
        try:
            async with DatabaseManager.db_session() as db:
                from database.models import ActiveRouletteBet
                db.query(ActiveRouletteBet).filter(
                    ActiveRouletteBet.chat_id == chat_id
                ).delete()
                db.commit()
        except Exception as e:
            logger.error(f"Failed to clear active bets: {e}")
        # ------------------------------------------------------

        return result_text

    @staticmethod
    async def refund_active_bets_on_startup():
        """Возвращает деньги за ставки, которые были активны при падении бота"""
        try:
            async with DatabaseManager.db_session() as db:
                from database.models import ActiveRouletteBet, TelegramUser
                
                # Получаем все активные ставки
                active_bets = db.query(ActiveRouletteBet).all()
                
                if not active_bets:
                    logger.info("✅ Нет зависших ставок для возврата")
                    return

                logger.info(f"🔄 Найдено {len(active_bets)} зависших ставок. Возвращаем средства...")
                
                refunds_by_user = {} # user_id -> amount
                
                for bet in active_bets:
                    if bet.user_id not in refunds_by_user:
                        refunds_by_user[bet.user_id] = 0
                    refunds_by_user[bet.user_id] += bet.amount
                
                # Возвращаем деньги
                for user_id, amount in refunds_by_user.items():
                    user = db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()
                    if user:
                        user.coins += amount
                        logger.info(f"💰 Возвращено {amount} монет пользователю {user_id}")
                
                # Удаляем все записи
                db.query(ActiveRouletteBet).delete()
                db.commit()
                logger.info("✅ Возврат средств завершен")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при возврате средств: {e}")

    async def _process_user_results(self, user_id: int, user_session: UserBetSession, result: int,
                                    user, user_updates: Dict, user_stats_updates: Dict,
                                    chat_id: int) -> str:
        """Обрабатывает результаты для одного пользователя"""
        current_coins = user.coins
        win_coins = user.win_coins or 0
        defeat_coins = user.defeat_coins or 0
        max_win = user.max_win_coins or 0
        min_win = user.min_win_coins or 0
        total_net_profit = 0
        total_payout = 0
        user_bets_text = []
        refund_texts = []
        win_bets_text = []
        display_name = user_session.username

        # Флаг выпадения зелёного
        is_green_result = result == 0
        logger.debug(
            f"DEBUG _process_user_results: user_id={user_id}, result={result}, is_green_result={is_green_result}")

        # Сначала собираем все данные для транзакций
        transactions_data = []

        for bet in user_session.bets:
            net_profit, payout = calculate_bet_result(self.game, bet, result)

            # Проверяем, является ли ставка на зелёное
            is_green_bet = bet.type == "цвет" and bet.value == "зеленое"
            logger.debug(f"DEBUG: Ставка: type={bet.type}, value={bet.value}, is_green_bet={is_green_bet}")
            logger.debug(f"DEBUG: Результат ставки: net_profit={net_profit}, payout={payout}")

            total_net_profit += net_profit
            total_payout += payout
            plain_name = get_plain_username(display_name)
            # ✅ ДОБАВЛЯЕМ: кликабельное имя пользователя
            user_link = format_username_with_link(user_id, display_name)

            # 1. Сначала все ставки (не кликабельные)
            user_bets_text.append(f"{plain_name} {bet.amount} на {bet.value}")

            # 2. Потом возвраты (если есть) - не кликабельные
            # Возврат только если 0 выпало, но ставка НЕ выиграла (т.е. net_profit <= 0)
            if is_green_result and net_profit < 0:
                # Возврат 50% при зелёном (если ставка проиграла)
                refund_amount = bet.amount // 2
                logger.debug(f"DEBUG: Возврат при зеленом: refund_amount={refund_amount}")
                refund_texts.append(f"{plain_name} возврат {refund_amount} монет")

            if net_profit > 0:
                win_bets_text.append(f"{user_link} выиграл {net_profit} на {bet.value}")
            elif net_profit == 0 and payout > 0:  # Ничья с возвратом ставки
                win_bets_text.append(f"{user_link} возврат {bet.amount} на {bet.value}")

            # Сохраняем данные для транзакций
            transactions_data.append({
                'user_id': user_id,
                'amount': bet.amount,
                'is_win': net_profit > 0,
                'bet_type': bet.type,
                'bet_value': str(bet.value),
                'result_number': result,
                'profit': net_profit
            })

        logger.info(f"DEBUG: user_id={user_id}, total_profit={total_net_profit}")

        # 🔥 ВАЖНО: Обновляем рекорды
        if total_net_profit != 0:
            await self._update_user_records(user_id, total_net_profit, chat_id, display_name)

            if total_net_profit > 0:
                win_coins += total_net_profit
                max_win = max(max_win, total_net_profit)
            else:
                defeat_coins += abs(total_net_profit)

            if min_win is None:
                min_win = 0
            min_win = min(min_win, total_net_profit)

        # Сохраняем обновления для batch-обработки
        user_updates[user_id] = current_coins + total_payout
        current_max_bet = max(bet.amount for bet in user_session.bets) if user_session.bets else 0
        new_max_bet = max(getattr(user, 'max_bet_coins', 0), current_max_bet)

        user_stats_updates[user_id] = (win_coins, defeat_coins, max_win, min_win, new_max_bet)

        # Создаем транзакции
        await self._create_roulette_transactions(transactions_data)

        # Формируем финальный текст в правильном порядке:
        # 1. Сначала все ставки (не кликабельные)
        final_text_parts = []

        # Добавляем ставки
        for bet_text in user_bets_text:
            final_text_parts.append(bet_text)

        # 2. Потом возвраты (не кликабельные)
        for refund_text in refund_texts:
            final_text_parts.append(refund_text)

        # 3. Потом выигрыши (кликабельные)
        for win_text in win_bets_text:
            final_text_parts.append(win_text)

        return "\n".join(final_text_parts)

    async def _update_user_records(self, user_id: int, net_profit: int, chat_id: int, username: str):
        """Обновляет рекорды пользователя после игры в рулетку"""
        try:
            if net_profit > 0:
                # Обновляем рекорд выигрыша
                success = await self.record_service.add_win_record(
                    user_id=user_id,
                    amount=net_profit,
                    chat_id=chat_id,
                    username=username,
                    first_name=username
                )

                if success:
                    logger.info(f"✅ Рекорд выигрыша обновлен: {user_id} -> {net_profit}")
                else:
                    logger.warning(f"⚠️ Не удалось обновить рекорд для {user_id}")

            elif net_profit < 0:
                # Обновляем рекорд проигрыша
                loss_amount = abs(net_profit)
                success = await self.record_service.add_loss_record(
                    user_id=user_id,
                    loss_amount=loss_amount,
                    username=username,
                    first_name=username
                )

                if success:
                    logger.info(f"✅ Рекорд проигрыша обновлен: {user_id} -> {loss_amount}")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления рекордов: {e}")

    async def _create_roulette_transactions(self, transactions_data: List[Dict]):
        """Создает транзакции рулетки в БД с одинаковым временем для всех ставок одной игры"""
        async with DatabaseManager.db_session() as db:
            # Используем одно и то же время для всех транзакций одной игры
            # Округляем до секунд чтобы было одинаковое время для группировки
            from datetime import datetime
            game_time = datetime.now().replace(microsecond=0)

            for transaction in transactions_data:
                RouletteRepository.create_roulette_transaction(
                    db=db,
                    user_id=transaction['user_id'],
                    amount=transaction['amount'],
                    is_win=transaction['is_win'],
                    bet_type=transaction['bet_type'],
                    bet_value=transaction['bet_value'],
                    result_number=transaction['result_number'],
                    profit=transaction['profit'],
                    created_at=game_time  # Все транзакции одной игры получают одинаковое время
                )

    async def _update_database_batch(self, user_updates: Dict, user_stats_updates: Dict):
        """Пакетное обновление БД"""
        try:
            await DatabaseManager.update_users_batch(user_updates, user_stats_updates)
        except Exception as e:
            logger.error(f"❌ Ошибка при пакетном обновлении БД: {e}")

    # -------------------------------------------------------------------------
    # ПОВТОРИТЬ/УДВОИТЬ
    # -------------------------------------------------------------------------
    async def _repeat_last_bets(self, user_id: int, chat_id: int, message_or_call):
        """Повторяет последние ставки пользователя"""
        session = self.session_manager.get_session(chat_id)
        username = get_display_name(
            message_or_call.from_user if hasattr(message_or_call, 'from_user')
            else message_or_call
        )
        if user_id not in session.last_user_bets or not session.last_user_bets[user_id]:
            reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
            await reply_method("❌ Нет последних ставок для повторения")
            return

        last_bets = session.last_user_bets[user_id]
        if hasattr(message_or_call, 'message'):
            ok, result_msg, total = await self._place_multiple_bets(
                user_id, chat_id, last_bets, username, message_or_call.message
            )
        else:
            ok, result_msg, total = await self._place_multiple_bets(
                user_id, chat_id, last_bets, username, message_or_call
            )
        if not ok and hasattr(message_or_call, 'answer'):
            await message_or_call.answer(result_msg)

    async def _double_bets(self, user_id: int, chat_id: int, message_or_call):
        """Удваивает текущие ставки пользователя"""
        session = self.session_manager.get_session(chat_id)
        username = get_display_name(
            message_or_call.from_user if hasattr(message_or_call, 'from_user')
            else message_or_call
        )

        if user_id not in session.user_sessions or not session.user_sessions[user_id].has_bets:
            reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
            await reply_method("❌ Нет активных ставок для удвоения")
            return

        user_session = session.user_sessions[user_id]
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
                await reply_method("❌ Пользователь не найден")
                return

            # Получаем сумму для удвоения
            double_amount = user_session.total_amount

            # Проверяем достаточно ли средств для удвоения
            if double_amount > user.coins:
                reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
                await reply_method(
                    f"❌ Недостаточно средств для удвоения. Нужно: {double_amount}, есть: {user.coins}")
                return

            # СОХРАНЯЕМ текущие ставки перед очисткой
            current_bets = [(bet.amount, bet.type, bet.value) for bet in user_session.bets]

            # Создаем удвоенные ставки
            doubled_bets = [(bet.amount * 2, bet.type, bet.value) for bet in user_session.bets]

            # ВОЗВРАЩАЕМ текущие ставки на баланс перед установкой новых
            returned_amount = user_session.total_amount
            user_session.clear_bets()

            # Обновляем баланс - возвращаем старые ставки
            UserRepository.update_user_balance(db, user_id, user.coins + returned_amount)

            # Устанавливаем флаг удвоения
            session.is_doubling_operation = True

            # Формируем текст для отображения
            bet_display_values = [f"{amount} на {get_bet_display_value(bet_type, value)}"
                                  for amount, bet_type, value in doubled_bets]
            double_text = f"⚡ Удвоение ставок:\n" + "\n".join(bet_display_values)

            # Размещаем новые удвоенные ставки
            if hasattr(message_or_call, 'message'):
                ok, result_msg, total = await self._place_multiple_bets_silent(
                    user_id, chat_id, doubled_bets, username, message_or_call.message
                )
                if ok:
                    try:
                        msg = await message_or_call.message.answer(double_text, parse_mode="Markdown")
                        user_session = session.get_user_session(user_id, username)
                        user_session.bet_message_ids.append(msg.message_id)
                    except Exception as e:
                        logger.error(f"Ошибка при создании сообщения: {e}")
                else:
                    # Если не удалось поставить удвоенные ставки, возвращаем оригинальные
                    await self._place_multiple_bets_silent(
                        user_id, chat_id, current_bets, username, message_or_call.message
                    )
                    await message_or_call.answer(f"❌ {result_msg}")
            else:
                ok, result_msg, total = await self._place_multiple_bets_silent(
                    user_id, chat_id, doubled_bets, username, message_or_call
                )
                if ok:
                    try:
                        msg = await message_or_call.answer(double_text, parse_mode="Markdown")
                        user_session = session.get_user_session(user_id, username)
                        user_session.bet_message_ids.append(msg.message_id)
                    except Exception as e:
                        logger.error(f"Ошибка при создании сообщения: {e}")
                else:
                    # Если не удалось поставить удвоенные ставки, возвращаем оригинальные
                    await self._place_multiple_bets_silent(
                        user_id, chat_id, current_bets, username, message_or_call
                    )
                    await message_or_call.answer(result_msg)

    async def _place_multiple_bets_silent(self, user_id: int, chat_id: int, bets: List[Tuple[int, str, str]],
                                          username: str, reply_target: types.Message) -> Tuple[bool, str, int]:
        """Размещает несколько ставок без показа сообщения (для удвоения)"""
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return False, "❌ Сначала зарегистрируйтесь через /start", 0
            coins = user.coins
            session = self.session_manager.get_session(chat_id)
            user_session = session.get_user_session(user_id, username)
            successful_bets = []
            total_amount = 0
            for amount, bet_type, bet_value in bets:
                is_valid, error_msg = BetValidator.validate_bet(amount, coins, user_session.total_amount)
                if not is_valid:
                    return False, error_msg, 0
                bet = Bet(amount, bet_type, bet_value, username, user_id)
                if user_session.add_bet(bet):
                    coins -= amount
                    total_amount += amount
                    successful_bets.append(bet)
                    UserRepository.update_user_balance(db, user_id, coins)
                    UserRepository.update_max_bet(db, user_id, amount)

            if not successful_bets:
                return False, "❌ Не удалось разместить ни одну ставку", 0

            if not getattr(session, 'is_doubling_operation', False):
                session.last_user_bets[user_id] = bets
            session.is_doubling_operation = False
            return True, "", total_amount


# =============================================================================
# РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================================================
def register_roulette_handlers(dp):
    """Регистрирует обработчики рулетки"""
    handler = RouletteHandler()

    # Основные команды
    dp.register_message_handler(
        handler.show_balance,
        lambda m: m.text and m.text.strip().lower() in ["б", "баланс", "balance"]
    )
    dp.register_message_handler(
        handler.start_roulette,
        commands=["рулетка", "roulette"]
    )
    dp.register_message_handler(
        handler.start_roulette,
        lambda m: m.text and m.text.lower() == "рулетка"
    )
    dp.register_message_handler(
        handler.quick_start_roulette,
        lambda m: m.text and m.text.lower() in ["го", "крутить", "spin"]
    )

    # Команды управления ставками
    dp.register_message_handler(
        handler.clear_bets_command,
        lambda m: m.text and m.text.lower() in ["отмена", "очистить", "clear", "отменить"]
    )
    dp.register_message_handler(
        handler.show_my_bets,
        lambda m: m.text and m.text.lower() in ["ставки", "мои ставки", "bets"]
    )

    # Команды повторения и удвоения
    dp.register_message_handler(
        lambda m: handler._repeat_last_bets(m.from_user.id, m.chat.id, m),
        lambda m: m.text and m.text.lower() in ["повторить", "repeat", "репит"]
    )
    dp.register_message_handler(
        lambda m: handler._double_bets(m.from_user.id, m.chat.id, m),
        lambda m: m.text and m.text.lower() in ["удвоить", "удвой", "double", "дабл"]
    )

    # Команды логов
    dp.register_message_handler(
        lambda m: handler.show_logs_command(m, False),
        lambda m: m.text and m.text.lower() == "лог"
    )
    dp.register_message_handler(
        lambda m: handler.show_logs_command(m, True),
        lambda m: m.text and m.text.lower() == "!лог"
    )

    # Текстовые ставки
    BET_PATTERNS = [
        r'^\d+\s*[kк]?\s+',  # Сообщения, начинающиеся с чисел
        r'\d+\s*-\s*\d+',    # Сообщения с диапазонами
    ]
    BET_KEYWORDS = ["на", "ставка", "ставку", "ставки", "красн", "черн", "зелен", "кр ", "ч ", "з "]
    VABANK_KEYWORDS = ["ва-банк", "вабанк", "ва банк"]
    dp.register_message_handler(
        handler.place_bet,
        lambda m: m.text and (
                any(word in m.text.lower() for word in BET_KEYWORDS) or
                any(m.text.lower().startswith(keyword) for keyword in VABANK_KEYWORDS) or
                any(re.search(pattern, m.text.lower()) for pattern in BET_PATTERNS)
        ),
        content_types=["text"],
        state="*"
    )

    # Обработчики callback
    dp.register_callback_query_handler(
        handler.handle_callback,
        lambda c: c.data and any(c.data.startswith(prefix) for prefix in ["bet:", "quick:", "action:"])
    )

    return handler