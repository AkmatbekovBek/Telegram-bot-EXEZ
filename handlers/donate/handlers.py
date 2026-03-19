# handlers/donate/handlers.py
import logging
from aiogram import types, Dispatcher
from datetime import datetime, timedelta

from .texts_simple import donate_texts
from .config import (
    BONUS_AMOUNT,
    BONUS_COOLDOWN_HOURS,
    THIEF_BONUS_AMOUNT,
    POLICE_BONUS_AMOUNT,
    PRIVILEGE_BONUS_COOLDOWN_HOURS,
    SUPPORT_USERNAME,
    DONATE_ITEMS,
    COIN_PACKAGES,
    CHANNEL_USERNAME,
    CHANNEL_LINK,
    SUBSCRIPTION_BONUS_AMOUNT,
    DONATE_ADMIN_GROUP_ID,
    DONATE_PAYMENT_REQUISITES_TEXT,
)
from .utils import format_time_left
from .bonus import BonusManager
from .keyboards import create_main_donate_keyboard, create_privileges_keyboard, create_bonus_keyboard, \
    create_back_keyboard, create_buy_coins_menu_keyboard, create_payment_method_keyboard
from .payment import PaymentHandler
from .manual_payment import ManualPaymentManager
from database.crud import DonateRepository, UserRepository
from ..admin.admin_helpers import check_admin_async, check_admin_silent

from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


