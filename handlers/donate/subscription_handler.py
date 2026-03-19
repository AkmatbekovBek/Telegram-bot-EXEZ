# handlers/donate/subscription_handler.py

import logging
from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .bonus import BonusManager
from .config import CHANNEL_USERNAME, CHANNEL_LINK, SUBSCRIPTION_BONUS_AMOUNT, BONUS_AMOUNT, THIEF_BONUS_AMOUNT, \
    POLICE_BONUS_AMOUNT

logger = logging.getLogger(__name__)


async def cmd_subscribe(message: types.Message):
    """Команда /subscribe - бонус за подписку на канал"""
    try:
        bonus_manager = BonusManager()

        # Проверяем статус подписки
        status = await bonus_manager.check_subscription_status(message.bot, message.from_user.id)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        if status.get("bonus_claimed"):
            await message.answer(
                "🎁 <b>Вы уже получали бонус за подписку на канал!</b>\n\n"
                "Спасибо за вашу поддержку! ❤️\n"
                f"📢 Продолжайте следить за новостями в {CHANNEL_USERNAME}",
                parse_mode="HTML"
            )
            return

        if status.get("subscribed"):
            # Пользователь подписан, можно получить бонус
            result = await bonus_manager.claim_subscription_bonus(message.bot, message.from_user.id)

            if result["success"]:
                await message.answer(
                    f"🎉 <b>Поздравляем!</b>\n\n"
                    f"Вы получили <b>{result['bonus_amount']} монет</b> за подписку на канал!\n\n"
                    f"Спасибо за вашу поддержку! ❤️\n"
                    f"📢 Оставайтесь с нами в {CHANNEL_USERNAME}",
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    f"❌ <b>Произошла ошибка:</b> {result.get('error', 'Неизвестная ошибка')}",
                    parse_mode="HTML"
                )
        else:
            # Пользователь не подписан, предлагаем подписаться
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=CHANNEL_LINK
                )
            ])

            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="✅ Я подписался! Проверить",
                    callback_data="check_subscription"
                )
            ])

            await message.answer(
                f"🎁 <b>Получите {SUBSCRIPTION_BONUS_AMOUNT} монет за подписку на наш канал!</b>\n\n"
                f"📢 <b>Канал:</b> {CHANNEL_USERNAME}\n"
                f"💰 <b>Награда:</b> {SUBSCRIPTION_BONUS_AMOUNT} монет\n\n"
                f"<b>Как получить бонус:</b>\n"
                f"1. Нажмите на кнопку ниже чтобы подписаться\n"
                f"2. После подписки нажмите '✅ Я подписался!'\n"
                f"3. Получите бонус! 🎉",
                reply_markup=keyboard,
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка в команде /subscribe: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса")


async def check_subscription_callback(callback: types.CallbackQuery):
    """Обработчик проверки подписки"""
    try:
        await callback.answer()

        bonus_manager = BonusManager()

        # Получаем бонус
        result = await bonus_manager.claim_subscription_bonus(callback.bot, callback.from_user.id)

        if result["success"]:
            # Используем HTML разметку вместо Markdown
            await callback.message.edit_text(
                f"🎉 <b>Поздравляем!</b>\n\n"
                f"Вы получили <b>{result['bonus_amount']} монет</b> за подписку на канал!\n\n"
                f"Спасибо за вашу поддержку! ❤️\n"
                f"📢 Оставайтесь с нами в {CHANNEL_USERNAME}",
                parse_mode="HTML"
            )
        elif result.get("needs_subscription"):
            # Пользователь еще не подписался
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=CHANNEL_LINK
                )],
                [InlineKeyboardButton(
                    text="🔄 Проверить снова",
                    callback_data="check_subscription"
                )]
            ])

            await callback.message.edit_text(
                f"❌ <b>Вы еще не подписались на канал {CHANNEL_USERNAME}</b>\n\n"
                f"Пожалуйста, подпишитесь по кнопке ниже, затем нажмите '🔄 Проверить снова'",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            # Убираем форматирование из сообщения об ошибке
            error_msg = str(result.get('error', 'Произошла ошибка'))
            await callback.message.edit_text(
                f"❌ {error_msg}",
                parse_mode=None  # Без форматирования
            )

    except Exception as e:
        logger.error(f"Ошибка в обработчике проверки подписки: {e}")
        try:
            await callback.message.edit_text(
                "❌ Произошла ошибка при проверке подписки. Попробуйте позже.",
                parse_mode=None
            )
        except:
            await callback.answer("❌ Произошла ошибка")


async def cmd_bonus(message: types.Message):
    """Команда /bonus - меню бонусов"""
    try:
        from .bonus import BonusManager

        bonus_manager = BonusManager()

        # Проверяем статус подписки
        subscription_status = await bonus_manager.check_subscription_status(message.bot, message.from_user.id)

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)

        # Если пользователь не подписан, показываем кнопку подписки
        if not subscription_status.get("subscribed"):
            keyboard.add(
                InlineKeyboardButton(
                    text="📢 Подписаться на канал (обязательно!)",
                    url=CHANNEL_LINK
                )
            )

        # Кнопка ежедневного бонуса
        daily_text = "🎁 Ежедневный бонус - 50,000 монет"
        if subscription_status.get("subscribed"):
            # Проверяем доступность бонуса
            bonus_info = await bonus_manager.check_daily_bonus(message.from_user.id)
            if bonus_info.get("available"):
                daily_text += " ✅"
            else:
                hours = bonus_info.get('hours_left', 0)
                minutes = bonus_info.get('minutes_left', 0)
                daily_text += f" ⏰ {hours}ч {minutes}м"
        else:
            daily_text += " 🔒 (требуется подписка)"

        keyboard.add(
            InlineKeyboardButton(text=daily_text, callback_data="daily_bonus_new")
        )

        # Кнопка бонуса за подписку
        sub_text = f"📢 Бонус за подписку - {SUBSCRIPTION_BONUS_AMOUNT} монет"
        if subscription_status.get("bonus_claimed"):
            sub_text += " ✅ (уже получен)"
        elif subscription_status.get("subscribed"):
            sub_text += " 🎁 (доступен)"
        else:
            sub_text += " 📍 (требуется подписка)"

        keyboard.add(
            InlineKeyboardButton(text=sub_text, callback_data="subscription_bonus")
        )

        # Информационный текст
        text = "🎁 **Меню бонусов**\n\n"

        if subscription_status.get("subscribed"):
            text += "✅ **Вы подписаны на канал**\n\n"
            text += "**Доступные бонусы:**\n"
            text += f"• 🎁 Ежедневный бонус - {BONUS_AMOUNT:,} монет каждый день\n"
            text += f"• 📢 Бонус за подписку - {SUBSCRIPTION_BONUS_AMOUNT} монет (одноразово)\n\n"

            # Проверяем доступность ежедневного бонуса
            bonus_info = await bonus_manager.check_daily_bonus(message.from_user.id)
            if bonus_info.get("available"):
                text += "🎉 **Ежедневный бонус доступен!**\n"
                text += "Нажмите '🎁 Ежедневный бонус' чтобы получить 50,000 монет\n"
            else:
                hours = bonus_info.get('hours_left', 0)
                minutes = bonus_info.get('minutes_left', 0)
                text += f"⏳ **До следующего бонуса:** {hours}ч {minutes}м\n"

            if subscription_status.get("bonus_claimed"):
                text += "\n✅ **Бонус за подписку уже получен**\n"
            else:
                text += f"\n🎁 **Бонус за подписку доступен!**\n"
                text += f"Нажмите '📢 Бонус за подписку' чтобы получить {SUBSCRIPTION_BONUS_AMOUNT} монет\n"
        else:
            text += "❌ **Вы не подписаны на канал!**\n\n"
            text += f"📢 **Канал:** {CHANNEL_USERNAME}\n\n"
            text += "**Для доступа к бонусам необходимо:**\n"
            text += "1. Подписаться на канал по кнопке выше\n"
            text += "2. После подписки нажмите на кнопку бонуса\n"
            text += "3. Нажмите '✅ Я подписался! Проверить'\n\n"
            text += "**Доступные бонусы после подписки:**\n"
            text += f"• 🎁 Ежедневный бонус - {BONUS_AMOUNT:,} монет каждый день\n"
            text += f"• 📢 Бонус за подписку - {SUBSCRIPTION_BONUS_AMOUNT} монет (одноразово)\n"

        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в команде /bonus: {e}")
        await message.answer("❌ Произошла ошибка при отображении меню бонусов")


