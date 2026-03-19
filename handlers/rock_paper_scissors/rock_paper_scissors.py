# handlers/rock_paper_scissors/rock_paper_scissors.py
import asyncio
import logging
import random
import re
from decimal import Decimal
from typing import Dict, Optional, Tuple

from aiogram import types, Dispatcher
from aiogram.dispatcher.handler import SkipHandler

from database import SessionLocal
from database.crud import UserRepository, TransactionRepository

logger = logging.getLogger(__name__)

# ==========================
# НАСТРОЙКИ
# ==========================

MIN_BET = 1000


CHOICES = {
    "камень": "🪨",
    "ножницы": "✂️",
    "бумага": "📄"
}

ANIMATION_EMOJI = {
    "камень": "✊",
    "бумага": "🖐",
    "ножницы": "✌️",
}

# что побеждает что (ключ побеждает значение)
WIN_RULES = {
    "камень": "ножницы",
    "ножницы": "бумага",
    "бумага": "камень"
}

# Счетчик игр для «1 победа из 10» (по пользователю)
_user_game_counter: Dict[int, int] = {}


# ==========================
# ВСПОМОГАТЕЛЬНЫЕ
# ==========================

_QUICK_CMD_RE = re.compile(r'^(камень|ножницы|бумага)\s+(\d+)\s*$', re.IGNORECASE)


def _parse_quick_command(text: str) -> Optional[Tuple[str, int]]:
    """
    Парсит команды вида:
      "камень 1000"
      "ножницы 2500"
      "бумага 10000"
    Возвращает (choice, bet) или None.
    """
    if not text:
        return None
    m = _QUICK_CMD_RE.match(text.strip())
    if not m:
        return None
    choice = m.group(1).lower()
    bet = int(m.group(2))
    return choice, bet


def _bot_choice_for_user(user_id: int, user_choice: str) -> str:
    """
    Бот выигрывает всегда, а игрок — 1 раз из 10 игр (ровно).
    Реализация: каждая 10-я игра пользователя — победа игрока.
    """
    count = _user_game_counter.get(user_id, 0) + 1
    _user_game_counter[user_id] = count

    # 10-я, 20-я, 30-я... игра — даем игроку победу
    if count % 10 == 0:
        # Чтобы игрок победил, бот выбирает то, что проигрывает выбору игрока
        return WIN_RULES[user_choice]

    # Иначе бот выбирает то, что побеждает выбор игрока
    for bot_choice, beats in WIN_RULES.items():
        if beats == user_choice:
            return bot_choice

    # Фолбэк (не должен случиться)
    return random.choice(list(CHOICES.keys()))


def _winner(user_choice: str, bot_choice: str) -> str:
    if user_choice == bot_choice:
        return "draw"
    if WIN_RULES[user_choice] == bot_choice:
        return "user"
    return "bot"


# ==========================
# ХЕНДЛЕРЫ
# ==========================

async def rps_rules(message: types.Message):
    rules = (
        "🎮 <b>Камень • Ножницы • Бумага</b>\n\n"
        "<b>Как играть:</b>\n"
        "Отправьте одну из команд:\n"
        "• <code>камень 1000</code>\n"
        "• <code>ножницы 1000</code>\n"
        "• <code>бумага 1000</code>\n\n"
        f"Минимальная ставка: <b>{MIN_BET}</b> монет.\n\n"
        "⚠️ По правилам этого бота: он обычно выигрывает 😈"
    )
    await message.answer(rules, parse_mode="HTML")


async def rps_quick_play(message: types.Message):
    parsed = _parse_quick_command(message.text or "")
    if not parsed:
        raise SkipHandler

    user_choice, bet_amount = parsed

    if bet_amount < MIN_BET:
        await message.reply(f"❌ Минимальная ставка: {MIN_BET}")
        return

    db = SessionLocal()
    try:
        user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.reply("❌ Пользователь не найден. Используйте /start")
            return

        if user.coins < Decimal(bet_amount):
            await message.reply(f"❌ Недостаточно монет. Баланс: {int(user.coins):,}")
            return

        # ✅ ВАЖНО: бот выбирает ОДИН РАЗ
        bot_choice = _bot_choice_for_user(message.from_user.id, user_choice)

        # 🔥 Мгновенно показываем ЖЕСТ БОТА
        await message.answer(ANIMATION_EMOJI[bot_choice])

        # ✅ Вычисляем результат по тому же выбору
        result = _winner(user_choice, bot_choice)

        if result == "user":
            user.coins += Decimal(bet_amount)
            user.win_games += 1
            user.win_coins += Decimal(bet_amount)

            TransactionRepository.create_transaction(
                db,
                from_user_id=None,
                to_user_id=message.from_user.id,
                amount=bet_amount,
                description=f"🎮 КНБ выигрыш (+{bet_amount})"
            )
            result_text = f"🎉 <b>Вы выиграли!</b>\n💰 +{bet_amount:,} монет"

        elif result == "bot":
            user.coins -= Decimal(bet_amount)
            user.lose_games += 1
            user.defeat_coins += Decimal(bet_amount)

            TransactionRepository.create_transaction(
                db,
                from_user_id=message.from_user.id,
                to_user_id=None,
                amount=bet_amount,
                description=f"🎮 КНБ проигрыш (-{bet_amount})"
            )
            result_text = f"😈 <b>Вы проиграли!</b>\n💸 -{bet_amount:,} монет"
        else:
            result_text = "🤝 <b>Ничья!</b>"

        UserRepository.update_max_bet(db, message.from_user.id, bet_amount)
        db.commit()

        await asyncio.sleep(0.4)

        await message.answer(
            "🎮 <b>Камень • Ножницы • Бумага</b>\n\n"
            f"Вы: {CHOICES[user_choice]} <b>{user_choice}</b>\n"
            f"Бот: {CHOICES[bot_choice]} <b>{bot_choice}</b>\n\n"
            f"{result_text}\n\n"
            f"💳 Баланс: <b>{int(user.coins):,}</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка в КНБ: {e}", exc_info=True)
        db.rollback()
        await message.reply("❌ Ошибка при игре в КНБ")
    finally:
        db.close()




# ==========================
# РЕГИСТРАЦИЯ
# ==========================

def register_rps_handlers(dp: Dispatcher):
    # Правила
    dp.register_message_handler(
        rps_rules,
        lambda m: m.text and m.text.lower().strip() in {"кнб", "кнб правила", "правила кнб"},
        state="*"
    )
    dp.register_message_handler(rps_rules, commands=["кнб"], state="*")

    # Быстрая игра: "камень 1000" / "ножницы 1000" / "бумага 1000"
    dp.register_message_handler(
        rps_quick_play,
        lambda m: m.text and _QUICK_CMD_RE.match(m.text.strip()),
        state="*"
    )

    logger.info("✅ RPS handlers registered")
