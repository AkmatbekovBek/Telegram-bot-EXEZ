# middlewares/auto_register_middleware.py
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from database import SessionLocal
from database.models import User, TelegramUser


class AutoRegisterMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: types.Message, data: dict):
        # Пропускаем служебные сообщения
        if not message.from_user:
            return

        # Пропускаем команды от ботов
        if message.from_user.is_bot:
            return

        # Определяем контекстный chat_id
        if message.chat.type in ('group', 'supergroup'):
            context_chat_id = message.chat.id
        else:
            context_chat_id = 0  # глобальный контекст для ЛС

        user_id = message.from_user.id
        username = message.from_user.username or ''
        first_name = message.from_user.first_name or ''

        db = SessionLocal()
        try:
            # 1. Сначала регистрируем в TelegramUser (глобальная таблица)
            telegram_user = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == user_id
            ).first()

            if not telegram_user:
                telegram_user = TelegramUser(
                    telegram_id=user_id,
                    username=username,
                    first_name=first_name,
                    coins=5000  # стартовый баланс
                )
                db.add(telegram_user)
                print(f"✅ Зарегистрирован новый TelegramUser: {user_id}")
            else:
                # Обновляем данные если изменились
                if telegram_user.username != username:
                    telegram_user.username = username
                if telegram_user.first_name != first_name:
                    telegram_user.first_name = first_name

            # 2. Регистрируем в User (таблица для чатов)
            user = db.query(User).filter(
                User.tg_id == user_id,
                User.chat_id == context_chat_id
            ).first()

            if not user:
                # Копируем данные из TelegramUser
                user = User(
                    tg_id=user_id,
                    chat_id=context_chat_id,
                    username=username,
                    coins=telegram_user.coins or 0,
                    win_coins=telegram_user.win_coins or 0,
                    defeat_coins=telegram_user.defeat_coins or 0,
                    max_win_coins=telegram_user.max_win_coins or 0,
                    min_win_coins=telegram_user.min_win_coins or 0,
                    max_bet_coins=telegram_user.max_bet or 0
                )
                db.add(user)
                print(f"✅ Зарегистрирован новый User в чате {context_chat_id}: {user_id}")
            else:
                # Обновляем данные из TelegramUser
                user.coins = telegram_user.coins or user.coins
                user.win_coins = telegram_user.win_coins or user.win_coins
                user.defeat_coins = telegram_user.defeat_coins or user.defeat_coins
                user.max_win_coins = telegram_user.max_win_coins or user.max_win_coins
                user.min_win_coins = telegram_user.min_win_coins or user.min_win_coins
                user.max_bet_coins = telegram_user.max_bet or user.max_bet_coins
                user.username = username or telegram_user.username or user.username

            db.commit()

        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка авторегистрации пользователя {user_id}: {e}")
        finally:
            db.close()