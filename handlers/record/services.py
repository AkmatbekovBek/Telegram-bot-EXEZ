import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional
import pytz
from aiogram import Bot
from .record_core import RecordCore, RecordErrors


class RecordService:
    """Сервис для работы с рекордами и балансами"""

    def __init__(self, record_core: RecordCore):
        self.core = record_core
        self.logger = logging.getLogger(__name__)
        self._reset_task = None
        self._start_daily_reset()

    def _start_daily_reset(self):
        """Запускает фоновую задачу для сброса рекордов дня в 00:00 МСК"""
        async def reset_loop():
            while True:
                try:
                    # Таймзона Москвы
                    msk_tz = pytz.timezone('Europe/Moscow')
                    now = datetime.now(msk_tz)
                    target_time = time(0, 0)  # 00:00 МСК
                    
                    # Вычисляем время до следующей полночи
                    if now.time() > target_time:
                        next_day = now.date() + timedelta(days=1)
                    else:
                        next_day = now.date()
                    
                    next_reset = msk_tz.localize(
                        datetime.combine(next_day, target_time)
                    )
                    
                    seconds_until_reset = (next_reset - now).total_seconds()
                    
                    self.logger.info(f"⏰ Следующий сброс РЕКОРДОВ ДНЯ через {seconds_until_reset:.0f} секунд")
                    await asyncio.sleep(seconds_until_reset)
                    
                    # Выполняем сброс ТОЛЬКО рекордов дня
                    await self.reset_daily_records()
                    
                except Exception as e:
                    self.logger.error(f"Ошибка в цикле сброса рекордов: {e}")
                    await asyncio.sleep(3600)  # Ждем час при ошибке
        
        # Запускаем фоновую задачу
        self._reset_task = asyncio.create_task(reset_loop())

    # handlers/record/services.py

    async def reset_daily_records(self, bot: Bot = None):
        """Сбрасывает только рекорды дня (выигрыши и проигрыши), НЕ данные профиля"""
        try:
            self.logger.info("🎯 Начинаем сброс ВСЕХ РЕКОРДОВ ДНЯ...")

            with self.core.db_session() as db:
                from database.models import DailyRecord, DailyLossRecord

                # 1. Удаляем ВСЕ записи DailyRecord (рекорды выигрышей за день)
                deleted_wins = db.query(DailyRecord).delete()

                # 2. Удаляем ВСЕ записи DailyLossRecord (рекорды проигрышей за день)
                deleted_losses = db.query(DailyLossRecord).delete()

                # 3. НЕ сбрасываем defeat_coins в профиле - это общая статистика!
                #    defeat_coins остается как общая сумма всех проигрышей пользователя

                db.commit()

                self.logger.info(
                    f"✅ Все рекорды дня сброшены! Удалено: {deleted_wins} выигрышей, {deleted_losses} проигрышей")

                # Уведомляем в консоль
                print("🔄 ВСЕ РЕКОРДЫ ДНЯ ОБНУЛЕНЫ! (00:00 МСК)")
                print(f"📊 Удалено записей выигрышей: {deleted_wins}")
                print(f"📊 Удалено записей проигрышей: {deleted_losses}")
                print("💰 Балансы пользователей сохранены")
                print("📈 Общая статистика проигрышей (defeat_coins) сохранена")

                return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка при сбросе рекордов дня: {e}")
            return False

    async def register_user_for_chat_top(self, user_id: int, chat_id: int, username: str = None,
                                         first_name: str = None) -> bool:
        """Регистрирует пользователя в топе чата только при запросе топа (не при каждом сообщении)"""
        try:
            # Добавляем небольшую задержку для предотвращения перегрузки
            await asyncio.sleep(0.01)

            def sync_register():
                with self.core.db_session() as db:
                    from database.models import TelegramUser, UserChat
                    from database.crud import UserRepository

                    # 1. Сначала убедимся, что пользователь есть в основной таблице
                    user = UserRepository.get_user_by_telegram_id(db, user_id)

                    created_user = False
                    if not user:
                        user = UserRepository.create_user(
                            db=db,
                            telegram_id=user_id,
                            username=username or "",
                            first_name=first_name or ""
                        )
                        created_user = True
                    else:
                        # Обновляем username/first_name если они изменились
                        if username and user.username != username:
                            user.username = username
                        if first_name and user.first_name != first_name:
                            user.first_name = first_name

                    # 2. Проверяем UserChat
                    user_chat = db.query(UserChat).filter(
                        UserChat.user_id == user_id,
                        UserChat.chat_id == chat_id
                    ).first()

                    created_user_chat = False
                    if not user_chat:
                        user_chat = UserChat(
                            user_id=user_id,
                            chat_id=chat_id
                        )
                        db.add(user_chat)
                        created_user_chat = True

                    # 3. Логируем только при реальных изменениях
                    if created_user:
                        self.logger.info(f"✅ Создан пользователь {user_id} для топа чата")
                    if created_user_chat:
                        self.logger.info(f"✅ Добавлен в топ чата {chat_id}")

                    return True

            # Запускаем в пуле потоков
            await asyncio.get_event_loop().run_in_executor(None, sync_register)
            return True

        except Exception as e:
            self.logger.error(f"Error in register_user_for_chat_top: {e}")
            return False

    async def add_win_record(self, user_id: int, amount: int, chat_id: int = None,
                             username: str = None, first_name: str = None) -> bool:
        """Добавляет или обновляет рекорд выигрыша (только если сумма больше текущего рекорда)"""
        try:
            if amount <= 0:
                self.logger.warning(f"Attempt to add non-positive win record: {amount}")
                return False

            if chat_id is None:
                chat_id = 0
            elif isinstance(chat_id, str):
                try:
                    chat_id = int(chat_id)
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid chat_id: {chat_id}, using 0")
                    chat_id = 0

            # Задержка для предотвращения перегрузки
            await asyncio.sleep(0.05)

            def sync_add_win():
                with self.core.db_session() as db:
                    from database.crud import DailyRecordRepository
                    from datetime import date
                    from database.models import DailyRecord

                    today = date.today()

                    # Получаем текущий рекорд В ТЕКУЩЕЙ СЕССИИ
                    current_record = (db.query(DailyRecord)
                                      .filter(
                        DailyRecord.user_id == user_id,
                        DailyRecord.record_date == today
                    )
                                      .order_by(DailyRecord.amount.desc())
                                      .first())

                    if current_record and amount <= current_record.amount:
                        self.logger.info(
                            f"📊 Рекорд выигрыша не обновлен: текущий {current_record.amount} >= новый {amount}")
                        return True

                    # Создаем новый рекорд
                    record = DailyRecordRepository.add_or_update_daily_record(
                        db=db,
                        user_id=user_id,
                        username=username or "",
                        first_name=first_name or "",
                        amount=amount,
                        chat_id=chat_id
                    )

                    if record:
                        if current_record:
                            self.logger.info(
                                f"🎯 Рекорд выигрыша УЛУЧШЕН для пользователя {user_id}: {current_record.amount} -> {amount} монет")
                        else:
                            self.logger.info(f"🎯 Новый рекорд выигрыша для пользователя {user_id}: {amount} монет")
                        return True
                    else:
                        self.logger.error(f"❌ Не удалось обновить рекорд для пользователя {user_id}")
                        return False

            # Запускаем в пуле потоков
            await asyncio.get_event_loop().run_in_executor(None, sync_add_win)
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка в add_win_record: {e}")
            return False

    async def add_loss_record(self, user_id: int, loss_amount: int, username: str = None,
                              first_name: str = None, chat_id: int = 0) -> bool:
        """Добавляет запись о проигрыше в DailyLossRecord"""
        try:
            if loss_amount <= 0:
                self.logger.warning(f"Attempt to add non-positive loss record: {loss_amount}")
                return False

            # Задержка для предотвращения перегрузки
            await asyncio.sleep(0.05)

            def sync_add_loss():
                with self.core.db_session() as db:
                    from database.crud import DailyRecordRepository, UserRepository
                    from datetime import date
                    from database.models import TelegramUser, DailyLossRecord

                    today = date.today()

                    # 1. Сначала убеждаемся, что пользователь существует
                    user = UserRepository.get_user_by_telegram_id(db, user_id)
                    if not user:
                        # Создаем пользователя
                        user = TelegramUser(
                            telegram_id=user_id,
                            username=username or "",
                            first_name=first_name or "",
                            coins=5000,
                            win_coins=0,
                            defeat_coins=loss_amount,
                            max_win_coins=0,
                            min_win_coins=0,
                            max_bet=0,
                            win_games=0,
                            lose_games=1
                        )
                        db.add(user)
                    else:
                        # Обновляем defeat_coins
                        user.defeat_coins = (user.defeat_coins or 0) + loss_amount

                    # 2. Получаем текущий рекорд проигрыша
                    current_record = (db.query(DailyLossRecord)
                                      .filter(
                        DailyLossRecord.user_id == user_id,
                        DailyLossRecord.record_date == today
                    )
                                      .order_by(DailyLossRecord.amount.desc())
                                      .first())

                    if current_record and loss_amount <= current_record.amount:
                        self.logger.info(
                            f"📊 Рекорд проигрыша не обновлен: текущий {current_record.amount} >= новый {loss_amount}")
                        return True

                    # 3. Создаем новый рекорд
                    new_record = DailyLossRecord(
                        user_id=user_id,
                        username=username or user.username or "",
                        first_name=first_name or user.first_name or "",
                        amount=loss_amount,
                        record_date=today,
                        chat_id=chat_id
                    )
                    db.add(new_record)

                    self.logger.info(f"💸 Рекорд проигрыша для пользователя {user_id}: {loss_amount} монет")
                    return True

            # Запускаем в пуле потоков
            await asyncio.get_event_loop().run_in_executor(None, sync_add_loss)
            return True

        except Exception as e:
            self.logger.error(f"Error in add_loss_record: {e}")
            return False

    async def update_user_balance(self, user_id: int, amount: int, username: str = None,
                                  first_name: str = None) -> bool:
        """Обновляет баланс пользователя (отдельно от рекордов)"""
        try:
            await self.core.ensure_user_registered(user_id, 0, username, first_name)

            with self.core.db_session() as db:
                from database.crud import UserRepository

                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if user:
                    new_balance = user.coins + amount
                    if new_balance < 0:
                        self.logger.warning(f"Negative balance prevented for user {user_id}")
                        return False

                    user.coins = new_balance
                    db.commit()
                    self.logger.info(f"Balance updated for user {user_id}: {amount} -> {new_balance} coins")
                    return True
                return False

        except Exception as e:
            self.logger.error(f"Error in update_user_balance: {e}")
            return False

    def get_daily_record_stats(self, user_id: int) -> dict:
        """Получает статистику рекордов пользователя за сегодня"""
        with self.core.db_session() as db:
            from database.crud import UserRepository

            user = UserRepository.get_user_by_telegram_id(db, user_id)
            win_record = self.core._get_user_daily_record_global(user_id)
            loss_record = self.core._get_user_loss_record(user_id)

            win_rank = self.core._get_user_global_rank_today(user_id)
            loss_rank = self.core._get_user_loss_rank_today(user_id)

            return {
                'win_amount': win_record.amount if win_record else 0,
                'win_rank': win_rank,
                'loss_amount': loss_record.defeat_coins if loss_record else 0,
                'loss_rank': loss_rank,
                'current_balance': user.coins if user else 0
            }

    def get_user_position_in_chat(self, user_id: int, chat_id: int) -> dict:
        """Получает позицию пользователя в топе чата"""
        with self.core.db_session() as db:
            from database.crud import ChatRepository, UserRepository

            user_position = ChatRepository.get_user_rank_in_chat(db, chat_id, user_id)
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            user_coins = user.coins if user else 0

            top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, 5)

            return {
                'position': user_position,
                'coins': user_coins,
                'top_5': top_users
            }