# handlers/roulette/admin_commands.py
import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

from .state_manager import state_manager
from .config import CONFIG

logger = logging.getLogger(__name__)


async def roulette_on_command(message: types.Message):
    """Включить рулетку в этом чате (!ron)"""

    # Проверяем права администратора
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await state_manager.check_admin_permissions(user_id, chat_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам группы или бота")
        return

    # Если рулетка уже включена в этом чате
    if state_manager.is_roulette_enabled(chat_id):
        await message.answer("ℹ️ Рулетка уже включена в этом чате")
        return

    # Включаем рулетку в этом чате
    state_manager.enable_roulette(chat_id)

    # Очищаем кэш для текущего пользователя
    state_manager.clear_cache(user_id, chat_id)

    chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"
    logger.info(f"Рулетка включена пользователем {user_id} в чате {chat_id} ({chat_name})")

    await message.answer(
        f"✅ <b>Рулетка включена в {chat_name}!</b>\n\n"
        "🎰 Теперь все команды рулетки доступны для использования.\n"
        "Участники могут делать ставки и играть в рулетку.",
        parse_mode="HTML"
    )


async def roulette_off_command(message: types.Message):
    """Отключить рулетку в этом чате (!roff)"""

    # Проверяем права администратора
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await state_manager.check_admin_permissions(user_id, chat_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам группы или бота")
        return

    # Если рулетка уже отключена в этом чате
    if not state_manager.is_roulette_enabled(chat_id):
        await message.answer("ℹ️ Рулетка уже отключена в этом чате")
        return

    # Отключаем рулетку в этом чате
    state_manager.disable_roulette(chat_id)

    # Очищаем кэш для текущего пользователя
    state_manager.clear_cache(user_id, chat_id)

    chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"
    logger.info(f"Рулетка отключена пользователем {user_id} в чате {chat_id} ({chat_name})")

    await message.answer(
        f"🚫 <b>Рулетка отключена в {chat_name}!</b>\n\n"
        "🎰 Все команды рулетки временно недоступны.\n"
        "Для включения используйте команду <code>!ron</code>.",
        parse_mode="HTML"
    )


async def roulette_status_command(message: types.Message):
    """Показать статус рулетки в этом чате (!rstatus)"""

    # Проверяем права администратора
    user_id = message.from_user.id
    chat_id = message.chat.id

    is_admin = await state_manager.check_admin_permissions(user_id, chat_id, message.bot)

    status = "🟢 <b>Включена и работает</b>" if state_manager.is_roulette_enabled(chat_id) else "🔴 <b>Отключена</b>"
    chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"

    response = (
        f"🎰 <b>Статус рулетки в {chat_name}</b>\n\n"
        f"Состояние: {status}\n"
        f"ID чата: <code>{chat_id}</code>\n"
    )

    if is_admin:
        response += (
            f"\n<b>Команды управления:</b>\n"
            f"• <code>!ron</code> - включить рулетку в этом чате\n"
            f"• <code>!roff</code> - отключить рулетку в этом чате\n"
            f"• <code>!rstatus</code> - показать статус"
        )
    else:
        response += f"\n<i>Только администраторы могут управлять рулеткой</i>"

    await message.answer(response, parse_mode="HTML")


def register_roulette_admin_commands(dp: Dispatcher):
    """Регистрирует команды управления рулеткой"""

    # Команды с восклицательным знаком
    dp.register_message_handler(
        roulette_on_command,
        lambda m: m.text and m.text.lower().strip() == '!ron'
    )

    dp.register_message_handler(
        roulette_off_command,
        lambda m: m.text and m.text.lower().strip() == '!roff'
    )

    dp.register_message_handler(
        roulette_status_command,
        lambda m: m.text and m.text.lower().strip() == '!rstatus'
    )

    # Альтернативные варианты команд
    dp.register_message_handler(
        roulette_on_command,
        lambda m: m.text and m.text.lower().strip() in ['/ron', 'ron', 'рулетка вкл']
    )

    dp.register_message_handler(
        roulette_off_command,
        lambda m: m.text and m.text.lower().strip() in ['/roff', 'roff', 'рулетка выкл']
    )

    dp.register_message_handler(
        roulette_status_command,
        lambda m: m.text and m.text.lower().strip() in ['/rstatus', 'rstatus', 'статус рулетки']
    )

    logger.info("✅ Команды управления рулеткой (по чатам) зарегистрированы")