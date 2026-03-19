# handlers/donate/bonus_handler.py

import logging
from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .bonus import BonusManager
from .config import SUBSCRIPTION_BONUS_AMOUNT, CHANNEL_USERNAME

logger = logging.getLogger(__name__)


async def cmd_bonus(message: types.Message):
    """Команда /bonus"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton(text="📢 Бонус за подписку", callback_data="subscription_bonus")],
        [InlineKeyboardButton(text="👑 Бонусы за привилегии", callback_data="privilege_bonus")]
    ])

    await message.answer(
        "🎁 **Доступные бонусы:**\n\n"
        "• 🎁 Ежедневный бонус - получайте каждый день\n"
        f"• 📢 Бонус за подписку - {SUBSCRIPTION_BONUS_AMOUNT} монет за подписку на канал\n"
        "• 👑 Бонусы за привилегии - дополнительные награды",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def daily_bonus_callback(callback: types.CallbackQuery):
    """Обработчик ежедневного бонуса"""
    await callback.answer()

    bonus_manager = BonusManager()
    result = await bonus_manager.claim_daily_bonus(callback.from_user.id)

    if result["success"]:
        bonuses_text = []
        if "daily" in result.get("bonuses_claimed", []):
            bonuses_text.append("🎁 Базовый бонус")
        if result.get("has_thief"):
            bonuses_text.append("🦹 Бонус вора")
        if result.get("has_police"):
            bonuses_text.append("👮 Бонус полиции")

        bonuses_list = "\n".join(bonuses_text)

        await callback.message.edit_text(
            f"🎉 **Вы получили бонус!**\n\n"
            f"💰 **Сумма:** {result['bonus_amount']} монет\n"
            f"📋 **Полученные бонусы:**\n{bonuses_list}\n\n"
            "Возвращайтесь завтра за новым бонусом! 🎁",
            parse_mode="Markdown"
        )
    else:
        if not result.get("available"):
            hours = result.get("hours_left", 0)
            minutes = result.get("minutes_left", 0)

            if hours > 0:
                time_text = f"{hours} часов {minutes} минут"
            else:
                time_text = f"{minutes} минут"

            await callback.message.edit_text(
                f"⏳ **Бонус еще не доступен**\n\n"
                f"Вы сможете получить бонус через: **{time_text}**\n\n"
                "Не пропустите свой шанс получить награду! 🎁",
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                f"❌ **Ошибка:** {result.get('error', 'Неизвестная ошибка')}"
            )


async def subscription_bonus_callback(callback: types.CallbackQuery):
    """Обработчик кнопки бонуса за подписку"""
    await callback.answer()

    from .subscription_handler import cmd_subscribe
    await cmd_subscribe(callback.message)


async def privilege_bonus_callback(callback: types.CallbackQuery):
    """Обработчик бонусов за привилегии"""
    await callback.answer()

    bonus_manager = BonusManager()
    result = await bonus_manager.claim_daily_bonus(callback.from_user.id)

    if result["success"]:
        bonuses_text = []
        total_amount = 0

        if "daily" in result.get("bonuses_claimed", []):
            bonuses_text.append("🎁 Базовый бонус (500 монет)")
            total_amount += 500

        if result.get("has_thief"):
            bonuses_text.append("🦹 Бонус вора (200 монет)")
            total_amount += 200

        if result.get("has_police"):
            bonuses_text.append("👮 Бонус полиции (200 монет)")
            total_amount += 200

        bonuses_list = "\n".join(bonuses_text)

        await callback.message.edit_text(
            f"👑 **Бонусы за привилегии**\n\n"
            f"💰 **Итоговая сумма:** {total_amount} монет\n\n"
            f"📋 **Полученные бонусы:**\n{bonuses_list}\n\n"
            "Привилегии дают дополнительные награды каждый день!",
            parse_mode="Markdown"
        )
    else:
        if not result.get("available"):
            hours = result.get("hours_left", 0)
            minutes = result.get("minutes_left", 0)

            if hours > 0:
                time_text = f"{hours} часов {minutes} минут"
            else:
                time_text = f"{minutes} минут"

            await callback.message.edit_text(
                f"⏳ **Бонусы за привилегии еще не доступны**\n\n"
                f"Вы сможете получить бонусы через: **{time_text}**\n\n"
                f"**Ваши привилегии:**\n"
                f"🦹 Вор: {'✅' if result.get('has_thief') else '❌'}\n"
                f"👮 Полиция: {'✅' if result.get('has_police') else '❌'}",
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                f"❌ **Ошибка:** {result.get('error', 'Неизвестная ошибка')}\n\n"
                f"**Ваши привилегии:**\n"
                f"🦹 Вор: {'✅' if result.get('has_thief') else '❌'}\n"
                f"👮 Полиция: {'✅' if result.get('has_police') else '❌'}",
                parse_mode="Markdown"
            )


def register_bonus_handlers(dp: Dispatcher):
    """Регистрация хендлеров бонусов"""
    dp.register_message_handler(cmd_bonus, commands=["bonus", "бонус"])
    dp.register_callback_query_handler(daily_bonus_callback, lambda c: c.data == "daily_bonus")
    dp.register_callback_query_handler(subscription_bonus_callback, lambda c: c.data == "subscription_bonus")
    dp.register_callback_query_handler(privilege_bonus_callback, lambda c: c.data == "privilege_bonus")
    logger.info("✅ Хендлеры бонусов зарегистрированы")