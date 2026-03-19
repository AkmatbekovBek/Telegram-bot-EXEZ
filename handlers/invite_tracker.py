# -*- coding: utf-8 -*-
# handlers/invite_tracker.py
import logging
from aiogram import types, Dispatcher
from aiogram.utils.deep_linking import get_start_link
from database import get_db
from database.crud import GroupInviteRepository, UserRepository, BotSearchRepository
from datetime import datetime
from database.models import GroupInvite  # Добавьте эту строку
logger = logging.getLogger(__name__)


class InviteTrackerHandler:
    """Обработчик для отслеживания приглашенных пользователей"""

    async def mymembers_command(self, message: types.Message):
        """Обработчик команды /mymembers"""
        try:
            db = next(get_db())

            # Статистика должна быть раздельной для каждой группы
            if message.chat.type == types.ChatType.PRIVATE:
                await message.reply("❌ Эта команда работает только в группе")
                return

            # Получаем информацию о пользователе
            user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
            if not user:
                await message.reply("❌ Пользователь не найден")
                return

            # Получаем количество приглашенных В ТЕКУЩЕЙ ГРУППЕ
            count = GroupInviteRepository.get_invites_count(
                db,
                message.from_user.id,
                message.chat.id
            )

            # Форматируем имя пользователя
            username = user.username or user.first_name or f"Пользователь {message.from_user.id}"

            # Формируем ответ
            chat_title = message.chat.title or "эта группа"
            response = f"👤 {username}\n\n🔹 В группе «{chat_title}» вы добавили {count} человек!"

            await message.reply(response)

        except Exception as e:
            logger.error(f"❌ Ошибка в mymembers_command: {e}")
            await message.reply("❌ Ошибка при выполнении команды")
        finally:
            db.close()

    async def clear_exez_command(self, message: types.Message):
        """Обработчик команды /clear_exez (сброс своих приглашений)"""
        try:
            db = next(get_db())

            if message.chat.type == types.ChatType.PRIVATE:
                await message.reply("❌ Эта команда работает только в группе")
                return

            # Сбрасываем приглашения
            deleted_count = GroupInviteRepository.reset_invites(
                db,
                message.from_user.id,
                message.chat.id
            )

            if deleted_count > 0:
                await message.reply(f"✅ Ваш счетчик приглашений в этой группе сброшен.\n🗑 Удалено записей: {deleted_count}")
            elif deleted_count == 0:
                await message.reply("ℹ️ У вас нет приглашений в этой группе.")
            else:
                await message.reply("❌ Произошла ошибка при сбросе счетчика.")

        except Exception as e:
            logger.error(f"❌ Ошибка в clear_exez_command: {e}")
            await message.reply("❌ Ошибка при выполнении команды")
        finally:
            db.close()

    async def check_new_member(self, message: types.Message):
        """Обрабатывает событие нового участника в группе (улучшенная версия)"""
        try:
            # Проверяем, что это действительно новый участник
            if not message.new_chat_members:
                return

            db = next(get_db())

            # Определяем, кто пригласил (сложная логика для закрытых групп)
            inviter_id = None

            # Способ 1: Проверяем, есть ли в user_data информация о приглашении
            # (если пользователь перешел по invite ссылке)
            for new_member in message.new_chat_members:
                if new_member.id == message.bot.id:
                    continue

                try:
                    # Ищем последнего пригласившего для этого пользователя
                    # (ищем приглашения с chat_id=0 - временные)
                    from database.models import GroupInvite
                    temp_invite = db.query(GroupInvite).filter(
                        GroupInvite.invited_id == new_member.id,
                        GroupInvite.chat_id == 0
                    ).order_by(GroupInvite.invited_at.desc()).first()

                    if temp_invite:
                        # Нашли временное приглашение - обновляем chat_id
                        inviter_id = temp_invite.inviter_id
                        temp_invite.chat_id = message.chat.id
                        temp_invite.invited_at = datetime.now()
                        db.commit() # Сохраняем обновление
                        logger.info(f"✅ Обновлено приглашение: {inviter_id} -> {new_member.id} в чат {message.chat.id}")

                    else:
                        # Способ 2: Если нет временного приглашения,
                        # пытаемся определить пригласившего по последней активности
                        # (пользователь, который недавно отправлял /invitelink)
                        # ИЛИ используем from_user.id как fallback

                        # Для закрытых групп: тот, кто подтвердил заявку (from_user.id)
                        if message.from_user.id != new_member.id:
                            inviter_id = message.from_user.id
                        else:
                            # Если это сам бот добавил или неизвестно кто
                            # Можем проверить администраторов группы
                            try:
                                admins = await message.bot.get_chat_administrators(message.chat.id)
                                for admin in admins:
                                    if not admin.user.is_bot and admin.status in ['creator', 'administrator']:
                                        inviter_id = admin.user.id
                                        break
                            except Exception:
                                pass

                    # Если нашли пригласившего, добавляем запись
                    if inviter_id and inviter_id != new_member.id:
                        # Проверяем, не существует ли уже такая запись
                        existing = db.query(GroupInvite).filter(
                            GroupInvite.inviter_id == inviter_id,
                            GroupInvite.invited_id == new_member.id,
                            GroupInvite.chat_id == message.chat.id
                        ).first()

                        if not existing:
                            GroupInviteRepository.add_invite(
                                db=db,
                                inviter_id=inviter_id,
                                invited_id=new_member.id,
                                chat_id=message.chat.id
                            )

                            # Логируем активность для поиска
                            try:
                                chat_title = message.chat.title or f"Чат {message.chat.id}"
                                BotSearchRepository.log_user_activity(
                                    db=db,
                                    user_id=inviter_id,
                                    chat_id=message.chat.id,
                                    chat_title=chat_title,
                                    nick=new_member.first_name or new_member.username or str(new_member.id)
                                )
                            except Exception as log_error:
                                logger.error(f"❌ Ошибка логирования активности: {log_error}")

                            # Отправляем уведомление о приглашении
                            # Для массовых приглашений (когда много людей) можно пропускать или отправлять только иногда
                            if len(message.new_chat_members) < 5: 
                                try:
                                    inviter_name = "Кто-то"
                                    # Пытаемся получить имя пригласившего, но безопасно
                                    try:
                                        inviter = await message.bot.get_chat(inviter_id)
                                        if inviter:
                                            inviter_name = inviter.first_name or inviter.username or inviter_name
                                    except:
                                        pass

                                    await message.answer(
                                        f"\U0001F680Доступ открыт. {new_member.first_name} присоединился по приглашению !"
                                    )
                                except Exception as notify_error:
                                    logger.error(f"❌ Ошибка отправки уведомления: {notify_error}")

                except Exception as inner_e:
                    logger.error(f"❌ Ошибка обработки участника {new_member.id}: {inner_e}")
                    # Продолжаем цикл для следующего участника

            # db.commit() # Уже коммитится внутри методов


        except Exception as e:
            logger.error(f"❌ Ошибка в check_new_member: {e}")
        finally:
            db.close()

    async def generate_invite_link(self, message: types.Message):
        """Генерация персональной пригласительной ссылки"""
        try:
            db = next(get_db())

            # Генерируем уникальную ссылку
            payload = f"invite_{message.from_user.id}"

            # Проверяем, что бот имеет права администратора для создания инвайт-ссылок
            try:
                # Пытаемся создать инвайт-ссылку для группы
                if message.chat.type != types.ChatType.PRIVATE:
                    chat_invite_link = await message.bot.create_chat_invite_link(
                        chat_id=message.chat.id,
                        creator_id=message.from_user.id,
                        name=f"Приглашение от {message.from_user.first_name or message.from_user.id}",
                        member_limit=1  # Одноразовая ссылка
                    )

                    await message.reply(
                        f"🔗 Ваша персональная пригласительная ссылка для этой группы:\n\n"
                        f"{chat_invite_link.invite_link}\n\n"
                        f"📌 Отправьте эту ссылку другу.\n"
                        f"📊 Когда он вступит в группу, это будет засчитано в вашей статистике.\n"
                        f"⚠️ Ссылка одноразовая и перестанет работать после первого использования."
                    )
                    return
            except Exception as e:
                logger.error(f"❌ Не удалось создать инвайт-ссылку для группы: {e}")
                # Fallback на стартовую ссылку бота

            # Fallback: ссылка для запуска бота
            invite_link = await get_start_link(payload=payload, encode=True)

            await message.reply(
                f"🔗 Ваша персональная ссылка для приглашений:\n\n"
                f"{invite_link}\n\n"
                f"📌 Отправьте эту ссылку другу.\n"
                f"📊 Когда он перейдет по ссылке и вступит в группу, "
                f"это будет засчитано в вашей статистике.\n\n"
                f"ℹ️ Для работы системы приглашений:\n"
                f"1. Друг переходит по вашей ссылке\n"
                f"2. Запускает бота через /start\n"
                f"3. Вступает в группу по той же ссылке\n"
                f"4. Его вступление засчитывается вам"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка генерации ссылки: {e}")
            await message.reply("❌ Ошибка генерации ссылки")
        finally:
            db.close()

    async def handle_chat_member_updated(self, update: types.ChatMemberUpdated):
        """Обработчик обновления статуса участника чата (для закрытых групп)"""
        try:
            # Этот обработчик лучше подходит для закрытых групп с заявками
            if update.new_chat_member.status in ['member', 'restricted']:
                # Пользователь принят в группу (через заявку или одобрение)

                db = next(get_db())

                # Определяем, кто принял заявку (администратор)
                # В Telegram API обычно это from_user в событии
                inviter_id = None

                if update.from_user and update.from_user.id != update.new_chat_member.user.id:
                    # Если есть информация о том, кто принял заявку
                    inviter_id = update.from_user.id
                else:
                    # Пытаемся найти по временным приглашениям
                    temp_invite = db.query(GroupInvite).filter(
                        GroupInvite.invited_id == update.new_chat_member.user.id,
                        GroupInvite.chat_id == 0
                    ).order_by(GroupInvite.invited_at.desc()).first()

                    if temp_invite:
                        inviter_id = temp_invite.inviter_id

                if inviter_id:
                    # Добавляем запись о приглашении
                    existing = db.query(GroupInvite).filter(
                        GroupInvite.inviter_id == inviter_id,
                        GroupInvite.invited_id == update.new_chat_member.user.id,
                        GroupInvite.chat_id == update.chat.id
                    ).first()

                    if not existing:
                        GroupInviteRepository.add_invite(
                            db=db,
                            inviter_id=inviter_id,
                            invited_id=update.new_chat_member.user.id,
                            chat_id=update.chat.id
                        )

                        logger.info(
                            f"✅ Учет через chat_member_updated: {inviter_id} -> {update.new_chat_member.user.id} в чат {update.chat.id}")

                        # Отправляем уведомление
                        try:
                            await update.bot.send_message(
                                update.chat.id,
                                f"\U0001F680Доступ открыт. {update.new_chat_member.user.first_name} присоединился по приглашению !"
                            )
                        except:
                            pass

                db.commit()
                db.close()

        except Exception as e:
            logger.error(f"❌ Ошибка обработки chat_member_updated: {e}")


def register_invite_tracker_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    handler = InviteTrackerHandler()

    # Команда для просмотра статистики
    dp.register_message_handler(
        handler.mymembers_command,
        commands=['my', 'mymembers', 'myinvites', 'пригласил']
    )

    dp.register_message_handler(
        handler.generate_invite_link,
        commands=['invitelink', 'пригласить', 'ссылка']
    )

    # Команда для сброса своих приглашений
    dp.register_message_handler(
        handler.clear_exez_command,
        commands=['clear_exez']
    )

    # Отслеживание новых участников
    dp.register_message_handler(
        handler.check_new_member,
        content_types=types.ContentTypes.NEW_CHAT_MEMBERS
    )

    # Отслеживание обновлений статуса участников (для закрытых групп)
    dp.register_chat_member_handler(handler.handle_chat_member_updated)

    logger.info("✅ InviteTrackerHandler зарегистрирован")