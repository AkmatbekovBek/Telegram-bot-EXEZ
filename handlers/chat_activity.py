import logging
import math
from typing import List, Tuple

from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from sqlalchemy import desc

from database import SessionLocal
from database.chat_activity import ChatActivityRepository, ChatActivity

logger = logging.getLogger(__name__)


# Пагинация для вывода списка активности
ACTIVITY_PAGE_SIZE = 10
ACTIVITY_CB_PREFIX = "act"  # callback_data: act:<chat_id>:<page>


class ChatActivityHandler:
    """Обработчик активности в чатах"""

    def __init__(self):
        # Импортируем UserFormatter из start.py
        from handlers.start import UserFormatter
        self.user_formatter = UserFormatter()

        # Команды, которые не должны отслеживаться
        self.ignored_prefixes = [
            # Команды из inviter
            '/my', '/mymembers', '/addinv',

            # Бот команды
            'бот ищи', 'бот очисти', 'бот статистика', 'ботстоп', 'бот стоп',
            'bot_stop', 'stopbot',

            # Подарки и магазин
            'подарки', 'мои подарки', 'магазин подарков', 'дарю', 'подарить', 'подарок', 'магазин',
            'shop', 'купить',

            # Админ команды
            'мут', 'бан', 'размут', 'разбан', 'очистка', 'очистить',

            # Игры
            'рулетка', 'кубик', 'кража', 'полиция', 'брак', 'развод',
            'розыгрыш', 'гонка', 'слот', 'камень ножницы бумага', 'кнб',

            # Прочее
            'рекорд', 'перевод', 'донат', 'админ', 'статус', 'рефералы',
            'приглашение', 'инвайт', 'мои',

            # Команды с ! (которые не наши)
            '!бот', '!подарки', '!магазин', '!рекорд', '!рулетка',
            '!кубик', '!кража', '!полиция'
        ]

        # Короткие команды (первое слово)
        self.short_commands = {
            'ботстоп', 'стоп', 'stop', 'поиск', 'статистика', 'стата',
            'подарки', 'магазин', 'рекорд', 'рулетка', 'кубик', 'кража',
            'полиция', 'брак', 'развод', 'розыгрыш', 'гонка', 'слот',
            'кнб', 'перевод', 'донат', 'мут', 'бан', 'размут', 'разбан',
            'очистка', 'приглашение', 'инвайт', 'мои', 'мой', 'my',
            'addinv', 'инвайты', 'приглашения'
        }

    def should_track_message(self, message: types.Message) -> bool:
        """Проверяет, нужно ли отслеживать сообщение (синхронный метод)"""
        # Проверяем наличие текста
        if not message.text or not message.text.strip():
            return False

        # Отслеживаем только в группах/супергруппах
        if message.chat.type not in ['group', 'supergroup']:
            return False

        text = message.text.strip()
        text_lower = text.lower()

        # 1. Исключаем команды, начинающиеся с /
        if text_lower.startswith('/'):
            # Разбиваем команду для проверки
            parts = text_lower.split()
            if parts:
                cmd = parts[0]
                # Проверяем команды из inviter
                if cmd in ['/my', '/mymembers', '/addinv']:
                    return False
                # Исключаем все команды с /
                return False
            return False

        # 2. Исключаем команды, начинающиеся с ! (кроме наших)
        if text_lower.startswith('!'):
            # Проверяем наши команды (они должны быть обработаны ранее)
            if text_lower in ['!актив', '!актив групп', '!сброситьактив']:
                return False
            # Все остальные команды с ! не отслеживаем
            return False

        # 3. Проверяем префиксы команд
        for prefix in self.ignored_prefixes:
            if text_lower.startswith(prefix):
                return False

        # 4. Проверяем короткие команды (первое слово)
        first_word = text_lower.split()[0] if text_lower.split() else text_lower
        if first_word in self.short_commands:
            return False

        # 5. Проверяем наличие команд без префиксов
        # Команды типа "бот стоп" (без префикса)
        if 'бот стоп' in text_lower or 'ботстоп' in text_lower:
            return False
        if 'бот ищи' in text_lower or 'бот очисти' in text_lower or 'бот статистика' in text_lower:
            return False
        if 'мои подарки' in text_lower or 'магазин подарков' in text_lower:
            return False

        # 6. Исключаем очень короткие сообщения
        if len(text_lower) < 3:
            return False

        # 7. Проверяем, не является ли сообщение ответом на опрос или что-то подобное
        if text_lower in ['да', 'нет', 'ок', 'хорошо', 'ладно', 'понял']:
            return False

        # Если все проверки пройдены - отслеживаем сообщение
        return True

    async def track_message(self, message: types.Message):
        """Отслеживание сообщений пользователей"""
        # Проверяем, нужно ли отслеживать это сообщение
        if not self.should_track_message(message):
            return

        user = message.from_user
        chat_id = message.chat.id

        db = SessionLocal()
        try:
            ChatActivityRepository.get_or_create(
                db=db,
                chat_id=chat_id,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
        except Exception as e:
            logger.error(f"Ошибка при отслеживании сообщения: {e}")
        finally:
            db.close()

    def _build_activity_page(self, db, chat_id: int, user_id: int, page: int) -> Tuple[str, InlineKeyboardMarkup | None]:
        """Собирает текст и клавиатуру для страницы рейтинга активности."""

        # Сколько всего пользователей с активностью в чате
        total_users = db.query(ChatActivity).filter(ChatActivity.chat_id == chat_id).count()
        if total_users <= 0:
            text = (
                "📊 <b>Статистика активности</b>\n\n"
                "Здесь пока нет данных.\n"
                "Начните общаться, чтобы заполнить таблицу!"
            )
            return text, None

        total_pages = max(1, int(math.ceil(total_users / ACTIVITY_PAGE_SIZE)))
        page = max(1, min(int(page), total_pages))
        offset = (page - 1) * ACTIVITY_PAGE_SIZE

        # Получаем нужную страницу топа (не меняем данные, только формат вывода)
        page_users = (
            db.query(ChatActivity)
            .filter(ChatActivity.chat_id == chat_id)
            .order_by(desc(ChatActivity.message_count))
            .offset(offset)
            .limit(ACTIVITY_PAGE_SIZE)
            .all()
        )

        # Получаем общее количество сообщений
        total_messages = ChatActivityRepository.get_total_messages(db, chat_id)

        # Получаем место текущего пользователя в рейтинге
        user_position = ChatActivityRepository.get_user_position(db, chat_id, user_id)

        # Получаем количество сообщений текущего пользователя
        user_message_count = ChatActivityRepository.get_user_message_count(db, chat_id, user_id)

        # Формируем список пользователей
        user_lines = []
        start_rank = offset + 1

        for idx, activity in enumerate(page_users, start_rank):
            if activity.first_name:
                display_name = activity.first_name
            elif activity.username:
                display_name = f"@{activity.username}"
            else:
                display_name = f"User{activity.user_id}"

            user_link = self.user_formatter.get_user_link_html(activity.user_id, display_name)
            user_lines.append(f"{idx}. {user_link} — {activity.message_count}")

        # Формируем строку с местом текущего пользователя
        if user_position:
            user_position_text = f"Ваша позиция: #{user_position} ({user_message_count} сообщ.)"
        elif user_message_count > 0:
            user_position_text = f"Ваше место: вне топа ({user_message_count} сообщ.)"
        else:
            user_position_text = "Вы пока не в рейтинге"

        page_text = f"Страница {page}/{total_pages}" if total_pages > 1 else ""

        header = "📊 <b>Топ активности</b>\n\n"
        body = chr(10).join(user_lines)
        page_line = f"\n\n{page_text}" if page_text else ""
        footer = f"\n\n{user_position_text}\nВсего сообщений: {total_messages:,}"

        activity_text = f"{header}{body}{page_line}{footer}"

        # Клавиатура пагинации
        markup = None
        if total_pages > 1:
            markup = InlineKeyboardMarkup(row_width=3)

            buttons = []
            if page > 1:
                buttons.append(
                    InlineKeyboardButton(
                        text="◀️",
                        callback_data=f"{ACTIVITY_CB_PREFIX}:{chat_id}:{page - 1}"
                    )
                )

            buttons.append(
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=f"{ACTIVITY_CB_PREFIX}:{chat_id}:{page}"
                )
            )

            if page < total_pages:
                buttons.append(
                    InlineKeyboardButton(
                        text="▶️",
                        callback_data=f"{ACTIVITY_CB_PREFIX}:{chat_id}:{page + 1}"
                    )
                )

            markup.row(*buttons)

        return activity_text, markup

    async def on_activity_page(self, callback_query: CallbackQuery):
        """Обработка перелистывания страниц активности."""
        try:
            if not callback_query.data:
                return

            parts = callback_query.data.split(':', 2)
            if len(parts) != 3 or parts[0] != ACTIVITY_CB_PREFIX:
                return

            chat_id = int(parts[1])
            page = int(parts[2])

            # Защита от кликов "не из того чата"
            if not callback_query.message or callback_query.message.chat.id != chat_id:
                await callback_query.answer()
                return

            db = SessionLocal()
            try:
                text, markup = self._build_activity_page(db, chat_id, callback_query.from_user.id, page)
            finally:
                db.close()

            await callback_query.message.edit_text(text, parse_mode=types.ParseMode.HTML, reply_markup=markup)
            await callback_query.answer()

        except Exception as e:
            logger.error(f"Ошибка пагинации активности: {e}")
            try:
                await callback_query.answer("❌ Ошибка")
            except Exception:
                pass

    async def show_activity(self, message: types.Message):
        """Показ активности чата"""
        chat_id = message.chat.id
        user_id = message.from_user.id

        db = SessionLocal()
        try:
            text, markup = self._build_activity_page(db, chat_id, user_id, page=1)
            await message.reply(text, parse_mode=types.ParseMode.HTML, reply_markup=markup)

        except Exception as e:
            logger.error(f"Ошибка при показе активности: {e}")
            await message.reply("❌ Ошибка загрузки статистики")
        finally:
            db.close()

    async def reset_activity(self, message: types.Message):
        """Сброс статистики активности (только для админов)"""
        # Проверяем права администратора
        chat_member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=message.from_user.id
        )

        if chat_member.status not in ['creator', 'administrator']:
            await message.reply("⛔ Только для администраторов!")
            return

        db = SessionLocal()
        try:
            ChatActivityRepository.reset_chat_activity(db, message.chat.id)
            await message.reply("✅ Статистика сброшена")
        except Exception as e:
            logger.error(f"Ошибка при сбросе статистики: {e}")
            await message.reply("❌ Ошибка сброса")
        finally:
            db.close()

    async def show_top_groups(self, message: types.Message):
        """Показать топ групп по активности с кликабельными названиями"""
        db = SessionLocal()
        try:
            # Получаем статистику по всем чатам
            from sqlalchemy import func

            chat_stats = db.query(
                ChatActivity.chat_id,
                func.sum(ChatActivity.message_count).label('total_messages')
            ).group_by(
                ChatActivity.chat_id
            ).order_by(
                func.sum(ChatActivity.message_count).desc()
            ).limit(20).all()

            if not chat_stats:
                response = (
                    "🏆 <b>Топ групп</b>\n\n"
                    "Нет данных.\n"
                    "Бот должен поработать в группах."
                )
                await message.reply(response, parse_mode=types.ParseMode.HTML)
                return

            # Формируем список групп с кликабельными ссылками
            group_lines = []

            # Пробуем получить информацию о чатах для создания ссылок
            for i, stat in enumerate(chat_stats, 1):
                chat_id = stat.chat_id
                messages = stat.total_messages

                try:
                    # Пробуем получить информацию о чате для создания ссылки
                    chat_info = await message.bot.get_chat(chat_id)
                    chat_name = chat_info.title or f"Безымянный чат"

                    # Обрезаем слишком длинные названия
                    if len(chat_name) > 30:
                        chat_name = chat_name[:27] + "..."

                    # Проверяем есть ли username у чата
                    if chat_info.username:
                        # Для публичных чатов - ссылка через @username
                        chat_link = f"https://t.me/{chat_info.username}"
                        group_line = f"{i}. <a href='{chat_link}'>{chat_name}</a> — {messages:,}"
                    else:
                        # Для приватных чатов - пытаемся создать invite link
                        try:
                            # Пробуем получить пригласительную ссылку
                            chat_invite = await chat_info.export_invite_link()
                            group_line = f"{i}. <a href='{chat_invite}'>{chat_name}</a> — {messages:,}"
                        except Exception:
                            # Если не можем получить ссылку, просто показываем название
                            group_line = f"{i}. {chat_name} — {messages:,}"

                except Exception as e:
                    logger.warning(f"Не удалось получить информацию о чате {chat_id}: {e}")
                    # Для чатов, которые не удалось получить, используем короткий ID
                    if chat_id < 0:
                        short_id = str(abs(chat_id))[-6:]
                        chat_name = f"Группа ...{short_id}"
                    else:
                        chat_name = f"Группа {chat_id}"

                    # Пытаемся создать возможную ссылку (если чат публичный и мы знаем username)
                    # Для этого нужны дополнительные данные, но пока просто название
                    group_line = f"{i}. {chat_name} — {messages:,}"

                group_lines.append(group_line)

            # Подсчитываем общую статистику
            total_groups = len(chat_stats)
            total_messages = sum(stat.total_messages for stat in chat_stats)

            # Формируем итоговое сообщение
            response = (
                "🏆 <b>Топ групп по активности</b>\n\n"
                f"{chr(10).join(group_lines)}\n\n"
                f"Всего групп: {total_groups}\n"
                f"Всего сообщений: {total_messages:,}"
            )

            await message.reply(response, parse_mode=types.ParseMode.HTML, disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Ошибка при показе топ групп: {e}")
            await message.reply("❌ Ошибка загрузки")
        finally:
            db.close()


def register_chat_activity_handlers(dp: Dispatcher):
    """Регистрация обработчиков активности чатов"""
    handler = ChatActivityHandler()

    # 1. Сначала регистрируем наши команды с высоким приоритетом
    dp.register_message_handler(
        handler.show_activity,
        lambda message: message.text and message.text.strip().lower() == '!актив',
        state='*'
    )

    dp.register_message_handler(
        handler.show_top_groups,
        lambda message: message.text and (message.text.strip().lower() == '!актив групп' or message.text.strip().lower() == '/find_chats'),
        state='*'
    )

    dp.register_message_handler(
        handler.reset_activity,
        lambda message: message.text and message.text.strip().lower() == '!сброситьактив',
        state='*'
    )

    # Пагинация для !актив (inline-кнопки)
    dp.register_callback_query_handler(
        handler.on_activity_page,
        lambda c: c.data and c.data.startswith(f"{ACTIVITY_CB_PREFIX}:"),
        state='*'
    )

    # 2. Затем регистрируем обработчик отслеживания сообщений с фильтрацией
    dp.register_message_handler(
        handler.track_message,
        lambda msg: handler.should_track_message(msg),  # Синхронный фильтр
        content_types=['text', 'photo', 'sticker', 'animation', 'document'],
        state='*'
    )

    logging.info("✅ Обработчики активности чатов зарегистрированы")