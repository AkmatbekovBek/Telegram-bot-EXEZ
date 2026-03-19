# admin_notifications.py

import logging
from pathlib import Path
from aiogram import types
from .admin_helpers import db_session, format_number
from database.crud import UserRepository

logger = logging.getLogger(__name__)


async def send_admin_action_notification(bot, user_id: int, action_type: str,
                                         amount: int = None, new_balance: int = None,
                                         privilege_info: dict = None):
    """Отправляет красивое уведомление о действии админа в ЛС пользователю"""
    try:
        # Сначала проверяем и создаем пользователя если нужно
        with db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                # Создаем пользователя если его нет
                try:
                    # Пытаемся получить информацию о пользователе через Telegram API
                    chat_member = await bot.get_chat(user_id)
                    username = chat_member.username
                    first_name = chat_member.first_name or "Пользователь"
                    user = UserRepository.create_user_safe(
                        db,
                        user_id,
                        first_name,
                        username
                    )
                    logger.info(f"✅ Создан новый пользователь {user_id} для доната")
                except Exception as user_info_error:
                    logger.warning(
                        f"Не удалось получить информацию о пользователе {user_id}: {user_info_error}")
                    # Создаем с базовыми данными
                    user = UserRepository.create_user_safe(
                        db,
                        user_id,
                        "Пользователь",
                        None
                    )
                db.commit()

        # Основной текст уведомления
        action_texts = {
            "donate": "🎉 Вам зачислен донат!",
            "add_coins": "💰 Вам начислены монеты!",
            "privilege": "🎁 Вам выдана привилегия!",
            "unlimit": "🔐 Вам сняли лимит переводов!",
            "coins_and_privilege": "🎊 Вам начислены монеты и привилегия!"
        }

        notification_text = f"<b>{action_texts.get(action_type, '🎁 Вам начислена награда!')}</b>\n"

        # Добавляем информацию о монетах если есть
        if amount is not None and new_balance is not None:
            notification_text += f"💝 <b>+{format_number(amount)} монет</b>\n"
            notification_text += f"💳 Теперь на вашем балансе: <b>{format_number(new_balance)} монет</b>\n"

        # Добавляем информацию о привилегии если есть
        if privilege_info:
            actual_days = privilege_info.get('actual_days', privilege_info.get('default_days', 30))
            duration = f"{actual_days} дней" if privilege_info.get('extendable') else "навсегда"
            notification_text += f"🎁 <b>Привилегия: {privilege_info['name']}</b>\n"
            notification_text += f"⏰ Срок: {duration}\n"

        notification_text += "✨ <i>Спасибо за вашу активность!</i>"

        # ИСПРАВЛЕННЫЙ ПОИСК ФОТО - ОТНОСИТЕЛЬНО ПРОЕКТА
        try:
            # Получаем корень проекта (где находится main.py)
            # Предполагаем, что структура: project/ handlers/ admin/ admin_notifications.py
            current_file = Path(__file__)  # Текущий файл
            project_root = current_file.parent.parent.parent  # Поднимаемся на 3 уровня вверх к корню

            logger.info(f"🔍 Корень проекта: {project_root}")

            # Проверяем разные возможные места для медиа ОТНОСИТЕЛЬНО корня проекта
            possible_media_paths = [
                project_root / "media" / "donate.jpg",
                project_root / "media" / "donate.png",
                project_root / "assets" / "donate.jpg",
                project_root / "assets" / "donate.png",
                project_root / "images" / "donate.jpg",
                project_root / "images" / "donate.png",
                project_root / "donate.jpg",
                project_root / "donate.png",
            ]

            photo_path = None

            # Ищем первый существующий файл
            for media_path in possible_media_paths:
                if media_path.exists():
                    photo_path = media_path
                    logger.info(f"✅ Найдено фото: {photo_path}")
                    break

            if photo_path:
                logger.info(f"📤 Отправляем фото: {photo_path}")
                with open(photo_path, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=notification_text,
                        parse_mode="HTML"
                    )
                logger.info(f"✅ Фото-уведомление отправлено пользователю {user_id}")
            else:
                # Логируем для отладки что доступно
                logger.warning("❌ Фото не найдено. Проверяем доступные файлы:")

                # Проверяем какие директории существуют
                check_dirs = ["media", "assets", "images"]
                for dir_name in check_dirs:
                    check_dir = project_root / dir_name
                    if check_dir.exists():
                        files = list(check_dir.glob("*.*"))
                        logger.warning(f"   📁 {dir_name}: {[f.name for f in files]}")
                    else:
                        logger.warning(f"   📁 {dir_name}: директория не существует")

                # Также проверяем файлы в корне
                root_files = list(project_root.glob("*.jpg")) + list(project_root.glob("*.png")) + list(
                    project_root.glob("*.jpeg"))

                # Отправляем текстовое сообщение
                logger.info("📝 Отправляем текстовое уведомление вместо фото")
                await bot.send_message(
                    chat_id=user_id,
                    text=notification_text,
                    parse_mode="HTML"
                )

        except Exception as photo_error:
            logger.warning(f"⚠️ Ошибка при отправке фото: {photo_error}, переключаемся на текст")
            await bot.send_message(
                chat_id=user_id,
                text=notification_text,
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления пользователю {user_id}: {e}")
        # Фолбэк на простой текст
        try:
            fallback_text = f"🎉 Вам начислена награда от администратора!"
            if amount is not None:
                fallback_text += f"\n💰 +{format_number(amount)} монет"
            if privilege_info:
                fallback_text += f"\n🎁 {privilege_info['name']}"
            await bot.send_message(
                chat_id=user_id,
                text=fallback_text
            )
        except Exception as fallback_error:
            logger.error(f"❌ Не удалось отправить даже фолбэк уведомление: {fallback_error}")