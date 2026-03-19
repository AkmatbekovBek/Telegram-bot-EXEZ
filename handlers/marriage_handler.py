# handlers/marriage_handler.py
import random
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any
from aiogram import types, Dispatcher
from aiogram.utils.callback_data import CallbackData
from database import get_db


class MarriageHandler:
    """Professional Marriage System with Group-Specific Marriages, Pagination and Solo Divorce"""

    def __init__(self):
        self.marriage_messages = {
            "proposal_received": [
                "💍 <b>Приглашение в вечность</b>\n\n{proposer} приглашает {target} разделить жизненный путь!\n\n✨ Судьба стучится в ваше сердце...",
                "🌹 <b>Предложение сердца</b>\n\n{proposer} предлагает {target} создать союз душ!\n\n💫 Ваш момент истины настал...",
                "💞 <b>Призыв судьбы</b>\n\n{proposer} желает пройти с {target} жизненный путь!\n\n🌟 Время сделать выбор...",
            ],
            "marriage_created": [
                "💒 <b>Союз скреплен!</b>\n\n{partner1} 💕 {partner2}\n🌟 Две души объединились в вечном танце!\n📅 {date}",
                "🌈 <b>Новая глава начинается!</b>\n\n{partner1} ✨ {partner2}\n💫 Судьба соединила сердца!\n🗓️ {date}",
                "🌠 <b>Вечность начинается сегодня!</b>\n\n{partner1} ❤️ {partner2}\n✨ Две звезды сошлись в небесах!\n📆 {date}",
            ],
            "divorce_completed": [
                "🌀 <b>Глава закрыта</b>\n\n{partner1} и {partner2} решили пойти разными путями.\n🕊️ Пусть каждый найдет свой новый свет...",
                "🌅 <b>Дороги разошлись</b>\n\n{partner1} и {partner2} завершили совместный путь.\n✨ Иногда расставание - начало новой истории...",
            ],
            "divorce_group_notification": [
                "💔 <b>Пара распалась</b>\n\n{partner1} и {partner2} официально расторгли свой брак.\n🕊️ Иногда пути расходятся, но жизнь продолжается...",
                "🌀 <b>Союз прекращен</b>\n\n{partner1} и {partner2} больше не вместе.\n✨ Пожелаем им найти новые пути к счастью!",
            ],
            "proposal_declined": [
                "💔 {respondent} отклонил(а) предложение руки и сердца от {proposer}\n🌟 Возможно, судьба приготовила другую встречу...",
                "🌀 {respondent} ответил(а) отказом на предложение {proposer}\n✨ Каждому предначертан свой путь...",
            ],
            "already_married": [
                "💍 <b>Вы уже в браке!</b>\n\nВы уже состоите в брачном союзе с {partner} в этой группе.\n\n💔 Если хотите создать новый союз, сначала расторгните текущий брак командой:\n<code>/развод</code>",
                "💞 <b>Брачный статус: занят</b>\n\nВаше сердце уже принадлежит {partner} в этой группе.\n\n🌀 Для нового предложения необходимо:\n<code>/развод</code> → затем новое предложение",
            ],
            "solo_divorce_completed": [
                "💔 <b>Развод оформлен</b>\n\n{user} в одиночку расторг брак с {partner}.\n🕊️ Теперь вы свободны и можете начать новый путь...",
                "🌀 <b>Союз расторгнут</b>\n\n{user} принял решение о разводе с {partner}.\n✨ Иногда нужно идти дальше в одиночку...",
            ],
            "solo_divorce_confirmation": [
                "⚖️ <b>Подтверждение развода</b>\n\nВы уверены, что хотите в одиночку расторгнуть брак с {partner}?\n\n⚠️ Это действие не требует согласия партнера и приведет к немедленному разводу.",
                "💔 <b>Окончательное решение</b>\n\nВы собираетесь расторгнуть брак с {partner} без их участия.\n\n❓ Вы действительно хотите завершить этот союз?",
            ],
            "divorce_cancelled": [
                "💖 <b>Развод отменен</b>\n\nВы решили сохранить брак с {partner}.\n✨ Возможно, это правильное решение...",
                "🌟 <b>Действие отменено</b>\n\nБрак с {partner} остается в силе.\n💫 Иногда стоит дать отношениям второй шанс...",
            ]
        }

        # Хранилище для отслеживания исходных чатов развода
        self.divorce_requests = {}

        # Callback data для пагинации
        self.marriage_pagination_cb = CallbackData("marriage_page", "page", "chat_id")

        # Callback data для одиночного развода
        self.solo_divorce_cb = CallbackData("solo_divorce", "action", "user_id", "partner_id", "chat_id")

        # Количество браков на странице
        self.MARRIAGES_PER_PAGE = 15

    def _get_random_message(self, category: str, **kwargs) -> str:
        """Get random message from category with formatting"""
        template = random.choice(self.marriage_messages[category])
        return template.format(**kwargs)

    def _get_time_difference(self, start_time: datetime) -> str:
        """Calculate human-readable time difference in days only"""
        try:
            now = datetime.now(timezone.utc)

            if start_time.tzinfo is not None:
                start_time_utc = start_time.astimezone(timezone.utc)
            else:
                start_time_utc = start_time.replace(tzinfo=timezone.utc)

            delta = now - start_time_utc
            days = delta.days

            if days < 0:
                return "сегодня"

            if days == 0:
                return "сегодня"
            elif days == 1:
                return "1 день"
            elif 2 <= days <= 4:
                return f"{days} дня"
            else:
                return f"{days} дней"

        except Exception as e:
            print(f"Time calculation error: {e}")
            return "неизвестно"

    def _create_user_link(self, user_id: int, first_name: str) -> str:
        """Create safe user profile link"""
        safe_name = first_name.replace('<', '&lt;').replace('>', '&gt;')
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

    def _get_marriage_data(self, user_id: int, chat_id: int) -> Optional[Tuple]:
        """Get marriage data for specific chat with error handling"""
        db = next(get_db())
        try:
            from sqlalchemy import text
            result = db.execute(
                text("""
                     SELECT id, user1, user2, married_at, chat_id
                     FROM marriages
                     WHERE chat_id = :chat_id
                       AND (user1 = :user_id OR user2 = :user_id)
                     """),
                {"user_id": user_id, "chat_id": chat_id}
            ).fetchone()
            return result
        except Exception as e:
            print(f"Database error in _get_marriage_data: {e}")
            # Fallback: попробуем без chat_id для обратной совместимости
            try:
                result = db.execute(
                    text("""
                         SELECT id, user1, user2, married_at
                         FROM marriages
                         WHERE (user1 = :user_id OR user2 = :user_id)
                         """),
                    {"user_id": user_id}
                ).fetchone()
                if result:
                    # Добавляем chat_id как None для совместимости
                    return result + (None,)
                return None
            except Exception as e2:
                print(f"Fallback error: {e2}")
                return None
        finally:
            db.close()

    def _is_user_married(self, user_id: int, chat_id: int) -> bool:
        """Check if user is married in specific chat"""
        return self._get_marriage_data(user_id, chat_id) is not None

    def _get_partner_info(self, user_id: int, chat_id: int) -> Tuple[Optional[int], Optional[datetime], Optional[int]]:
        """Get partner information for specific chat"""
        marriage = self._get_marriage_data(user_id, chat_id)
        if not marriage:
            return None, None, None

        # Обрабатываем разные случаи возвращаемых данных
        if len(marriage) == 4:  # Старая структура без chat_id
            marriage_id, u1, u2, married_at = marriage
            chat_id_from_db = None
        else:  # Новая структура с chat_id
            marriage_id, u1, u2, married_at, chat_id_from_db = marriage

        partner_id = u2 if u1 == user_id else u1
        return partner_id, married_at, marriage_id

    async def _get_user_display_info(self, bot, user_id: int, default_name: str = "Пользователь") -> Tuple[str, str]:
        """Get user info for display with fallbacks"""
        try:
            user_chat = await bot.get_chat(user_id)
            display_name = user_chat.first_name or user_chat.username or default_name
            user_link = self._create_user_link(user_id, display_name)
            return user_link, display_name
        except Exception:
            return default_name, default_name

    async def _validate_marriage_proposal(self, message: types.Message, target_id: int) -> Optional[str]:
        """Validate marriage proposal conditions"""
        proposer_id = message.from_user.id
        chat_id = message.chat.id

        if self._is_user_married(proposer_id, chat_id):
            partner_id, _, _ = self._get_partner_info(proposer_id, chat_id)
            partner_link, _ = await self._get_user_display_info(message.bot, partner_id)

            already_married_msg = self._get_random_message(
                "already_married",
                partner=partner_link
            )
            return already_married_msg

        if proposer_id == target_id:
            return "🌀 Нельзя предложить брак самому себе."

        if self._is_user_married(target_id, chat_id):
            return "💫 Этот пользователь уже нашел свою половинку в этой группе."

        return None

    async def _store_divorce_request_context(self, requester_id: int, partner_id: int, chat_id: int, message_id: int):
        """Store divorce request context for group notifications"""
        key = f"{requester_id}_{partner_id}_{chat_id}"
        self.divorce_requests[key] = {
            'chat_id': chat_id,
            'message_id': message_id,
            'timestamp': datetime.now()
        }

    async def _get_divorce_request_context(self, requester_id: int, partner_id: int, chat_id: int):
        """Get stored divorce request context"""
        key = f"{requester_id}_{partner_id}_{chat_id}"
        return self.divorce_requests.get(key)

    async def _cleanup_divorce_request_context(self, requester_id: int, partner_id: int, chat_id: int):
        """Clean up stored divorce request context"""
        key = f"{requester_id}_{partner_id}_{chat_id}"
        self.divorce_requests.pop(key, None)

    async def _send_group_divorce_notification(self, bot, chat_id: int, requester_link: str, partner_link: str):
        """Send divorce notification to original group chat"""
        try:
            notification_text = self._get_random_message(
                "divorce_group_notification",
                partner1=requester_link,
                partner2=partner_link
            )

            await bot.send_message(
                chat_id,
                notification_text,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Group notification error: {e}")

    def _create_pagination_keyboard(self, page: int, total_pages: int, chat_id: int) -> types.InlineKeyboardMarkup:
        """Create pagination keyboard for marriages list"""
        keyboard = types.InlineKeyboardMarkup(row_width=5)

        buttons = []

        # Добавляем кнопку "Назад" если не на первой странице
        if page > 0:
            buttons.append(
                types.InlineKeyboardButton(
                    "◀️ Назад",
                    callback_data=self.marriage_pagination_cb.new(page=page - 1, chat_id=chat_id)
                )
            )
        else:
            # Пустая кнопка для сохранения структуры
            buttons.append(
                types.InlineKeyboardButton(
                    " ",
                    callback_data="noop"
                )
            )

        # Добавляем номер текущей страницы
        buttons.append(
            types.InlineKeyboardButton(
                f"📄 {page + 1}/{total_pages}",
                callback_data="noop"
            )
        )

        # Добавляем кнопку "Вперед" если не на последней странице
        if page < total_pages - 1:
            buttons.append(
                types.InlineKeyboardButton(
                    "Вперед ▶️",
                    callback_data=self.marriage_pagination_cb.new(page=page + 1, chat_id=chat_id)
                )
            )
        else:
            # Пустая кнопка для сохранения структуры
            buttons.append(
                types.InlineKeyboardButton(
                    " ",
                    callback_data="noop"
                )
            )

        keyboard.row(*buttons)

        # Кнопка обновления
        keyboard.row(
            types.InlineKeyboardButton(
                "🔄 Обновить",
                callback_data=self.marriage_pagination_cb.new(page=page, chat_id=chat_id)
            )
        )

        return keyboard

    def _create_solo_divorce_keyboard(self, user_id: int, partner_id: int, chat_id: int) -> types.InlineKeyboardMarkup:
        """Create keyboard for solo divorce confirmation"""
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton(
                "✅ Да, развестись",
                callback_data=self.solo_divorce_cb.new(
                    action="confirm",
                    user_id=user_id,
                    partner_id=partner_id,
                    chat_id=chat_id
                )
            ),
            types.InlineKeyboardButton(
                "❌ Нет, отменить",
                callback_data=self.solo_divorce_cb.new(
                    action="cancel",
                    user_id=user_id,
                    partner_id=partner_id,
                    chat_id=chat_id
                )
            )
        )
        return keyboard

    async def propose_marriage(self, message: types.Message):
        """💍 Handle marriage proposal with enhanced UX"""

        chat_id = message.chat.id

        # Check if user is already married in this chat (direct command)
        if self._is_user_married(message.from_user.id, chat_id):
            partner_id, _, _ = self._get_partner_info(message.from_user.id, chat_id)
            partner_link, _ = await self._get_user_display_info(message.bot, partner_id)

            already_married_msg = self._get_random_message(
                "already_married",
                partner=partner_link
            )
            await message.reply(already_married_msg, parse_mode="HTML")
            return

        if not message.reply_to_message:
            guidance = (
                "💌 <b>Как сделать предложение:</b>\n\n"
                "1. Найдите сообщение пользователя\n"
                "2. Ответьте на него командой\n"
                "3. Напишите <code>брак</code>\n\n"
                "✨ И пусть судьба улыбнется вам!\n\n"
                f"💬 <i>Этот брак будет действовать только в этой группе</i>"
            )
            await message.reply(guidance, parse_mode="HTML")
            return

        proposer = message.from_user
        target = message.reply_to_message.from_user

        # Validation
        validation_error = await self._validate_marriage_proposal(message, target.id)
        if validation_error:
            await message.reply(validation_error, parse_mode="HTML")
            return

        # Create proposal
        db = next(get_db())
        try:
            from sqlalchemy import text

            # Final conflict check
            existing = db.execute(
                text("""
                     SELECT id
                     FROM marriages
                     WHERE chat_id = :chat_id
                       AND (user1 IN (:u1, :u2) OR user2 IN (:u1, :u2))
                     """),
                {"u1": proposer.id, "u2": target.id, "chat_id": chat_id}
            ).fetchone()

            if existing:
                await message.reply("⚡ Обнаружен конфликт статусов.", parse_mode="HTML")
                return

            # Prepare user info with clickable names
            proposer_link, _ = await self._get_user_display_info(message.bot, proposer.id)
            target_link, _ = await self._get_user_display_info(message.bot, target.id)

            # Create proposal interface
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton(
                    "💖 Принять судьбу",
                    callback_data=f"marriage_accept_{proposer.id}_{target.id}_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    "💔 Отказаться",
                    callback_data=f"marriage_decline_{proposer.id}_{target.id}_{chat_id}"
                )
            )

            # Use proposal message with both clickable names
            proposal_text = self._get_random_message(
                "proposal_received",
                proposer=proposer_link,
                target=target_link
            )

            # Send proposal silently (no confirmation to proposer)
            await message.reply_to_message.reply(
                proposal_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

        except Exception as e:
            print(f"Proposal error: {e}")
            await message.reply("🌪️ Произошла непредвиденная ошибка.", parse_mode="HTML")
        finally:
            db.close()

    async def handle_marriage_response(self, callback: types.CallbackQuery):
        """🤵👰 Process marriage responses"""

        try:
            data_parts = callback.data.split("_")
            if len(data_parts) != 5:
                await callback.answer("Неверные данные", show_alert=True)
                return

            action_type = data_parts[1]
            proposer_id = int(data_parts[2])
            target_id = int(data_parts[3])
            chat_id = int(data_parts[4])
            respondent = callback.from_user

            if respondent.id != target_id:
                await callback.answer("Это предложение не для вас", show_alert=True)
                return

            db = next(get_db())
            try:
                from sqlalchemy import text

                # Get user info with clickable names
                proposer_link, _ = await self._get_user_display_info(callback.bot, proposer_id)
                respondent_link, _ = await self._get_user_display_info(callback.bot, respondent.id)

                if action_type == "accept":
                    # Final validation
                    conflict = db.execute(
                        text("""
                             SELECT id
                             FROM marriages
                             WHERE chat_id = :chat_id
                               AND (user1 IN (:u1, :u2) OR user2 IN (:u1, :u2))
                             """),
                        {"u1": proposer_id, "u2": target_id, "chat_id": chat_id}
                    ).fetchone()

                    if conflict:
                        await callback.answer("Конфликт статусов", show_alert=True)
                        await callback.message.edit_text(
                            "⚡ Предложение устарело",
                            reply_markup=None,
                            parse_mode="HTML"
                        )
                        return

                    # Create marriage
                    marriage_time = datetime.now()
                    db.execute(
                        text("""
                             INSERT INTO marriages (user1, user2, married_at, chat_id)
                             VALUES (:u1, :u2, :at, :chat_id)
                             """),
                        {"u1": proposer_id, "u2": target_id, "at": marriage_time, "chat_id": chat_id}
                    )
                    db.commit()

                    # Update message in original chat with both clickable names
                    marriage_text = self._get_random_message(
                        "marriage_created",
                        partner1=proposer_link,
                        partner2=respondent_link,
                        date=marriage_time.strftime('%d.%m.%Y в %H:%M')
                    )

                    await callback.message.edit_text(
                        marriage_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )

                    # Notify both users in private
                    try:
                        await callback.bot.send_message(
                            proposer_id,
                            f"💞 {respondent_link} принял(а) ваше предложение!\n✨ Теперь вы в браке в этой группе!",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    await callback.answer("💍 Брак заключен!", show_alert=True)

                else:  # Decline
                    # Use decline message with both clickable names
                    decline_text = self._get_random_message(
                        "proposal_declined",
                        respondent=respondent_link,
                        proposer=proposer_link
                    )

                    await callback.message.edit_text(
                        decline_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )

                    try:
                        await callback.bot.send_message(
                            proposer_id,
                            f"💔 {respondent_link} отклонил(а) ваше предложение\n✨ Не отчаивайтесь - ваша половинка ждет вас!",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    await callback.answer("❌ Предложение отклонено", show_alert=True)

            except Exception as e:
                print(f"Response error: {e}")
                await callback.answer("Ошибка системы", show_alert=True)
            finally:
                db.close()

        except Exception as e:
            print(f"Callback error: {e}")
            await callback.answer("Критическая ошибка", show_alert=True)

    async def list_marriages(self, message: types.Message, page: int = 0):
        """📊 Display marriages for current group with pagination"""

        chat_id = message.chat.id
        db = next(get_db())
        try:
            from sqlalchemy import text

            # Получаем общее количество браков в группе
            total_count = db.execute(
                text("""
                     SELECT COUNT(*) as count
                     FROM marriages
                     WHERE chat_id = :chat_id
                     """),
                {"chat_id": chat_id}
            ).scalar() or 0

            if total_count == 0:
                await message.reply(
                    "💫 <b>Пока тихо и пусто...</b>\nСтаньте первой парой, заключившей союз в этой группе!",
                    parse_mode="HTML"
                )
                return

            # Рассчитываем пагинацию
            total_pages = (total_count + self.MARRIAGES_PER_PAGE - 1) // self.MARRIAGES_PER_PAGE
            page = max(0, min(page, total_pages - 1))  # Защита от выхода за границы
            offset = page * self.MARRIAGES_PER_PAGE

            # Получаем браки для текущей страницы
            marriages = db.execute(
                text("""
                     SELECT user1, user2, married_at
                     FROM marriages
                     WHERE chat_id = :chat_id
                     ORDER BY married_at DESC LIMIT :limit
                     OFFSET :offset
                     """),
                {"chat_id": chat_id, "limit": self.MARRIAGES_PER_PAGE, "offset": offset}
            ).fetchall()

            if not marriages:
                await message.reply(
                    "🌀 <b>Страница не найдена</b>\nВернитесь к первой странице.",
                    parse_mode="HTML"
                )
                return

            # Формируем заголовок
            display_text = (
                f"💞 <b>Счастливые пары этой группы</b>\n"
                f"📊 Всего союзов: <b>{total_count}</b>\n"
                f"📄 Страница: <b>{page + 1}/{total_pages}</b>\n"
                f"👥 Показано: <b>{len(marriages)}</b> из <b>{total_count}</b>\n\n"
            )

            # Добавляем информацию о браках
            for idx, (u1, u2, date) in enumerate(marriages, offset + 1):
                u1_link, _ = await self._get_user_display_info(message.bot, u1)
                u2_link, _ = await self._get_user_display_info(message.bot, u2)
                duration = self._get_time_difference(date)

                icons = ["💕", "✨", "❤️", "🌟", "💞", "🥰", "💘", "💝", "💖", "💗"]
                icon = random.choice(icons)

                display_text += (
                    f"{idx}. {u1_link} {icon} {u2_link}\n"
                    f"   ⏳ {duration} вместе\n"
                    f"   📅 {date.strftime('%d.%m.%Y')}\n\n"
                )

            # Создаем клавиатуру пагинации
            keyboard = self._create_pagination_keyboard(page, total_pages, chat_id)

            # Отправляем сообщение
            if isinstance(message, types.Message):
                # Если это новый запрос - отправляем новое сообщение
                await message.reply(
                    display_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            else:
                # Если это обновление пагинации - редактируем существующее
                try:
                    await message.edit_text(
                        display_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
                except Exception:
                    # Если сообщение не может быть отредактировано, отправляем новое
                    await message.message.answer(
                        display_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )

        except Exception as e:
            print(f"List error: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

            error_msg = "🌪️ <b>Ошибка загрузки данных</b>\nПопробуйте позже."

            if isinstance(message, types.Message):
                await message.reply(error_msg, parse_mode="HTML")
            else:
                try:
                    await message.message.edit_text(error_msg, parse_mode="HTML")
                except Exception:
                    await message.message.answer(error_msg, parse_mode="HTML")
        finally:
            db.close()

    async def handle_marriage_pagination(self, callback: types.CallbackQuery, callback_data: Dict[str, str]):
        """Handle pagination for marriages list"""
        try:
            page = int(callback_data.get("page", 0))
            chat_id = int(callback_data.get("chat_id", 0))

            # Проверяем, что пользователь в том же чате
            if callback.message.chat.id != chat_id:
                await callback.answer("Пагинация доступна только в том чате, где был запрос", show_alert=True)
                return

            await self.list_marriages(callback.message, page)
            await callback.answer()

        except Exception as e:
            print(f"Pagination error: {e}")
            await callback.answer("Ошибка при переключении страницы", show_alert=True)

    async def my_marriage(self, message: types.Message):
        """👰🤵 Display user's marriage info for current group"""

        user_id = message.from_user.id
        chat_id = message.chat.id
        marriage = self._get_marriage_data(user_id, chat_id)

        if not marriage:
            await message.reply(
                "💫 <b>Вы свободны как ветер</b>\nНайдите свою половинку и создайте союз в этой группе!",
                parse_mode="HTML"
            )
            return

        # Обрабатываем разные структуры данных
        if len(marriage) == 4:  # Старая структура без chat_id
            _, u1, u2, marriage_time = marriage
        else:  # Новая структура с chat_id
            _, u1, u2, marriage_time, _ = marriage

        partner_id = u2 if u1 == user_id else u1

        user_link, _ = await self._get_user_display_info(message.bot, user_id)
        partner_link, _ = await self._get_user_display_info(message.bot, partner_id)
        duration = self._get_time_difference(marriage_time)

        status_messages = [
            f"💞 <b>Ваш союз в этой группе</b>\n\n{user_link} 💕 {partner_link}\n⏳ Вместе: {duration}\n📅 С: {marriage_time.strftime('%d.%m.%Y')}\n\n✨ Цените каждый момент!",
            f"🌟 <b>Ваша история в этой группе</b>\n\n{user_link} ❤️ {partner_link}\n🕰️ Союз длится: {duration}\n🗓️ Начало: {marriage_time.strftime('%d.%m.%Y')}\n\n💫 Пусть любовь только крепнет!",
            f"💒 <b>Ваш брак в этой группе</b>\n\n{user_link} ✨ {partner_link}\n⏱️ В браке: {duration}\n📆 С: {marriage_time.strftime('%d.%m.%Y')}\n\n🌈 Берегите ваш союз!"
        ]

        await message.reply(random.choice(status_messages), parse_mode="HTML")

    async def handle_solo_divorce(self, callback: types.CallbackQuery, callback_data: Dict[str, str]):
        """Handle solo divorce (without partner consent)"""
        try:
            action = callback_data.get("action")
            user_id = int(callback_data.get("user_id"))
            partner_id = int(callback_data.get("partner_id"))
            chat_id = int(callback_data.get("chat_id"))

            # Проверяем, что пользователь, нажавший кнопку, это инициатор развода
            if callback.from_user.id != user_id:
                await callback.answer("Это действие доступно только инициатору развода", show_alert=True)
                return

            # Получаем информацию о пользователях
            user_link, _ = await self._get_user_display_info(callback.bot, user_id)
            partner_link, _ = await self._get_user_display_info(callback.bot, partner_id)

            db = next(get_db())
            try:
                from sqlalchemy import text

                if action == "confirm":
                    # Удаляем брак из базы данных
                    result = db.execute(
                        text("""
                             DELETE
                             FROM marriages
                             WHERE chat_id = :chat_id
                               AND ((user1 = :u1 AND user2 = :u2) OR (user1 = :u2 AND user2 = :u1))
                             """),
                        {"u1": user_id, "u2": partner_id, "chat_id": chat_id}
                    )
                    db.commit()

                    if result.rowcount > 0:
                        # Успешный развод
                        divorce_text = self._get_random_message(
                            "solo_divorce_completed",
                            user=user_link,
                            partner=partner_link
                        )

                        await callback.message.edit_text(
                            divorce_text,
                            reply_markup=None,
                            parse_mode="HTML"
                        )

                        # Уведомляем партнера (если возможно)
                        try:
                            await callback.bot.send_message(
                                partner_id,
                                f"💔 {user_link} в одностороннем порядке расторг брак с вами в этой группе.\n🕊️ Союз завершен.",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass

                        # Отправляем уведомление в группу
                        await self._send_group_divorce_notification(
                            callback.bot,
                            chat_id,
                            user_link,
                            partner_link
                        )

                        await callback.answer("💔 Брак расторгнут", show_alert=True)
                    else:
                        await callback.answer("Брак не найден", show_alert=True)

                elif action == "cancel":
                    # Отмена развода
                    cancel_text = self._get_random_message(
                        "divorce_cancelled",
                        partner=partner_link
                    )

                    await callback.message.edit_text(
                        cancel_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )

                    await callback.answer("💖 Развод отменен", show_alert=True)

            except Exception as e:
                print(f"Solo divorce error: {e}")
                await callback.answer("Ошибка при обработке развода", show_alert=True)
            finally:
                db.close()

        except Exception as e:
            print(f"Solo divorce callback error: {e}")
            await callback.answer("Критическая ошибка", show_alert=True)

    async def request_divorce(self, message: types.Message):
        """💔 Handle divorce with both options: mutual and solo"""

        user_id = message.from_user.id
        chat_id = message.chat.id

        if not self._is_user_married(user_id, chat_id):
            await message.reply(
                "💫 <b>Нечего расторгать</b>\nВы не состоите в браке в этой группе.",
                parse_mode="HTML"
            )
            return

        partner_id, marriage_time, _ = self._get_partner_info(user_id, chat_id)

        if not partner_id:
            await message.reply(
                "❌ <b>Ошибка данных</b>\nНе удалось найти информацию о партнере.",
                parse_mode="HTML"
            )
            return

        # Проверяем, хочет ли пользователь одиночный развод или совместный
        # Если текст содержит "развод" без дополнительных параметров - предлагаем выбор

        # Создаем меню выбора типа развода
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton(
                "💔 Развод по согласию",
                callback_data=f"mutual_divorce_start_{user_id}_{partner_id}_{chat_id}"
            )
        )
        keyboard.row(
            types.InlineKeyboardButton(
                "⚖️ Одиночный развод (без согласия)",
                callback_data=f"solo_divorce_start_{user_id}_{partner_id}_{chat_id}"
            )
        )

        await message.reply(
            "⚖️ <b>Выберите тип развода:</b>\n\n"
            "1. <b>Развод по согласию</b> - требует подтверждения партнера\n"
            "2. <b>Одиночный развод</b> - без участия партнера (немедленный)\n\n"
            "💫 Выберите подходящий вариант:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    async def start_solo_divorce(self, callback: types.CallbackQuery):
        """Start solo divorce process"""
        try:
            data_parts = callback.data.split("_")
            if len(data_parts) != 6:
                await callback.answer("Неверные данные", show_alert=True)
                return

            user_id = int(data_parts[3])
            partner_id = int(data_parts[4])
            chat_id = int(data_parts[5])

            # Проверяем, что пользователь, нажавший кнопку, это инициатор
            if callback.from_user.id != user_id:
                await callback.answer("Это действие доступно только вам", show_alert=True)
                return

            # Получаем информацию о партнере
            partner_link, _ = await self._get_user_display_info(callback.bot, partner_id)

            # Создаем сообщение с подтверждением одиночного развода
            confirmation_text = self._get_random_message(
                "solo_divorce_confirmation",
                partner=partner_link
            )

            keyboard = self._create_solo_divorce_keyboard(user_id, partner_id, chat_id)

            await callback.message.edit_text(
                confirmation_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

        except Exception as e:
            print(f"Start solo divorce error: {e}")
            await callback.answer("Ошибка при запуске развода", show_alert=True)

    async def start_mutual_divorce(self, callback: types.CallbackQuery):
        """Start mutual divorce process (requires partner consent)"""
        try:
            data_parts = callback.data.split("_")
            if len(data_parts) != 6:
                await callback.answer("Неверные данные", show_alert=True)
                return

            user_id = int(data_parts[3])
            partner_id = int(data_parts[4])
            chat_id = int(data_parts[5])

            # Проверяем, что пользователь, нажавший кнопку, это инициатор
            if callback.from_user.id != user_id:
                await callback.answer("Это действие доступно только вам", show_alert=True)
                return

            # Дальнейшая обработка развода по согласию (существующая логика)
            # Здесь вызываем существующий метод request_divorce_with_consent
            # или используем логику из существующего метода request_divorce

            # Для совместимости с существующим кодом, отправляем команду развода
            # которая будет обработана как развод по согласию
            from aiogram.types import Message
            fake_message = Message(
                message_id=callback.message.message_id,
                date=datetime.now(),
                chat=callback.message.chat,
                text="/развод",
                from_user=callback.from_user,
                bot=callback.bot
            )

            # Вызываем существующую логику развода по согласию
            await self.request_divorce_with_consent(fake_message)

        except Exception as e:
            print(f"Start mutual divorce error: {e}")
            await callback.answer("Ошибка при запуске развода", show_alert=True)

    async def request_divorce_with_consent(self, message: types.Message):
        """💔 Handle mutual divorce (requires partner consent)"""

        # Это существующая логика развода по согласию
        user_id = message.from_user.id
        chat_id = message.chat.id

        if not self._is_user_married(user_id, chat_id):
            await message.answer(
                "💫 <b>Нечего расторгать</b>\nВы не состоите в браке в этой группе.",
                parse_mode="HTML"
            )
            return

        partner_id, marriage_time, _ = self._get_partner_info(user_id, chat_id)

        if not partner_id:
            await message.answer(
                "❌ <b>Ошибка данных</b>\nНе удалось найти информацию о партнере.",
                parse_mode="HTML"
            )
            return

        db = next(get_db())
        try:
            from sqlalchemy import text

            # Check existing requests for this chat
            existing = db.execute(
                text("""
                     SELECT id
                     FROM divorce_requests
                     WHERE chat_id = :chat_id
                       AND (requester = :uid OR partner = :uid)
                     """),
                {"uid": user_id, "chat_id": chat_id}
            ).fetchone()

            if existing:
                await message.answer(
                    "⏳ <b>Запрос уже отправлен</b>\nОжидайте ответа второй стороны.",
                    parse_mode="HTML"
                )
                return

            user_link, _ = await self._get_user_display_info(message.bot, user_id)
            partner_link, _ = await self._get_user_display_info(message.bot, partner_id)

            # Create divorce request
            db.execute(
                text("""
                     INSERT INTO divorce_requests (requester, partner, requested_at, chat_id)
                     VALUES (:r, :p, :at, :chat_id)
                     """),
                {"r": user_id, "p": partner_id, "at": datetime.now(), "chat_id": chat_id}
            )
            db.commit()

            # Store divorce request context for group notifications
            await self._store_divorce_request_context(
                user_id,
                partner_id,
                chat_id,
                message.message_id
            )

            # Create divorce interface
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton(
                    "💔 Подтвердить развод",
                    callback_data=f"divorce_yes_{user_id}_{partner_id}_{chat_id}"
                ),
                types.InlineKeyboardButton(
                    "💖 Сохранить брак",
                    callback_data=f"divorce_no_{user_id}_{partner_id}_{chat_id}"
                )
            )

            divorce_messages = [
                f"💔 <b>Запрос на развод</b>\n\n{user_link} хочет расторгнуть брак с {partner_link}.\n⏳ Вместе: {self._get_time_difference(marriage_time)}\n\n⚠️ Внимательно обдумайте решение...",
                f"🌀 <b>Кризис в отношениях</b>\n\n{user_link} подал(а) на развод с {partner_link}.\n🕰️ Длительность союза: {self._get_time_difference(marriage_time)}\n\n💫 Возможно, это повод для диалога...",
                f"🌅 <b>Переломный момент</b>\n\n{user_link} желает завершить брак с {partner_link}.\n⏱️ В браке: {self._get_time_difference(marriage_time)}\n\n✨ Примите мудрое решение..."
            ]

            # Send to partner
            try:
                await message.bot.send_message(
                    partner_id,
                    random.choice(divorce_messages),
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

                # Notify requester
                await message.answer(
                    "💌 <b>Запрос отправлен</b>\nОжидайте решения второй стороны...",
                    parse_mode="HTML"
                )

            except Exception as e:
                print(f"Ошибка отправки сообщения партнеру: {e}")
                await message.answer(
                    "❌ Не удалось уведомить партнера. Возможно, у него закрытые ЛС.",
                    parse_mode="HTML"
                )
                # Cleanup
                db.execute(
                    text("""
                         DELETE
                         FROM divorce_requests
                         WHERE requester = :r
                           AND partner = :p
                           AND chat_id = :chat_id
                         """),
                    {"r": user_id, "p": partner_id, "chat_id": chat_id}
                )
                db.commit()
                await self._cleanup_divorce_request_context(user_id, partner_id, chat_id)

        except Exception as e:
            print(f"Divorce request error: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

            # Более информативное сообщение об ошибке
            error_msg = (
                "🌪️ <b>Произошла ошибка при обработке запроса</b>\n\n"
                "Попробуйте позже или обратитесь к администратору."
            )
            await message.answer(error_msg, parse_mode="HTML")
        finally:
            db.close()

    async def handle_divorce_response(self, callback: types.CallbackQuery):
        """⚖️ Process mutual divorce responses with group notifications"""

        try:
            data_parts = callback.data.split("_")
            if len(data_parts) != 5:
                await callback.answer("Неверные данные", show_alert=True)
                return

            response_type = data_parts[1]
            requester_id = int(data_parts[2])
            partner_id = int(data_parts[3])
            chat_id = int(data_parts[4])
            respondent = callback.from_user

            if respondent.id != partner_id:
                await callback.answer("Это не ваш запрос", show_alert=True)
                return

            db = next(get_db())
            try:
                from sqlalchemy import text

                # Validate request for this chat
                divorce_req = db.execute(
                    text("""
                         SELECT id
                         FROM divorce_requests
                         WHERE requester = :r
                           AND partner = :p
                           AND chat_id = :chat_id
                         """),
                    {"r": requester_id, "p": partner_id, "chat_id": chat_id}
                ).fetchone()

                if not divorce_req:
                    await callback.answer("Запрос устарел", show_alert=True)
                    return

                requester_link, _ = await self._get_user_display_info(callback.bot, requester_id)
                respondent_link, _ = await self._get_user_display_info(callback.bot, respondent.id)

                if response_type == "yes":
                    # Process divorce for this chat
                    db.execute(
                        text("""
                             DELETE
                             FROM marriages
                             WHERE chat_id = :chat_id
                               AND ((user1 = :u1 AND user2 = :u2) OR (user1 = :u2 AND user2 = :u1))
                             """),
                        {"u1": requester_id, "u2": partner_id, "chat_id": chat_id}
                    )
                    db.execute(
                        text("DELETE FROM divorce_requests WHERE id = :id"),
                        {"id": divorce_req[0]}
                    )
                    db.commit()

                    # Get stored group chat context
                    group_context = await self._get_divorce_request_context(requester_id, partner_id, chat_id)

                    # Send notification to original group chat if available
                    if group_context:
                        await self._send_group_divorce_notification(
                            callback.bot,
                            group_context['chat_id'],
                            requester_link,
                            respondent_link
                        )

                    # Update callback message
                    divorce_text = self._get_random_message(
                        "divorce_completed",
                        partner1=requester_link,
                        partner2=respondent_link
                    )

                    await callback.message.edit_text(
                        divorce_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )

                    # Notify both users
                    try:
                        await callback.bot.send_message(
                            requester_id,
                            f"💔 {respondent_link} подтвердил(а) развод\n🕊️ Брак в этой группе расторгнут.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    # Cleanup stored context
                    await self._cleanup_divorce_request_context(requester_id, partner_id, chat_id)

                    await callback.answer("💔 Брак расторгнут", show_alert=True)

                else:  # Decline divorce
                    db.execute(
                        text("DELETE FROM divorce_requests WHERE id = :id"),
                        {"id": divorce_req[0]}
                    )
                    db.commit()

                    # Cleanup stored context
                    await self._cleanup_divorce_request_context(requester_id, partner_id, chat_id)

                    await callback.message.edit_text(
                        "💖 <b>Брак сохранен</b>\nВы сохранили ваш союз в этой группе!",
                        reply_markup=None,
                        parse_mode="HTML"
                    )

                    try:
                        await callback.bot.send_message(
                            requester_id,
                            f"💞 {respondent_link} сохранил(а) ваш брак!\n✨ Дайте отношениям второй шанс!",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    await callback.answer("💖 Брак сохранен", show_alert=True)

            except Exception as e:
                print(f"Divorce processing error: {e}")
                await callback.answer("Ошибка системы", show_alert=True)
            finally:
                db.close()

        except Exception as e:
            print(f"Divorce callback error: {e}")
            await callback.answer("Критическая ошибка", show_alert=True)


def register_marriage_handlers(dp: Dispatcher):
    """🚀 Register marriage system handlers"""

    handler = MarriageHandler()

    # Command handlers with exact matching
    dp.register_message_handler(
        handler.propose_marriage,
        lambda msg: msg.text and msg.text.lower().strip() in ["брак", "!брак", "/брак"]
    )

    dp.register_message_handler(
        lambda msg: handler.list_marriages(msg, 0),  # Начинаем с первой страницы
        lambda msg: msg.text and msg.text.lower().strip() in ["браки", "!браки", "/браки"]
    )

    dp.register_message_handler(
        handler.my_marriage,
        lambda msg: msg.text and msg.text.lower().strip() in ["мой брак", "!мой брак", "/мой брак"]
    )

    dp.register_message_handler(
        handler.request_divorce,
        lambda msg: msg.text and msg.text.lower().strip() in ["развод", "!развод", "/развод"]
    )

    # Callback handlers
    dp.register_callback_query_handler(
        handler.handle_marriage_response,
        lambda c: c.data and c.data.startswith(("marriage_accept_", "marriage_decline_"))
    )

    dp.register_callback_query_handler(
        handler.handle_divorce_response,
        lambda c: c.data and c.data.startswith(("divorce_yes_", "divorce_no_"))
    )

    # Handler для запуска одиночного развода
    dp.register_callback_query_handler(
        handler.start_solo_divorce,
        lambda c: c.data and c.data.startswith("solo_divorce_start_")
    )

    # Handler для запуска развода по согласию
    dp.register_callback_query_handler(
        handler.start_mutual_divorce,
        lambda c: c.data and c.data.startswith("mutual_divorce_start_")
    )

    # Handler для обработки одиночного развода
    dp.register_callback_query_handler(
        handler.handle_solo_divorce,
        handler.solo_divorce_cb.filter()
    )

    # Пагинация для списка браков
    dp.register_callback_query_handler(
        handler.handle_marriage_pagination,
        handler.marriage_pagination_cb.filter()
    )

    print("💍 Marriage System: Group-Specific Edition with Solo Divorce Activated")