class DonateHandler:
    """Класс для обработки операций доната и бонусов"""

    def __init__(self, bot):
        self.logger = logger
        self.bot = bot
        self.bonus_manager = BonusManager()
        self.payment_handler = PaymentHandler(bot)
        self.manual_payment_manager = ManualPaymentManager()

    # --- Вспомогательные методы ---
    async def _ensure_private_chat(self, message: types.Message) -> bool:
        """Проверяет, что команда вызвана в личных сообщениях"""
        if message.chat.type != "private":
            bot_username = (await message.bot.get_me()).username
            bot_link = f"https://t.me/gameexez_bot?start=_tgr_NvQeAjswY2Uy"
            await message.reply(
                "💎 <b>Донат магазин</b>\n\n"
                f"Команда работает только в <a href='{bot_link}'>личных сообщениях</a>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return False
        return True

    def _get_main_donate_text(self) -> str:
        """Форматирует главный текст доната"""
        text = donate_texts.get("main")
        # Заменяем {support_username} если есть
        if "{support_username}" in text:
            text = text.format(support_username=SUPPORT_USERNAME)
        return text

    async def _get_user_bonus_info_text(self, user_id: int) -> str:
        """Формирует текст информации о бонусах пользователя"""
        text = "🎁 <b>Ежедневный бонус</b>\n\n"
        text += f"💎 Каждые 24 часа вы можете получить <b>{BONUS_AMOUNT:,} монет</b>!\n\n"
        text += "⚡ <b>Как получить:</b>\n"
        text += "1. Нажмите 'Получить бонус'\n"
        text += "2. Получите свои монеты\n"
        text += "3. Возвращайтесь через 24 часа\n"

        try:
            from database import get_db
            db = next(get_db())
            user_purchases = DonateRepository.get_user_active_purchases(db, user_id)
            purchased_ids = [p.item_id for p in user_purchases]
            has_thief = 1 in purchased_ids
            has_police = 2 in purchased_ids

            # Добавляем информацию о дополнительных бонусах
            if has_thief or has_police:
                text += "\n💎 <b>Дополнительные бонусы за привилегии:</b>"
                if has_thief:
                    text += f"\n• 👑 Вор в законе: +{THIEF_BONUS_AMOUNT:,} монет"
                if has_police:
                    text += f"\n• 👮‍♂️ Полицейский: +{POLICE_BONUS_AMOUNT:,} монет"

        except Exception as e:
            self.logger.error(f"Error getting user purchases: {e}")
            text += "\n\n⚠️ <i>Не удалось загрузить информацию о привилегиях</i>"

        return text

    def _format_coin_packages_text(self):
        """Форматирует текст с пакетами монет (только звезды)"""
        text = "💎 <b>Пакеты монет (оплата звездами):</b>\n\n"

        for package in COIN_PACKAGES:
            text += f"• <b>{package['amount']:,} монет</b> — ⭐ {package['stars_text']}\n"

        text += f"\n🆔 <b>Не забудьте указать ваш ID</b> (команда /id)"
        text += f"\n\n💎 <b>Выберите пакет:</b>"
        return text

    # --- Основные команды ---
    async def donate_command(self, message: types.Message):
        """Обработчик команды доната"""
        if not await self._ensure_private_chat(message):
            return

        donate_text = self._get_main_donate_text()
        keyboard = create_main_donate_keyboard()

        await message.answer(donate_text, reply_markup=keyboard, parse_mode="HTML")

    # --- Callback обработчики ---
    async def donate_callback_handler(self, callback: types.CallbackQuery):
        """Обработчик нажатий на кнопки доната"""
        if callback.message.chat.type != "private":
            await callback.answer("💎 Команда работает только в личных сообщениях", show_alert=True)
            return

        action = callback.data
        user_id = callback.from_user.id

        try:
            if action == "back_to_donate":
                await self._handle_back_to_donate(callback)
            elif action == "donate_buy_coins_menu":
                await self._handle_buy_coins_menu(callback)
            elif action == "back_to_buy":
                await self._handle_back_to_buy(callback)
            elif action == "donate_privileges":
                await self._handle_privileges(callback, user_id)
            elif action == "daily_bonus":
                await self._handle_daily_bonus(callback, user_id)
            elif action == "daily_bonus_info":
                await self._handle_daily_bonus_info(callback, user_id)
            elif action == "privilege_bonus_info":
                await self._handle_privilege_bonus_info(callback, user_id)
            elif action == "claim_bonus":
                await self._handle_claim_bonus(callback, user_id)
            elif action == "claim_privilege_bonus":
                await self._handle_claim_privilege_bonus(callback, user_id)
            elif action == "check_subscription":
                await self._handle_check_subscription(callback, user_id)
            elif action.startswith("select_coins_"):
                await self._handle_select_coins(callback)
            elif action.startswith("select_privilege_"):
                await self._handle_select_privilege(callback)
            elif action.startswith("pay_stars_"):
                await self._handle_pay_stars(callback)
            elif action.startswith("pay_manual_"):
                await self._handle_pay_manual(callback)
            elif action.startswith("manualpay_cancel_"):
                await self._handle_manualpay_cancel(callback)
            elif action.startswith("donate_already_bought_"):
                await self._handle_already_bought(callback)
            elif action == "ignore":
                await callback.answer("⛔ Этот товар нельзя купить за звезды")
        except Exception as e:
            self.logger.error(f"Error in donate callback handler: {e}", exc_info=True)
            await self._handle_error(callback)

    async def _handle_back_to_donate(self, callback: types.CallbackQuery):
        """Возвращает в главное меню доната"""
        donate_text = self._get_main_donate_text()
        keyboard = create_main_donate_keyboard()

        try:
            await callback.message.edit_text(donate_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message when going back to donate: {e}")

        await callback.answer()

    async def _handle_buy_coins_menu(self, callback: types.CallbackQuery):
        """Обрабатывает показ меню покупки монет (только звезды)"""
        text = self._format_coin_packages_text()
        keyboard = create_buy_coins_menu_keyboard()

        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message for buy coins menu: {e}")

        await callback.answer()

    async def _handle_back_to_buy(self, callback: types.CallbackQuery):
        """Возвращает в меню покупки монет"""
        await self._handle_buy_coins_menu(callback)

    async def _handle_privileges(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает показ привилегий (только звезды)"""
        text = (
            "👑 <b>Привилегии (оплата звездами):</b>\n\n"
            "⚡ <b>Улучшите свой игровой опыт с привилегиями!</b>\n\n"
            "💎 <b>Доступные привилегии:</b>\n"
            "• <b>Вор в законе</b> — ⭐ 1800 звезд\n"
            "• <b>Полицейский</b> — ⭐ 950 звезд\n"
            "• <b>Снятие лимита перевода</b> — ⛔ нет звезд\n\n"
            "⏰ <b>Срок действия:</b> 30 дней\n"
            "🆔 <b>Укажите ID:</b> /id в лс бота\n\n"
            "💎 <b>Выберите привилегию:</b>"
        )
        keyboard = create_privileges_keyboard(user_id)

        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message for privileges: {e}")

        await callback.answer()

    async def _handle_select_coins(self, callback: types.CallbackQuery):
        """Обрабатывает выбор пакета монет (только звезды)"""
        item_id = int(callback.data.split("_")[2])
        package = next((p for p in COIN_PACKAGES if p["id"] == item_id), None)

        if package:
            text = (
                f"💎 <b>Пакет монет: {package['amount']:,}</b>\n\n"
                f"💰 <b>Цена:</b> ⭐ {package['stars_text']}\n"
                f"🎯 <b>После оплаты монеты будут начислены на ваш баланс</b>\n\n"
                f"🆔 <b>Не забудьте указать ваш ID</b> (команда /id)\n\n"
                f"💎 <b>Оплатить звездами:</b>"
            )

            keyboard = create_payment_method_keyboard("coins", item_id)

            try:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    self.logger.error(f"Error editing message for coin selection: {e}")

            await callback.answer(f"💎 {package['amount']:,} монет")
        else:
            await callback.answer("❌ Пакет не найден")

    async def _handle_select_privilege(self, callback: types.CallbackQuery):
        """Обрабатывает выбор привилегии (только звезды)"""
        item_id = int(callback.data.split("_")[2])
        item = next((i for i in DONATE_ITEMS if i["id"] == item_id), None)

        if item and item.get("stars_price"):
            text = (
                f"👑 <b>{item['name']}</b>\n\n"
                f"💰 <b>Цена:</b> ⭐ {item['stars_text']}\n"
                f"⏰ <b>Срок:</b> {item['duration']}\n"
                f"🎯 <b>Преимущества:</b>\n{item['benefit']}\n\n"
                f"🎁 <b>После оплаты привилегия будет активирована автоматически</b>\n\n"
                f"💎 <b>Оплатить звездами:</b>"
            )

            keyboard = create_payment_method_keyboard("privilege", item_id)

            try:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    self.logger.error(f"Error editing message for privilege selection: {e}")

            await callback.answer(f"👑 {item['name']}")
        else:
            await callback.answer("❌ Эта привилегия не доступна для покупки за звезды")

    async def _handle_pay_stars(self, callback: types.CallbackQuery):
        """Обрабатывает оплату звездами"""
        try:
            _, _, item_type, item_id = callback.data.split("_")
            item_id = int(item_id)

            # Отправляем счет для оплаты звездами
            success = await self.payment_handler.send_stars_invoice(
                chat_id=callback.from_user.id,
                item_type=item_type,
                item_id=item_id
            )

            if success:
                await callback.answer("✅ Счет отправлен. Оплатите его в открывшемся окне.")
            else:
                await callback.answer("❌ Ошибка при создании счета")

        except Exception as e:
            self.logger.error(f"Error in _handle_pay_stars: {e}")
            await callback.answer("❌ Произошла ошибка")

    async def _handle_pay_manual(self, callback: types.CallbackQuery):
        """Запускает ручную оплату по реквизитам и ожидает чек от пользователя."""
        try:
            _, _, item_type, item_id = callback.data.split("_")
            item_id = int(item_id)

            if DONATE_ADMIN_GROUP_ID == 0:
                await callback.answer(
                    "❌ Не настроена админ-группа для проверок (DONATE_ADMIN_GROUP_ID)",
                    show_alert=True,
                )
                return

            item_name, coins_amount, price_text = self._get_item_details(item_type, item_id)
            if not item_name:
                await callback.answer("❌ Товар не найден", show_alert=True)
                return

            request_id = self.manual_payment_manager.create_request(
                user_id=callback.from_user.id,
                username=callback.from_user.username,
                first_name=callback.from_user.first_name,
                last_name=callback.from_user.last_name,
                item_type=item_type,
                item_id=item_id,
                item_name=item_name,
                coins_amount=coins_amount,
                price_text=price_text,
            )

            try:
                requisites_text = DONATE_PAYMENT_REQUISITES_TEXT.format(user_id=callback.from_user.id)
            except Exception:
                requisites_text = DONATE_PAYMENT_REQUISITES_TEXT

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    text="❌ Отменить", callback_data=f"manualpay_cancel_{request_id}"
                )
            )
            keyboard.add(types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_donate"))

            text = (
                "💳 <b>Оплата по реквизитам</b>\n\n"
                f"🧾 <b>Заявка:</b> #{request_id}\n"
                f"📦 <b>Товар:</b> {item_name}\n"
                f"💰 <b>Сумма:</b> {price_text}\n\n"
                f"{requisites_text}\n\n"
                "📎 <b>После оплаты отправьте сюда чек</b> (фото/скрин/файл/текст).\n"
                "После отправки чек автоматически уйдет в админ-группу на проверку."
            )

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer("✅ Реквизиты отправлены")

        except Exception as e:
            self.logger.error(f"Error in _handle_pay_manual: {e}", exc_info=True)
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def _handle_manualpay_cancel(self, callback: types.CallbackQuery):
        """Отмена заявки пользователем (пока чек еще не отправлен)."""
        try:
            request_id = int(callback.data.split("_")[-1])
            cancelled = self.manual_payment_manager.cancel_request(request_id, callback.from_user.id)

            if not cancelled:
                await callback.answer("❌ Не удалось отменить (возможно, уже отправлен чек)", show_alert=True)
                return

            await callback.message.edit_text(
                "✅ Заявка отменена.\n\nВы можете открыть донат снова и выбрать другой способ оплаты.",
                reply_markup=create_main_donate_keyboard(),
                parse_mode="HTML",
            )
            await callback.answer("Отменено")
        except Exception as e:
            self.logger.error(f"Error in _handle_manualpay_cancel: {e}", exc_info=True)
            await callback.answer("❌ Ошибка", show_alert=True)

    async def _handle_check_subscription(self, callback: types.CallbackQuery, user_id: int):
        """Проверяет подписку и (при необходимости) выдает бонус за подписку."""
        try:
            result = await self.bonus_manager.check_subscription_status(callback.bot, user_id)

            if result.get("bonus_claimed"):
                # Уже получал бонус — просто показываем доступ к бонусам
                await callback.answer("✅ Подписка подтверждена", show_alert=False)
                await self._handle_daily_bonus(callback, user_id)
                return

            # Если не подписан — показываем CTA
            from .bonus import SubscriptionManager
            is_subscribed = await SubscriptionManager.check_subscription(callback.bot, user_id)
            if not is_subscribed:
                await callback.answer("❌ Вы не подписаны", show_alert=True)
                return

            # Подписан, пробуем начислить бонус
            claim = await self.bonus_manager.claim_subscription_bonus(callback.bot, user_id)
            if claim.get("success"):
                await callback.answer("🎉 Бонус начислен!")
            else:
                # Например: уже получал бонус
                await callback.answer("✅ Подписка подтверждена")

            await self._handle_daily_bonus(callback, user_id)

        except Exception as e:
            self.logger.error(f"Error in _handle_check_subscription: {e}", exc_info=True)
            await callback.answer("❌ Ошибка проверки", show_alert=True)

    def _get_item_details(self, item_type: str, item_id: int):
        """Возвращает (item_name, coins_amount, price_text) для ручной оплаты."""
        if item_type == "coins":
            package = next((p for p in COIN_PACKAGES if p["id"] == item_id), None)
            if not package:
                return None, 0, ""
            price_parts = []
            if package.get("rub_price"):
                price_parts.append(f"{package['rub_price']}₽")
            if package.get("tenge_price"):
                price_parts.append(f"{package['tenge_price']} тг")
            price_text = " / ".join(price_parts) if price_parts else ""
            return f"💎 {package['amount']:,} монет", int(package["amount"]), price_text

        if item_type == "privilege":
            item = next((i for i in DONATE_ITEMS if i["id"] == item_id), None)
            if not item:
                return None, 0, ""
            price_parts = []
            if item.get("price"):
                price_parts.append(str(item["price"]))
            if item.get("tenge_price"):
                price_parts.append(str(item["tenge_price"]))
            price_text = " / ".join([p for p in price_parts if p])
            return item["name"], 0, price_text

        return None, 0, ""

    async def _handle_daily_bonus(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает показ бонусов (ТЕПЕРЬ С ПРОВЕРКОЙ ПОДПИСКИ)"""
        try:
            # Сначала проверяем подписку на канал
            from .bonus import SubscriptionManager
            is_subscribed = await SubscriptionManager.check_subscription(callback.bot, user_id)

            if not is_subscribed:
                # Пользователь не подписан, показываем сообщение с требованием подписки
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        text="📢 Подписаться на канал",
                        url=CHANNEL_LINK
                    )
                )
                keyboard.add(
                    types.InlineKeyboardButton(
                        text="✅ Я подписался! Проверить",
                        callback_data="check_subscription"
                    )
                )
                keyboard.add(
                    types.InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="back_to_donate"
                    )
                )

                await callback.message.edit_text(
                    "🎁 <b>Ежедневный бонус</b>\n\n"
                    "❌ <b>Чтобы получать ежедневные бонусы, вы должны подписаться на наш канал!</b>\n\n"
                    f"📢 <b>Канал:</b> {CHANNEL_USERNAME}\n"
                    f"💰 <b>Ежедневная награда:</b> {BONUS_AMOUNT:,} монет\n\n"
                    "<b>Как получить доступ к бонусам:</b>\n"
                    "1. Подпишитесь на канал по кнопке ниже\n"
                    "2. После подписки нажмите '✅ Я подписался!'\n"
                    "3. Получите доступ к ежедневным бонусам! 🎉",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Если пользователь подписан, показываем старый интерфейс бонусов
            bonus_info = await self.bonus_manager.check_daily_bonus(user_id)
            privilege_bonus_info = await self.bonus_manager.check_privilege_bonus(user_id)

            bonus_text = await self._get_user_bonus_info_text(user_id)

            # Добавляем статус
            if bonus_info.get("available", False) or privilege_bonus_info.get("available", False):
                status_text = "\n🎉 <b>Статус:</b> бонусы доступны!"
            else:
                time_left = format_time_left(bonus_info.get('hours_left', 0), bonus_info.get('minutes_left', 0))
                status_text = f"\n⏳ <b>Статус:</b> до следующих бонусов {time_left}"

            full_text = bonus_text + status_text
            keyboard = create_bonus_keyboard(
                bonus_info.get("available", False) or privilege_bonus_info.get("available", False))

            try:
                await callback.message.edit_text(full_text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    self.logger.error(f"Error editing message for daily bonus: {e}")

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in _handle_daily_bonus: {e}")
            await callback.answer("❌ Произошла ошибка")

    async def _handle_daily_bonus_info(self, callback: types.CallbackQuery, user_id: int):
        """Показывает информацию о бонусе 50K"""
        bonus_info = await self.bonus_manager.check_daily_bonus(user_id)

        # Используем сохраненный текст для бонуса
        text = donate_texts.get("daily_bonus")

        # Заменяем переменные если есть
        if "{bonus_amount}" in text:
            text = text.format(bonus_amount=BONUS_AMOUNT)

        if bonus_info.get("available", False):
            status_text = donate_texts.get("bonus_available")
        else:
            time_left = format_time_left(bonus_info.get('hours_left', 0), bonus_info.get('minutes_left', 0))
            status_text = donate_texts.get("bonus_cooldown").format(time_left=time_left)

        text += f"\n\n{status_text}"
        keyboard = create_back_keyboard()

        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message for daily bonus info: {e}")

        await callback.answer()

    async def _handle_privilege_bonus_info(self, callback: types.CallbackQuery, user_id: int):
        """Показывает информацию о бонусах за привилегии"""
        privilege_bonus_info = await self.bonus_manager.check_privilege_bonus(user_id)

        text = donate_texts.get("privilege_bonus")

        has_thief = privilege_bonus_info.get('has_thief', False)
        has_police = privilege_bonus_info.get('has_police', False)

        if not has_thief and not has_police:
            text += f"\n\n{donate_texts.get('no_privileges')}"

        if privilege_bonus_info.get("available", False):
            status_text = donate_texts.get("bonus_available")
        else:
            time_left = format_time_left(privilege_bonus_info.get('hours_left', 0),
                                         privilege_bonus_info.get('minutes_left', 0))
            status_text = donate_texts.get("bonus_cooldown").format(time_left=time_left)

        text += f"\n\n{status_text}"
        keyboard = create_back_keyboard()

        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message for privilege bonus info: {e}")

        await callback.answer()

    async def _handle_claim_bonus(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает получение бонуса 50K (С ПРОВЕРКОЙ ПОДПИСКИ)"""
        try:
            # Сначала проверяем подписку
            from .bonus import SubscriptionManager
            is_subscribed = await SubscriptionManager.check_subscription(callback.bot, user_id)

            if not is_subscribed:
                await callback.answer("❌ Вы не подписаны на канал. Подпишитесь чтобы получать бонусы!")
                return

            result = await self.bonus_manager.claim_daily_bonus(user_id)

            if result.get("success", False):
                bonus_amount = result.get("bonus_amount", 0)

                # Простой текст
                text = f"🎉 <b>Поздравляем!</b>\n\n"
                text += f"Вы получили <b>{bonus_amount:,} монет</b>!\n\n"

                # Добавляем благодарность за подписку
                text += f"📢 Спасибо за подписку на наш канал!\n"
                text += f"🔄 Следующий бонус будет доступен через 24 часа\n"

                keyboard = create_bonus_keyboard(False)

                try:
                    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        self.logger.error(f"Error editing message after claiming bonus: {e}")

                await callback.answer("✅ Бонус успешно получен!")
            else:
                if not result.get("available", True):
                    time_left = format_time_left(result.get('hours_left', 0), result.get('minutes_left', 0))
                    await callback.answer(f"⏳ Бонус будет доступен через {time_left}")
                else:
                    await callback.answer("❌ Ошибка при получении бонуса")

        except Exception as e:
            self.logger.error(f"Error in _handle_claim_bonus: {e}")
            await callback.answer("❌ Произошла ошибка")

    async def _handle_claim_privilege_bonus(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает получение бонусов за привилегии"""
        # Используем ту же функцию что и для обычного бонуса
        await self._handle_claim_bonus(callback, user_id)

    async def _handle_already_bought(self, callback: types.CallbackQuery):
        """Обрабатывает нажатие на уже купленной привилегии"""
        item_id = int(callback.data.split("_")[3])
        item = next((i for i in DONATE_ITEMS if i["id"] == item_id), None)

        if item:
            # Используем сохраненный текст для уже купленной привилегии
            text = donate_texts.get("already_bought")

            # Подготавливаем данные для замены
            price_text = f"{item['price']}"
            if item['tenge_price']:
                price_text += f" {item['tenge_price']}"

            # Заменяем переменные
            text = text.format(
                item_name=item['name'],
                price_text=price_text,
                duration=item['duration'],
                benefit=item['benefit'],
                cooldown_hours=BONUS_COOLDOWN_HOURS
            )

            keyboard = create_back_keyboard()

            try:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    self.logger.error(f"Error editing message for already bought item: {e}")

            await callback.answer("✅ Уже куплено")
        else:
            await callback.answer("❌ Товар не найден")

    async def _handle_error(self, callback: types.CallbackQuery):
        """Обрабатывает общие ошибки"""
        text = donate_texts.get("error_text")

        try:
            await callback.message.edit_text(
                text,
                reply_markup=create_back_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message in _handle_error: {e}")

        await callback.answer("⚠️ Произошла ошибка")

    # --- Автодонат по реквизитам (чек -> админ-группа -> approve/deny) ---
    async def manual_receipt_handler(self, message: types.Message):
        """Получает чек от пользователя и отправляет его в админ-группу на проверку."""
        try:
            if message.chat.type != "private":
                return

            pending = self.manual_payment_manager.get_latest_user_request(
                user_id=message.from_user.id,
                status="awaiting_receipt",
            )
            if not pending:
                return

            if DONATE_ADMIN_GROUP_ID == 0:
                await message.reply(
                    "❌ Админ-группа для проверок не настроена. Сообщите администратору бота.",
                    parse_mode="HTML",
                )
                return

            # Помечаем, что чек привязан к заявке
            self.manual_payment_manager.attach_receipt(
                request_id=pending.id,
                receipt_chat_id=message.chat.id,
                receipt_message_id=message.message_id,
            )

            # Пересылаем чек в админ-группу
            forwarded = await self.bot.forward_message(
                chat_id=DONATE_ADMIN_GROUP_ID,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )

            # Кнопки для админов
            admin_kb = types.InlineKeyboardMarkup(row_width=2)
            admin_kb.row(
                types.InlineKeyboardButton(
                    text="✅ Разрешить",
                    callback_data=f"manualadmin_approve_{pending.id}",
                ),
                types.InlineKeyboardButton(
                    text="❌ Запретить",
                    callback_data=f"manualadmin_reject_{pending.id}",
                ),
            )

            user_display = (
                f"@{pending.username}" if pending.username else (pending.first_name or "пользователь")
            )
            created_str = pending.created_at.strftime("%Y-%m-%d %H:%M") if pending.created_at else ""

            admin_text = (
                "🧾 <b>Новый чек на проверку</b>\n\n"
                f"🆔 <b>Заявка:</b> #{pending.id}\n"
                f"👤 <b>Пользователь:</b> {user_display} (<code>{pending.user_id}</code>)\n"
                f"📦 <b>Товар:</b> {pending.item_name}\n"
                f"💰 <b>Сумма:</b> {pending.price_text}\n"
                f"📅 <b>Создано:</b> {created_str}\n"
            )

            admin_msg = await self.bot.send_message(
                chat_id=DONATE_ADMIN_GROUP_ID,
                text=admin_text,
                parse_mode="HTML",
                reply_to_message_id=forwarded.message_id,
                reply_markup=admin_kb,
                disable_web_page_preview=True,
            )

            self.manual_payment_manager.set_admin_message(
                request_id=pending.id,
                admin_chat_id=DONATE_ADMIN_GROUP_ID,
                admin_message_id=admin_msg.message_id,
            )

            await message.reply(
                "✅ Чек получен и отправлен на проверку.\n\n"
                "Ожидайте решения администраторов — бот уведомит вас автоматически.",
                parse_mode="HTML",
            )

        except Exception as e:
            self.logger.error(f"Error in manual_receipt_handler: {e}", exc_info=True)

    async def manual_admin_callback_handler(self, callback: types.CallbackQuery):
        """Approve/deny заявки админами в группе."""
        try:
            if not await check_admin_silent(callback.from_user.id):
                await callback.answer("❌ Недостаточно прав", show_alert=True)
                return

            parts = callback.data.split("_")
            # manualadmin_approve_{id} | manualadmin_reject_{id}
            if len(parts) < 3:
                await callback.answer("❌ Некорректные данные", show_alert=True)
                return

            action = parts[1]
            request_id = int(parts[2])

            req = self.manual_payment_manager.get_request_by_id(request_id)
            if not req:
                await callback.answer("❌ Заявка не найдена", show_alert=True)
                return

            if req.status != "pending_admin":
                await callback.answer("ℹ️ Заявка уже обработана", show_alert=True)
                # Убираем клавиатуру, если еще висит
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
                return

            if action == "approve":
                updated = self.manual_payment_manager.decide(request_id, callback.from_user.id, "approved")
                if not updated:
                    await callback.answer("ℹ️ Уже обработано", show_alert=True)
                    return

                apply_result = await self._apply_manual_purchase(req)

                # Обновляем сообщение в админ-группе
                admin_line = f"✅ <b>Одобрено</b> админом <code>{callback.from_user.id}</code>"
                try:
                    await callback.message.edit_text(
                        callback.message.html_text + "\n" + admin_line,
                        parse_mode="HTML",
                        reply_markup=None,
                        disable_web_page_preview=True,
                    )
                except Exception:
                    # Если редактирование текста не удалось — хотя бы убираем кнопки
                    try:
                        await callback.message.edit_reply_markup(reply_markup=None)
                    except Exception:
                        pass

                await callback.answer("✅ Одобрено")

                # Уведомление пользователю
                await self._notify_user_on_decision(req, approved=True, apply_result=apply_result)

            elif action == "reject":
                updated = self.manual_payment_manager.decide(request_id, callback.from_user.id, "rejected")
                if not updated:
                    await callback.answer("ℹ️ Уже обработано", show_alert=True)
                    return

                admin_line = f"❌ <b>Отклонено</b> админом <code>{callback.from_user.id}</code>"
                try:
                    await callback.message.edit_text(
                        callback.message.html_text + "\n" + admin_line,
                        parse_mode="HTML",
                        reply_markup=None,
                        disable_web_page_preview=True,
                    )
                except Exception:
                    try:
                        await callback.message.edit_reply_markup(reply_markup=None)
                    except Exception:
                        pass

                await callback.answer("❌ Отклонено")
                await self._notify_user_on_decision(req, approved=False)
            else:
                await callback.answer("❌ Неизвестное действие", show_alert=True)

        except Exception as e:
            self.logger.error(f"Error in manual_admin_callback_handler: {e}", exc_info=True)
            await callback.answer("❌ Ошибка", show_alert=True)

    async def _apply_manual_purchase(self, req):
        """Начисление монет/активация привилегии после approve."""
        from database import get_db
        from database.models import UserPurchase

        db = next(get_db())
        try:
            # гарантируем пользователя
            user = UserRepository.get_or_create_user(
                db,
                telegram_id=req.user_id,
                username=req.username,
                first_name=req.first_name,
                last_name=req.last_name,
            )

            if req.item_type == "coins":
                current = int(user.coins or 0)
                user.coins = current + int(req.coins_amount)
                db.commit()
                return {"type": "coins", "amount": int(req.coins_amount), "balance": int(user.coins)}

            if req.item_type == "privilege":
                expires_at = None
                if req.item_id in [1, 2]:
                    expires_at = datetime.now() + timedelta(days=30)

                existing = (
                    db.query(UserPurchase)
                    .filter(UserPurchase.user_id == req.user_id, UserPurchase.item_id == req.item_id)
                    .first()
                )

                if existing:
                    existing.item_name = req.item_name
                    existing.expires_at = expires_at
                    existing.purchased_at = datetime.now()
                else:
                    purchase = UserPurchase(
                        user_id=req.user_id,
                        item_id=req.item_id,
                        item_name=req.item_name,
                        price=0,
                        chat_id=req.admin_chat_id or 0,
                        purchased_at=datetime.now(),
                        expires_at=expires_at,
                    )
                    db.add(purchase)

                db.commit()
                return {"type": "privilege", "item_name": req.item_name, "expires_at": expires_at}

            return {"type": "unknown"}

        except Exception as e:
            db.rollback()
            self.logger.error(f"Failed to apply manual purchase for request #{req.id}: {e}", exc_info=True)
            return {"type": "error", "error": str(e)}
        finally:
            db.close()

    async def _notify_user_on_decision(self, req, approved: bool, apply_result: Optional[dict] = None):
        """Уведомляет пользователя о решении."""
        try:
            if approved:
                if apply_result and apply_result.get("type") == "coins":
                    text = (
                        "✅ <b>Оплата подтверждена</b>\n\n"
                        f"📦 <b>Товар:</b> {req.item_name}\n"
                        f"💎 <b>Начислено:</b> {apply_result['amount']:,} монет\n"
                        f"💰 <b>Ваш баланс:</b> {apply_result['balance']:,} монет\n"
                    )
                elif apply_result and apply_result.get("type") == "privilege":
                    expires_at = apply_result.get("expires_at")
                    expires_text = (
                        expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "без срока"
                    )
                    text = (
                        "✅ <b>Оплата подтверждена</b>\n\n"
                        f"👑 <b>Привилегия активирована:</b> {req.item_name}\n"
                        f"⏰ <b>Действует до:</b> {expires_text}\n\n"
                        "🎁 Теперь вы можете получать ежедневные бонусы."
                    )
                else:
                    text = (
                        "✅ <b>Оплата подтверждена</b>\n\n"
                        f"📦 <b>Товар:</b> {req.item_name}\n"
                        "Если начисление не отобразилось сразу — откройте /donate заново."
                    )
            else:
                text = (
                    "❌ <b>Оплата отклонена</b>\n\n"
                    f"📦 <b>Товар:</b> {req.item_name}\n"
                    "Если вы считаете, что это ошибка — напишите в кассу."
                    f"\n\n💬 @{SUPPORT_USERNAME}"
                )

            await self.bot.send_message(chat_id=req.user_id, text=text, parse_mode="HTML")
        except Exception:
            # Пользователь мог заблокировать бот... просто игнорируем
            pass

    # --- Обработчики платежей ---
    async def pre_checkout_handler(self, pre_checkout_query: types.PreCheckoutQuery):
        """Обработчик предварительной проверки платежа"""
        await self.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    async def successful_payment_handler(self, message: types.Message):
        """Обработчик успешного платежа через Telegram Stars"""
        try:
            payment = message.successful_payment
            user_id = message.from_user.id

            # payload содержит тип товара и его ID
            payload = payment.invoice_payload  # Например: "coins_1" или "privilege_2"

            if payload:
                parts = payload.split('_')
                if len(parts) >= 2:
                    item_type = parts[0]  # "coins" или "privilege"
                    item_id = int(parts[1])  # ID товара

                    if item_type == "coins":
                        package = next((p for p in COIN_PACKAGES if p["id"] == item_id), None)
                        if package:
                            # НАЧИСЛЯЕМ МОНЕТЫ
                            from database import get_db
                            from database.crud import UserRepository
                            db = next(get_db())
                            try:
                                user = UserRepository.get_or_create_user(
                                    db,
                                    telegram_id=user_id,
                                    username=message.from_user.username,
                                    first_name=message.from_user.first_name,
                                    last_name=message.from_user.last_name,
                                )

                                current = int(user.coins or 0)
                                user.coins = current + int(package['amount'])
                                db.commit()

                                # Уведомляем пользователя
                                await message.answer(
                                    f"✅ <b>Оплата успешна!</b>\n\n"
                                    f"💎 <b>Получено:</b> {package['amount']:,} монет\n"
                                    f"💰 <b>Ваш баланс:</b> {int(user.coins):,} монет\n"
                                    f"⭐ <b>Оплачено:</b> {package['stars_text']}\n\n"
                                    f"Спасибо за покупку! ❤️",
                                    parse_mode="HTML"
                                )
                            except Exception as e:
                                logger.error(f"Ошибка начисления монет: {e}")
                                await message.answer("❌ Ошибка при начислении монет")
                            finally:
                                db.close()

                    elif item_type == "privilege":
                        item = next((i for i in DONATE_ITEMS if i["id"] == item_id), None)
                        if item and item.get("stars_price"):
                            # АКТИВИРУЕМ ПРИВИЛЕГИЮ
                            from database import get_db
                            from database.models import UserPurchase
                            db = next(get_db())
                            try:
                                expires_at = None
                                if item_id in [1, 2]:
                                    expires_at = datetime.now() + timedelta(days=30)

                                existing = (
                                    db.query(UserPurchase)
                                    .filter(UserPurchase.user_id == user_id, UserPurchase.item_id == item_id)
                                    .first()
                                )

                                if existing:
                                    existing.item_name = item['name']
                                    existing.expires_at = expires_at
                                    existing.purchased_at = datetime.now()
                                else:
                                    purchase = UserPurchase(
                                        user_id=user_id,
                                        item_id=item_id,
                                        item_name=item['name'],
                                        price=0,
                                        chat_id=message.chat.id,
                                        purchased_at=datetime.now(),
                                        expires_at=expires_at,
                                    )
                                    db.add(purchase)

                                db.commit()

                                # Уведомляем пользователя
                                await message.answer(
                                    f"✅ <b>Оплата успешна!</b>\n\n"
                                    f"👑 <b>Привилегия активирована:</b> {item['name']}\n"
                                    f"⏰ <b>Срок:</b> {item['duration']}\n"
                                    f"⭐ <b>Оплачено:</b> {item['stars_text']}\n\n"
                                    f"🎁 Теперь вы можете получать ежедневные бонусы!\n"
                                    f"Спасибо за покупку! ❤️",
                                    parse_mode="HTML"
                                )
                            except Exception as e:
                                logger.error(f"Ошибка активации привилегии: {e}")
                                await message.answer("❌ Ошибка при активации привилегии")
                            finally:
                                db.close()

        except Exception as e:
            logger.error(f"Ошибка обработки платежа: {e}")
            await message.answer("❌ Произошла ошибка при обработке платежа")

    async def check_expired_command(self, message: types.Message):
        """Команда для проверки истекших привилегий (только для админов)"""
        if not await check_admin_async(message):
            return

        try:
            from database import get_db
            from database.models import UserPurchase
            from sqlalchemy import and_

            db = next(get_db())
            current_time = datetime.now()

            # Находим истекшие привилегии
            expired_purchases = db.query(UserPurchase).filter(
                and_(
                    UserPurchase.expires_at.isnot(None),
                    UserPurchase.expires_at <= current_time
                )
            ).all()

            if not expired_purchases:
                await message.reply("✅ Нет истекших привилегий")
                return

            expired_count = 0
            report_lines = []

            for purchase in expired_purchases:
                if hasattr(purchase, 'is_active') and purchase.is_active:
                    purchase.is_active = False
                    expired_count += 1
                    report_lines.append(f"• ID {purchase.user_id} - {purchase.item_name}")

            if expired_count > 0:
                db.commit()
                report = f"✅ Помечено {expired_count} истекших привилегий:\n" + "\n".join(report_lines[:20])
                if len(report_lines) > 20:
                    report += f"\n...и еще {len(report_lines) - 20}"
                await message.reply(report)
            else:
                await message.reply("ℹ️ Все истекшие привилегии уже обработаны")

        except Exception as e:
            await message.reply(f"❌ Ошибка: {str(e)}")


def register_donate_handlers(dp: Dispatcher, bot):
    """Регистрация обработчиков доната"""
    handler = DonateHandler(bot)

    # Регистрация команд доната
    dp.register_message_handler(handler.donate_command, commands=["донат", "donate"], state="*")
    dp.register_message_handler(handler.donate_command,
                                lambda m: m.text and m.text.lower() in ["донат", "donate"],
                                state="*")

    # Регистрация callback обработчиков
    donate_callbacks = [
        "donate_buy_coins_menu", "back_to_buy", "donate_privileges", "daily_bonus",
        "privilege_bonus", "back_to_donate", "claim_bonus", "claim_privilege_bonus",
        "daily_bonus_info", "privilege_bonus_info", "select_coins_", "select_privilege_",
        "pay_stars_", "pay_manual_", "manualpay_cancel_", "check_subscription",
        "donate_already_bought_", "ignore"
    ]
    dp.register_callback_query_handler(handler.donate_callback_handler,
                                       lambda c: any(c.data.startswith(prefix) for prefix in donate_callbacks),
                                       state="*")

    # Админские кнопки approve/deny по ручным платежам (работают в группе)
    dp.register_callback_query_handler(
        handler.manual_admin_callback_handler,
        lambda c: c.data.startswith("manualadmin_"),
        state="*",
    )

    # Приём чеков от пользователей (только если есть ожидающая заявка)
    dp.register_message_handler(
        handler.manual_receipt_handler,
        lambda m: (
            m.chat.type == "private"
            and handler.manual_payment_manager.get_latest_user_request(m.from_user.id, "awaiting_receipt") is not None
        ),
        content_types=[types.ContentType.PHOTO, types.ContentType.DOCUMENT, types.ContentType.TEXT],
        state="*",
    )

    # Регистрация обработчиков платежей
    dp.register_pre_checkout_query_handler(handler.pre_checkout_handler, state="*")
    dp.register_message_handler(
        handler.successful_payment_handler,
        content_types=types.ContentType.SUCCESSFUL_PAYMENT,
        state="*"
    )

    logging.info("✅ Донат обработчики зарегистрированы")