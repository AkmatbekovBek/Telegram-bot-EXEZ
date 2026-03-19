# handlers/police/handlers.py
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from aiogram import types
from database import get_db
from database.crud import PoliceRepository, ShopRepository, UserRepository
from handlers.police.service import PoliceService

logger = logging.getLogger(__name__)


class PoliceHandlers:
    def __init__(self):
        self.service = PoliceService()
        self.logger = logger

    @staticmethod
    def normalize_cmd(text: str) -> str:
        """Нормализует команду, обрабатывая пустые строки и русские команды"""
        if not text or not text.strip():
            return ""

        # Убираем символы команд и упоминания
        text = re.sub(r"^[/!]", "", text)
        text = re.sub(r"@[\w_]+$", "", text)

        # Разбиваем на слова и берем первое, если оно есть
        parts = text.strip().lower().split()
        return parts[0] if parts else ""

    @staticmethod
    def is_arrest_cmd(msg: types.Message) -> bool:
        """Проверяет, является ли сообщение командой ареста"""
        cmd = PoliceHandlers.normalize_cmd(msg.text)
        return cmd in ["арест", "!арест", "/арест", "/arrest", "арестовать", "!арестовать", "/арестовать", "arreste"]

    @staticmethod
    def is_check_cmd(msg: types.Message) -> bool:
        """Проверяет, является ли сообщение командой проверки"""
        cmd = PoliceHandlers.normalize_cmd(msg.text)
        return cmd in ["проверить", "!проверить", "/проверить", "/check", "арест?", "!арест?"]

    @staticmethod
    def is_unarrest_cmd(msg: types.Message) -> bool:
        """Проверяет, является ли сообщение командой снятия ареста"""
        cmd = PoliceHandlers.normalize_cmd(msg.text)
        return cmd in ["разжаловать", "!разжаловать", "/разжаловать", "/unarrest", "снятьарест"]

    @staticmethod
    def is_stats_cmd(msg: types.Message) -> bool:
        """Проверяет, является ли сообщение командой статистики"""
        cmd = PoliceHandlers.normalize_cmd(msg.text)
        return cmd in ["полиция", "!полиция", "/полиция", "/police", "статистика"]

    def _format_time_delta(self, delta: timedelta) -> str:
        """Форматирует временной интервал в читаемый вид"""
        total_seconds = int(delta.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}д")
        if hours > 0:
            parts.append(f"{hours}ч")
        if minutes > 0:
            parts.append(f"{minutes}м")

        return " ".join(parts) if parts else "0м"

    def _format_time_left(self, minutes: int) -> str:
        """Форматирует оставшееся время ареста"""
        if minutes >= 1440:  # 24 часа
            days = minutes // 1440
            hours = (minutes % 1440) // 60
            if hours > 0:
                return f"{days}д {hours}ч"
            return f"{days}д"
        elif minutes >= 60:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes > 0:
                return f"{hours}ч {remaining_minutes}м"
            return f"{hours}ч"
        else:
            return f"{minutes}м"

    async def _get_user_display_info(self, user_id: int, db) -> Tuple[str, bool]:
        """Получает информацию о пользователе для отображения"""
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                # Формируем полное имя из first_name и last_name
                user_name_parts = []
                if user.first_name:
                    user_name_parts.append(user.first_name)
                if user.last_name:
                    user_name_parts.append(user.last_name)

                user_name = ' '.join(user_name_parts) if user_name_parts else "Пользователь"

                # Если есть username, добавляем его для идентификации
                if user.username:
                    user_name = f"{user_name} (@{user.username})"
            else:
                user_name = "Неизвестный пользователь"

            is_thief = self.service.check_thief_permission(user_id)
            return user_name, is_thief

        except Exception as e:
            self.logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            return "Неизвестный пользователь", False

    async def arrest_user(self, message: types.Message):
        """Обработчик команды ареста"""
        self.logger.info(f"🔍 arrest_user вызван: '{message.text}' от пользователя {message.from_user.id}")

        try:
            police = message.from_user
            if not self.service.check_police_permission(police.id):
                await message.reply("👮 Только <b>Полицейские</b> могут арестовывать!", parse_mode="HTML")
                return

            if not message.reply_to_message:
                await message.reply("❗ Ответь на сообщение вора.")
                return

            target = message.reply_to_message.from_user
            bot = await message.bot.get_me()

            # Получаем отображаемые имена
            db = next(get_db())
            try:
                police_name, _ = await self._get_user_display_info(police.id, db)
                target_name, is_thief = await self._get_user_display_info(target.id, db)
            finally:
                db.close()

            # Проверки валидности цели
            if police.id == target.id:
                await message.reply("🚫 Нельзя арестовать себя!")
                return
            if target.id == bot.id:
                await message.reply("🤖 Бот вне закона!")
                return
            if not is_thief:
                await message.reply("🎭 Цель не является <b>Вором в законе</b>!", parse_mode="HTML")
                return

            # Проверка кулдауна полицейского
            can, cooldown_end = self.service.check_police_cooldown(police.id)
            if not can:
                left = cooldown_end - datetime.now()
                time_left_str = self._format_time_delta(left)
                await message.reply(
                    f"⏳ <b>Кулдаун полицейского</b>\n\n"
                    f"👮 Полицейский: {police_name}\n"
                    f"⏰ Следующий арест через: {time_left_str}\n"
                    f"🕐 Время: {cooldown_end.strftime('%H:%M')}",
                    parse_mode="HTML"
                )
                return

            # Парсинг времени ареста
            minutes = self.service.parse_arrest_time(message.text)
            success, msg = self.service.arrest_user(police.id, target.id, minutes)

            if success:
                release_time = datetime.now() + timedelta(minutes=minutes)
                time_str = self._format_time_left(minutes)

                await message.reply(
                    f"🚔 <b>АРЕСТ ВОРА В ЗАКОНЕ</b>\n\n"
                    f"👮 Полицейский: {police_name}\n"
                    f"🎯 Вор в законе: {target_name}\n"
                    f"⏰ Срок: {time_str}\n"
                    f"🕐 Освобождение: {release_time.strftime('%H:%M')}\n\n"
                    f"⏳ Следующий арест через 3 часа",
                    parse_mode="HTML"
                )
                self.logger.info(f"✅ Полицейский {police.id} арестовал вора {target.id} на {minutes} минут")
            else:
                await message.reply(f"❌ {msg}")

        except Exception as e:
            self.logger.error(f"💥 Ошибка в arrest_user: {e}")
            await message.reply("🚨 Внутренняя ошибка при аресте.")

    async def check_arrest(self, message: types.Message):
        """Обработчик команды проверки ареста"""
        try:
            target = message.reply_to_message.from_user if message.reply_to_message else message.from_user

            db = next(get_db())
            try:
                # Получаем сырую запись об аресте без авто-очистки
                from database.models import UserArrest
                arrest = db.query(UserArrest).filter(UserArrest.user_id == target.id).first()

                user_name, is_thief = await self._get_user_display_info(target.id, db)
                user_type = "🎭 Вор в законе" if is_thief else "👤 Пользователь"

                if arrest and arrest.release_time > datetime.now():
                    time_left = arrest.release_time - datetime.now()
                    time_left_str = self._format_time_delta(time_left)

                    # Получаем информацию о полицейском
                    police_name, _ = await self._get_user_display_info(arrest.arrested_by, db)

                    status_msg = (
                        f"🔒 <b>СТАТУС: АРЕСТОВАН</b>\n\n"
                        f"{user_type}: {user_name}\n"
                        f"👮 Арестовал: {police_name}\n"
                        f"⏳ Освобождение через: {time_left_str}\n"
                        f"🕐 Время: {arrest.release_time.strftime('%H:%M')}\n"
                        f"📅 Дата: {arrest.release_time.strftime('%d.%m.%Y')}"
                    )
                else:
                    # Очищаем истекший арест
                    if arrest:
                        PoliceRepository.unarrest_user(db, target.id)
                        db.commit()

                    status_msg = (
                        f"✅ <b>СТАТУС: СВОБОДЕН</b>\n\n"
                        f"{user_type}: {user_name}\n"
                        f"🎉 Не арестован и может свободно действовать!"
                    )

                await message.reply(status_msg, parse_mode="HTML")

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Ошибка в check_arrest: {e}")
            await message.reply("❌ Ошибка при проверке ареста.")

    async def unarrest_user(self, message: types.Message):
        """Обработчик команды снятия ареста"""
        try:
            if not self.service.check_police_permission(message.from_user.id):
                await message.reply("👮 Только <b>Полицейские</b> могут снимать аресты!", parse_mode="HTML")
                return

            if not message.reply_to_message:
                await message.reply("❗ Ответь на сообщение пользователя, чтобы снять арест.")
                return

            police = message.from_user
            target = message.reply_to_message.from_user

            db = next(get_db())
            try:
                # Проверяем арест
                arrest = PoliceRepository.get_user_arrest(db, target.id)

                if not arrest:
                    await message.reply(f"ℹ️ {target.full_name} не арестован.")
                    return

                # Снимаем арест
                result = PoliceRepository.unarrest_user(db, target.id)
                db.commit()

                if result:
                    await message.reply(
                        f"✅ <b>СНЯТИЕ АРЕСТА</b>\n\n"
                        f"👮 Полицейский: {police.full_name}\n"
                        f"🎯 Пользователь: {target.full_name}\n"
                        f"🎉 Арест снят!",
                        parse_mode="HTML"
                    )
                    self.logger.info(f"👮 Полицейский {police.id} снял арест с {target.id}")
                else:
                    await message.reply("❌ Не удалось снять арест.")

            except Exception as e:
                db.rollback()
                self.logger.error(f"Ошибка БД в unarrest_user: {e}")
                await message.reply("❌ Ошибка при снятии ареста.")
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Ошибка в unarrest_user: {e}")
            await message.reply("❌ Ошибка при обработке команды.")

    async def police_stats(self, message: types.Message):
        """Обработчик команды статистики полицейского"""
        try:
            user_id = message.from_user.id

            if not self.service.check_police_permission(user_id):
                await message.reply("👮 Только <b>Полицейские</b> могут просматривать статистику!", parse_mode="HTML")
                return

            db = next(get_db())
            try:
                # Получаем активные аресты
                active_arrests = PoliceRepository.get_all_active_arrests(db)

                # Аресты этого полицейского
                my_arrests = PoliceRepository.get_arrests_by_police(db, user_id)
                my_active_arrests = [a for a in my_arrests if a.release_time > datetime.now()]

                # Подсчитываем только воров
                thieves_arrested = 0
                for arrest in my_active_arrests:
                    if self.service.check_thief_permission(arrest.user_id):
                        thieves_arrested += 1

                # Проверяем кулдаун
                can_arrest, cooldown_end = self.service.check_police_cooldown(user_id)
                cooldown_info = ""

                if not can_arrest and cooldown_end:
                    time_left = cooldown_end - datetime.now()
                    time_left_str = self._format_time_delta(time_left)
                    cooldown_info = f"⏳ Следующий арест через: {time_left_str}\n"
                else:
                    cooldown_info = "✅ Готов к следующему аресту\n"

                # Формируем ответ
                result = (
                    f"👮 <b>СТАТИСТИКА ПОЛИЦЕЙСКОГО</b>\n\n"
                    f"📛 Имя: {message.from_user.full_name}\n"
                    f"🔒 Арестовано воров: {thieves_arrested}\n"
                    f"🔒 Всего активных арестов: {len(active_arrests)}\n"
                    f"{cooldown_info}"
                )

                # Добавляем список текущих арестов
                if my_active_arrests:
                    result += "\n🔒 <b>Мои текущие аресты:</b>\n"
                    count = 0
                    for arrest in my_active_arrests:
                        if self.service.check_thief_permission(arrest.user_id):
                            user_name, _ = await self._get_user_display_info(arrest.user_id, db)
                            time_left = arrest.release_time - datetime.now()
                            time_left_str = self._format_time_delta(time_left)
                            result += f"• {user_name} - {time_left_str}\n"
                            count += 1
                            if count >= 5:  # Ограничиваем список
                                break

                await message.reply(result, parse_mode="HTML")

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Ошибка в police_stats: {e}")
            await message.reply("❌ Ошибка при получении статистики.")


def register_police_handlers(dp):
    """Регистрация обработчиков полиции"""
    handler = PoliceHandlers()

    dp.register_message_handler(handler.arrest_user, PoliceHandlers.is_arrest_cmd, state="*")
    dp.register_message_handler(handler.check_arrest, PoliceHandlers.is_check_cmd, state="*")
    dp.register_message_handler(handler.unarrest_user, PoliceHandlers.is_unarrest_cmd, state="*")
    dp.register_message_handler(handler.police_stats, PoliceHandlers.is_stats_cmd, state="*")

    logger.info("✅ Police handlers registered")