async def daily_bonus_callback(callback: types.CallbackQuery):
    """Обработчик кнопки ежедневного бонуса"""
    try:
        await callback.answer()

        bonus_manager = BonusManager()

        # Проверяем статус подписки
        subscription_status = await bonus_manager.check_subscription_status(callback.bot, callback.from_user.id)

        if not subscription_status.get("subscribed"):
            # Пользователь не подписан, показываем сообщение о необходимости подписки
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=CHANNEL_LINK
                )],
                [InlineKeyboardButton(
                    text="✅ Я подписался! Проверить",
                    callback_data="check_subscription"
                )],
                [InlineKeyboardButton(
                    text="◀️ Назад в меню бонусов",
                    callback_data="bonus_back"
                )]
            ])

            await callback.message.edit_text(
                "🎁 **Ежедневный бонус**\n\n"
                "❌ **Чтобы получать ежедневные бонусы, вы должны подписаться на наш канал!**\n\n"
                f"📢 **Канал:** {CHANNEL_USERNAME}\n"
                f"💰 **Ежедневная награда:** {BONUS_AMOUNT:,} монет\n\n"
                "**Как получить доступ к бонусам:**\n"
                "1. Подпишитесь на канал по кнопке ниже\n"
                "2. После подписки нажмите '✅ Я подписался!'\n"
                "3. Получите доступ к ежедневным бонусам! 🎉",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return

        # Если пользователь подписан, выдаем бонус
        result = await bonus_manager.claim_daily_bonus(callback.from_user.id)

        if result.get("success", False):
            bonus_amount = result.get("bonus_amount", 0)
            bonuses_claimed = result.get("bonuses_claimed", [])

            # Формируем текст
            text = f"🎉 **Поздравляем!**\n\n"
            text += f"Вы получили **{bonus_amount:,} монет**!\n\n"

            # Добавляем детали бонусов если есть дополнительные
            if len(bonuses_claimed) > 1:
                text += "<b>Состав бонуса:</b>\n"
                if "daily" in bonuses_claimed:
                    text += f"• Ежедневный бонус: {BONUS_AMOUNT:,} монет\n"
                if "thief" in bonuses_claimed:
                    text += f"• Бонус Вора: {THIEF_BONUS_AMOUNT:,} монет\n"
                if "police" in bonuses_claimed:
                    text += f"• Бонус Полицейского: {POLICE_BONUS_AMOUNT:,} монет\n"

            text += f"\n🔄 Следующий бонус будет доступен через 24 часа\n"
            text += f"📢 Не забывайте подписываться на наш канал: {CHANNEL_USERNAME}"

            # Кнопка назад
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="◀️ Назад в меню бонусов",
                    callback_data="bonus_back"
                )]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

        else:
            if not result.get("available", True):
                hours = result.get('hours_left', 0)
                minutes = result.get('minutes_left', 0)

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="◀️ Назад в меню бонусов",
                        callback_data="bonus_back"
                    )]
                ])

                await callback.message.edit_text(
                    f"⏳ **Бонус еще не доступен**\n\n"
                    f"Вы сможете получить бонус через: **{hours} часов {minutes} минут**\n\n"
                    "Не пропустите свой шанс получить награду! 🎁",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await callback.answer(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")

    except Exception as e:
        logger.error(f"Ошибка в обработчике ежедневного бонуса: {e}")
        await callback.answer("❌ Произошла ошибка")


async def subscription_bonus_callback(callback: types.CallbackQuery):
    """Обработчик кнопки бонуса за подписку"""
    try:
        await callback.answer()
        await cmd_subscribe(callback.message)
    except Exception as e:
        logger.error(f"Ошибка в обработчике бонуса за подписку: {e}")
        await callback.answer("❌ Произошла ошибка")


async def bonus_back_callback(callback: types.CallbackQuery):
    """Возврат в меню бонусов"""
    try:
        await callback.answer()
        await cmd_bonus(callback.message)
    except Exception as e:
        logger.error(f"Ошибка в обработчике возврата: {e}")
        await callback.answer("❌ Произошла ошибка")


def register_subscription_handlers(dp: Dispatcher):
    """Регистрация хендлеров подписки и бонусов"""
    # Команды
    dp.register_message_handler(cmd_subscribe, commands=["subscribe", "подписка"])
    dp.register_message_handler(cmd_bonus, commands=["bonus", "бонус"])

    # Колбэки
    dp.register_callback_query_handler(check_subscription_callback, lambda c: c.data == "check_subscription")
    dp.register_callback_query_handler(subscription_bonus_callback, lambda c: c.data == "subscription_bonus")
    dp.register_callback_query_handler(daily_bonus_callback, lambda c: c.data == "daily_bonus_new")
    dp.register_callback_query_handler(bonus_back_callback, lambda c: c.data == "bonus_back")

    logger.info("✅ Хендлеры подписки и бонусов зарегистрированы")