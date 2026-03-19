# handlers/thief/handlers.py
import re
import random
import logging
from datetime import datetime, timedelta
from aiogram import types
from handlers.thief.service import ThiefService

logger = logging.getLogger(__name__)


def normalize_cmd(text: str) -> str:
    """Нормализует команду, убирает лишние пробелы и приводит к нижнему регистру"""
    if not text or not text.strip():
        return ""

    # Убираем символы команд и упоминания
    text = re.sub(r"^[/!]", "", text)
    text = re.sub(r"@[\w_]+$", "", text)

    # Разбиваем на слова и берем первое, если оно есть
    parts = text.strip().lower().split()
    return parts[0] if parts else ""


def is_rob_cmd(msg: types.Message):
    """Проверяет, является ли сообщение командой кражи"""
    if not msg.text or not msg.text.strip():
        return False

    normalized_cmd = normalize_cmd(msg.text)
    return normalized_cmd in ["украсть", "ограбить", "воруй", "красть", "steal"]


def is_steal_prefix_cmd(msg: types.Message):
    """Проверяет команды с префиксом '-' (например: '-5000')"""
    if not msg.text or not msg.text.strip():
        return False

    text = msg.text.strip()
    return text.startswith('-') and len(text) > 1 and text[1:].isdigit()


def is_thief_stats_cmd(msg: types.Message):
    """Проверяет команды статистики краж"""
    if not msg.text or not msg.text.strip():
        return False

    normalized_cmd = normalize_cmd(msg.text)
    return normalized_cmd in ["кражи", "thief_stats", "статистика"]


async def rob_user(message: types.Message):
    """Основной обработчик кражи"""
    try:
        thief = message.from_user
        if not ThiefService.check_thief_permission(thief.id):
            await message.reply("🎭 Только <b>Воры в законе</b> могут красть!", parse_mode="HTML")
            return

        if not message.reply_to_message:
            await message.reply("❗ Ответь на сообщение жертвы.")
            return

        victim = message.reply_to_message.from_user
        bot = await message.bot.get_me()

        if victim.id == bot.id:
            await message.reply("🤖 У бота нет денег.")
            return

        if thief.id == victim.id:
            await message.reply("🚫 Нельзя грабить себя")
            return

        # Проверяем, не является ли жертва вором
        if ThiefService.check_thief_permission(victim.id):
            thief_name = thief.full_name or thief.first_name or thief.username or "Неизвестный вор"
            await message.reply(f"🎭 Нельзя грабить другого вора в законе!")
            return

        # Парсим сумму из сообщения
        steal_amount = ThiefService.parse_steal_amount(message.text)

        success, msg_text, amount = await ThiefService.rob_user(thief.id, victim.id, steal_amount)

        if success:
            # Определяем имена
            thief_name = thief.username or thief.first_name or "Неизвестный вор"
            victim_name = victim.username or victim.first_name or "Неизвестная жертва"

            await message.reply(
                f"👤 {thief_name} незаметно украл у {victim_name} 💸 +{amount:,}"
            )
        else:
            await message.reply(f"❌ {msg_text}")

    except Exception as e:
        logger.error(f"Error in rob_user: {e}")
        await message.reply("🚨 Внутренняя ошибка кражи.")


async def steal_with_prefix(message: types.Message):
    """Обработчик для команд с префиксом '-'"""
    try:
        thief = message.from_user
        if not ThiefService.check_thief_permission(thief.id):
            await message.reply("🎭 Только <b>Воры в законе</b> могут красть!", parse_mode="HTML")
            return

        if not message.reply_to_message:
            await message.reply("❗ Ответь на сообщение жертвы.")
            return

        victim = message.reply_to_message.from_user
        bot = await message.bot.get_me()

        if victim.id == bot.id:
            await message.reply("🤖 У бота нет денег.")
            return

        if thief.id == victim.id:
            await message.reply("🚫 Нельзя грабить себя")
            return

        # Проверяем, не является ли жертва вором
        if ThiefService.check_thief_permission(victim.id):
            await message.reply(f"🎭 Нельзя грабить другого вора в законе!")
            return

        # Парсим сумму с префиксом '-'
        steal_amount = ThiefService.parse_steal_amount(message.text)

        if steal_amount == 0:
            await message.reply(f"❌ Минимальная сумма для кражи: {ThiefService.MIN_STEAL_AMOUNT:,} монет!")
            return

        success, msg_text, amount = await ThiefService.rob_user(thief.id, victim.id, steal_amount)

        if success:
            thief_name = thief.username or thief.first_name or "Неизвестный вор"
            victim_name = victim.username or victim.first_name or "Неизвестная жертва"

            await message.reply(
                f"👤 {thief_name} незаметно украл у {victim_name} 💸 +{amount:,}"
            )
        else:
            await message.reply(f"❌ {msg_text}")

    except Exception as e:
        logger.error(f"Error in steal_with_prefix: {e}")
        await message.reply("🚨 Внутренняя ошибка кражи.")


async def thief_stats(message: types.Message):
    """Показывает статистику по кражам"""
    try:
        user_id = message.from_user.id

        if not ThiefService.check_thief_permission(user_id):
            await message.reply("🎭 Только <b>Воры в законе</b> могут просматривать статистику!", parse_mode="HTML")
            return

        stats = await ThiefService.get_thief_stats(user_id)

        result = f"📊 <b>Статистика кражей {message.from_user.full_name}</b>\n\n"
        result += f"✅ Успешных краж: {stats['successful_steals']}\n"
        result += f"❌ Неудачных попыток: {stats['failed_steals']}\n"
        result += f"💰 Всего украдено: {stats['total_stolen']:,} монет\n\n"

        if stats['last_steal_time']:
            last_steal = stats['last_steal_time'].strftime("%d.%m.%Y %H:%M")
            result += f"⏰ Последняя кража: {last_steal}\n"
        else:
            result += "⏰ Последняя кража: никогда\n"

        # Проверяем кулдаун
        can_steal, cooldown_info = await ThiefService.check_steal_cooldown(user_id)
        if not can_steal and cooldown_info:
            result += f"⏳ До следующей кражи: {cooldown_info}\n"

        result += f"\n🎯 <i>Удачи в следующих кражах!</i>"

        await message.reply(result, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in thief_stats: {e}")
        await message.reply("❌ Ошибка при получении статистики.")


def register_thief_handlers(dp):
    """Регистрация обработчиков для вора"""
    # Основные команды кражи
    dp.register_message_handler(rob_user, is_rob_cmd, state="*")

    # Команды с префиксом '-'
    dp.register_message_handler(steal_with_prefix, is_steal_prefix_cmd, state="*")

    # Статистика
    dp.register_message_handler(thief_stats, is_thief_stats_cmd, state="*")

    logger.info("✅ Обработчики 'кража' зарегистрированы")