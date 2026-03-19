# handlers/raffle/raffle.py

import logging
import random
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import types, Dispatcher, Bot
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.handler import SkipHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import SessionLocal
from database.crud import UserRepository, TransactionRepository
from database.models import Raffle, RaffleParticipant  # Import models

logger = logging.getLogger(__name__)

# ==========================
# НАСТРОЙКИ И КОНСТАНТЫ
# ==========================

MIN_RAFFLE_AMOUNT = 50000

# Обновленные настройки
MIN_PARTICIPANTS = 5
MAX_PARTICIPANTS = 150

WINNER_PERCENTAGE = 0.30  # 30% победителей
AUTO_START_DELAY = 3 * 3600  # 3 часа

# Активные розыгрыши
active_raffles: Dict[str, Dict] = {}


def load_active_raffles_from_db(bot: Bot):
    """Загружает активные розыгрыши из БД при старте"""
    db = SessionLocal()
    try:
        # Ищем розыгрыши в статусе waiting или active
        raffles_db = db.query(Raffle).filter(Raffle.status.in_(['waiting', 'active'])).all()
        
        count = 0
        for r in raffles_db:
            # Загружаем участников
            participants = []
            for p in r.participants:
                participants.append({
                    'user_id': p.user_id,
                    'username': p.username,
                    'tickets': p.tickets,
                    'joined_at': p.joined_at
                })
            
            active_raffles[r.id] = {
                'creator_id': r.creator_id,
                'creator_name': r.creator_name,
                'amount': r.amount,
                'participants': participants,
                'status': r.status,
                'chat_id': r.chat_id,
                'message_id': r.message_id,
                'created_at': r.created_at,
                'winners': [],
                'timer_task': None 
            }
            
            # Если розыгрыш в ожидании, перезапускаем таймер (с учетом прошедшего времени)
            if r.status == 'waiting':
                # Вычисляем сколько осталось времени
                elapsed = (datetime.now() - r.created_at).total_seconds()
                delay = max(0, AUTO_START_DELAY - elapsed)
                
                active_raffles[r.id]['timer_task'] = asyncio.create_task(
                    auto_start_raffle(bot, r.id, delay)
                )
            
            count += 1
            
        logger.info(f"✅ Загружено {count} активных розыгрышей из БД")
            
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки розыгрышей из БД: {e}")
    finally:
        db.close()



# ==========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================

def generate_raffle_id() -> str:
    """Генерирует уникальный ID розыгрыша"""
    return f"raffle_{datetime.now().timestamp()}_{random.randint(1000, 9999)}"


def calculate_winners(participants: List[Dict], total_amount: int) -> List[Dict]:
    if not participants:
        return []

    # 30% победителей, минимум 1
    winner_count = max(1, int(len(participants) * WINNER_PERCENTAGE))
    
    # Выбираем случайных победителей
    picked = random.sample(participants, winner_count)
    
    # Делим выигрыш поровну (split 100% of winnings)
    prize_per_winner = total_amount // winner_count
    remainder = total_amount % winner_count
    
    winners = []
    for i, user in enumerate(picked):
        prize = prize_per_winner
        if i == 0:
            prize += remainder  # Отдаем остаток первому
            
        winners.append({
            "user_id": user["user_id"],
            "username": user["username"],
            "prize": prize,
            "position": i + 1
        })
        
    return winners


def format_participants_list(participants: List[Dict], limit: int = 50) -> str:
    if not participants:
        return "👥 Участники пока отсутствуют"

    lines = []
    for i, participant in enumerate(participants[:limit], 1):
        username = participant['username'] or f"Участник {i}"
        tickets = participant.get('tickets', 1)
        lines.append(f"{i}. {username}: {tickets}🎫")

    if len(participants) > limit:
        lines.append(f"... и ещё {len(participants) - limit} участников")

    return "\n".join(lines)


def format_winners_list(winners: List[Dict]) -> str:
    lines = []
    for w in winners:
        username = w['username'] or f"Участник {w['position']}"
        lines.append(f"{w['position']}. {username} — {w['prize']:,} монет")
    return "\n".join(lines)


def create_raffle_keyboard(raffle_id: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="🎫 Участвовать", callback_data=f"join_raffle_{raffle_id}"),
        InlineKeyboardButton(text="👥 Участники", callback_data=f"view_participants_{raffle_id}")
    )
    keyboard.add(
        InlineKeyboardButton(text="🚦 Начать", callback_data=f"start_raffle_{raffle_id}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_raffle_{raffle_id}")
    )
    return keyboard


def create_winner_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="🎉 Поздравляем победителей!", callback_data="winner_congrats"))
    return keyboard


def _get_active_raffle_in_chat(chat_id: int) -> str | None:
    for rid, raffle in active_raffles.items():
        if raffle.get("chat_id") == chat_id and raffle.get("status") in ("waiting", "active"):
            return rid
    return None


def _is_creator(raffle: Dict, user_id: int) -> bool:
    return raffle.get("creator_id") == user_id


def _is_admin(db, user_id: int) -> bool:
    try:
        user = UserRepository.get_user_by_telegram_id(db, user_id)
        return bool(user and getattr(user, "is_admin", False))
    except Exception:
        return False


async def auto_start_raffle(bot: Bot, raffle_id: str, delay: int):
    """Задача автоматического старта через delay секунд"""
    try:
        await asyncio.sleep(delay)
        
        # Проверяем, существует ли еще розыгрыш и в статусе waiting
        raffle = active_raffles.get(raffle_id)
        if raffle and raffle.get("status") == "waiting":
            # Проверяем минимальное количество участников
            if len(raffle.get("participants", [])) >= MIN_PARTICIPANTS:
                # Отправляем уведомление
                try:
                    await bot.send_message(
                        chat_id=raffle['chat_id'],
                        text="⏰ <b>Время вышло! Автоматический запуск розыгрыша...</b>",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                
                # Запускаем
                raffle["status"] = "active"
                await finish_raffle(bot, raffle_id)
            else:
                # Отменяем из-за нехватки участников
                try:
                    await bot.send_message(
                        chat_id=raffle['chat_id'],
                        text=f"⏰ <b>Время вышло!</b>\n❌ Не набрано минимальное количество участников ({MIN_PARTICIPANTS}). Розыгрыш отменяется.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                await cancel_raffle_logic(bot, raffle_id, "Автоматическая отмена (нехватка участников)")
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in auto_start_raffle: {e}")


async def cancel_raffle_logic(bot: Bot, raffle_id: str, reason: str):
    """Общая логика отмены розыгрыша"""
    raffle = active_raffles.get(raffle_id)
    if not raffle:
        return

    raffle['status'] = 'cancelled'
    
    # Отменяем таймер если есть
    if 'timer_task' in raffle and raffle['timer_task']:
        raffle['timer_task'].cancel()

    cancellation_text = (
        f"❌ <b>РОЗЫГРЫШ ОТМЕНЁН</b> ❌\n\n"
        f"Создатель: {raffle['creator_name']}\n"
        f"Сумма: {raffle['amount']:,} монет\n"
        f"Участников: {len(raffle.get('participants', []))}\n\n"
        f"💬 {reason}"
    )

    try:
        await bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=cancellation_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение об отмене: {e}")

    # Возврат средств
    db = SessionLocal()
    try:
        # Обновляем статус в БД
        raffle_db = db.query(Raffle).filter(Raffle.id == raffle_id).first()
        if raffle_db:
            raffle_db.status = 'cancelled'

        creator = UserRepository.get_user_by_telegram_id(db, raffle["creator_id"])
        if creator:
            creator.coins += Decimal(raffle["amount"])
            TransactionRepository.create_transaction(
                db,
                from_user_id=None,
                to_user_id=raffle["creator_id"],
                amount=raffle["amount"],
                description="↩️ Возврат фонда (отмена розыгрыша)"
            )
            db.commit()
    finally:
        db.close()

    active_raffles.pop(raffle_id, None)


# ==========================
# ХЕНДЛЕРЫ
# ==========================

async def raffle_rules(message: types.Message):
    rules_text = (
        "🎉 <b>СИСТЕМА РОЗЫГРЫШЕЙ</b> 🎉\n\n"
        "<b>📋 Основные правила:</b>\n"
        f"• Минимальная сумма розыгрыша: {MIN_RAFFLE_AMOUNT:,} монет\n"
        f"• Участников нужно: от {MIN_PARTICIPANTS} до 150\n"
        f"• Победителей: 30% от числа участников\n"
        "• <b>Автостарт через 3 часа</b>\n\n"
        "<b>🏆 Распределение призов:</b>\n"
        "• Победители делят 100% призового фонда поровну\n\n"
        "<b>🎮 Команды:</b>\n"
        f"• розыгрыш {MIN_RAFFLE_AMOUNT} — создать розыгрыш\n"
        f"• раффл {MIN_RAFFLE_AMOUNT} — создать розыгрыш\n\n"
        "<b>🎫 Как участвовать:</b>\n"
        "1) Создатель пишет команду с суммой\n"
        "2) Участники жмут «Участвовать»\n"
        "3) Можно начать вручную (от 5 уч.) или ждать автостарта\n"
        "✨ Удачи! ✨"
    )
    await message.answer(rules_text, parse_mode="HTML")


async def raffle_start(message: types.Message, state: FSMContext):
    """Создать розыгрыш"""
    text = (message.text or "").lower().strip()

    if not (text.startswith('!розыгрыш ') or text.startswith('!раффл ')
            or text.startswith('розыгрыш ') or text.startswith('раффл ')):
        return

    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(f"❌ Используйте: розыгрыш <сумма>\nПример: розыгрыш {MIN_RAFFLE_AMOUNT:,}")
        return

    amount = int(parts[1])
    if amount < MIN_RAFFLE_AMOUNT:
        await message.answer(f"❌ Минимальная сумма розыгрыша: {MIN_RAFFLE_AMOUNT:,} монет")
        return

    # Проверяем, нет ли уже активного розыгрыша в чате
    existing = _get_active_raffle_in_chat(message.chat.id)
    if existing:
        await message.answer("❌ В этом чате уже есть активный розыгрыш!")
        return

    db = SessionLocal()
    try:
        user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден. Начните с команды /start")
            return

        if user.coins < amount:
            await message.answer(f"❌ Недостаточно монет для розыгрыша. Ваш баланс: {user.coins:,}")
            return

        # Списываем монеты
        user.coins -= Decimal(amount)
        TransactionRepository.create_transaction(
            db,
            from_user_id=message.from_user.id,
            to_user_id=None,
            amount=amount,
            description="🎟 Создание розыгрыша"
        )
        db.commit()
        db.refresh(user)

        raffle_id = generate_raffle_id()
        
        # Сохраняем в БД
        new_raffle = Raffle(
            id=raffle_id,
            chat_id=message.chat.id,
            creator_id=message.from_user.id,
            creator_name=message.from_user.username or message.from_user.first_name,
            amount=amount,
            status='waiting',
            created_at=datetime.now()
        )
        db.add(new_raffle)
        db.commit()

        active_raffles[raffle_id] = {
            'creator_id': message.from_user.id,
            'creator_name': message.from_user.username or message.from_user.first_name,
            'amount': amount,
            'participants': [],
            'status': 'waiting',  # ожидание набора участников
            'chat_id': message.chat.id,
            'message_id': None,
            'created_at': datetime.now(),
            'winners': [],
            'timer_task': None
        }

        # Сообщение о розыгрыше
        raffle_text = (
            f"🎉 <b>РОЗЫГРЫШ СОЗДАН!</b> 🎉\n\n"
            f"💎 <b>Создатель:</b> {active_raffles[raffle_id]['creator_name']}\n"
            f"💰 <b>Призовой фонд:</b> {amount:,} монет\n"
            f"👥 <b>Нужно участников:</b> {MIN_PARTICIPANTS}-{MAX_PARTICIPANTS}\n"
            f"🏆 <b>Победителей:</b> 30% (делят всё)\n\n"
            f"🎫 Нажмите «Участвовать» для вступления!\n"
            f"👥 Участников: 0\n\n"
            f"⏳ <b>Автостарт через 3 часа</b> (или вручную от 5 уч.)"
        )

        msg = await message.answer(
            raffle_text,
            parse_mode="HTML",
            reply_markup=create_raffle_keyboard(raffle_id)
        )
        active_raffles[raffle_id]['message_id'] = msg.message_id
        
        # Обновляем message_id в БД
        new_raffle.message_id = msg.message_id
        db.commit()
        
        # Запускаем таймер
        active_raffles[raffle_id]['timer_task'] = asyncio.create_task(
            auto_start_raffle(message.bot, raffle_id, AUTO_START_DELAY)
        )

    except Exception as e:
        logger.error(f"Ошибка при создании розыгрыша: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при создании розыгрыша")
    finally:
        db.close()


async def join_raffle_callback(callback_query: types.CallbackQuery, state: FSMContext):
    raffle_id = callback_query.data.replace("join_raffle_", "")

    raffle = active_raffles.get(raffle_id)
    if not raffle:
        await callback_query.answer("❌ Розыгрыш не найден или завершён", show_alert=True)
        return

    if raffle.get("status") != "waiting":
        await callback_query.answer("❌ Розыгрыш уже запущен/завершён", show_alert=True)
        return

    # Уже участвует?
    if any(p['user_id'] == callback_query.from_user.id for p in raffle['participants']):
        await callback_query.answer("❌ Вы уже участвуете!", show_alert=True)
        return

    # Лимит
    if len(raffle['participants']) >= MAX_PARTICIPANTS:
        await callback_query.answer(f"❌ Максимум {MAX_PARTICIPANTS} участников. Розыгрыш должен начаться.", show_alert=True)
        return

    db = SessionLocal()
    try:
        # Сохраняем участника в БД
        participant = RaffleParticipant(
            raffle_id=raffle_id,
            user_id=callback_query.from_user.id,
            username=callback_query.from_user.username or callback_query.from_user.first_name,
            tickets=1,
            joined_at=datetime.now()
        )
        db.add(participant)
        try:
            db.commit()
        except:
            db.rollback()
            # Возможно, уже участвует (если проверка сверху не сработала из-за гонки)
            await callback_query.answer("❌ Вы уже участвуете!", show_alert=True)
            return

        raffle['participants'].append({
            'user_id': callback_query.from_user.id,
            'username': callback_query.from_user.username or callback_query.from_user.first_name,
            'tickets': 1,
            'joined_at': datetime.now()
        })
    
        count = len(raffle['participants'])
        ready_text = ""
        if count >= MIN_PARTICIPANTS:
            ready_text = f"\n✅ <b>Минимум набран!</b> Можно начинать."
    except Exception as e:
        logger.error(f"Ошибка сохранения участника: {e}")
        await callback_query.answer("❌ Ошибка при вступлении")
        return
    finally:
        db.close()

    updated_text = (
        f"🎉 <b>РОЗЫГРЫШ!</b> 🎉\n\n"
        f"💎 <b>Создатель:</b> {raffle['creator_name']}\n"
        f"💰 <b>Призовой фонд:</b> {raffle['amount']:,} монет\n"
        f"👥 <b>Нужно участников:</b> {MIN_PARTICIPANTS}-{MAX_PARTICIPANTS}\n"
        f"🏆 <b>Победителей:</b> 30% (делят всё)\n\n"
        f"👥 Участников: {count}"
        f"{ready_text}\n\n"
        f"⏳ <b>Автостарт через 3 часа</b>"
    )

    try:
        await callback_query.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=updated_text,
            parse_mode="HTML",
            reply_markup=create_raffle_keyboard(raffle_id)
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение розыгрыша: {e}")

    await callback_query.answer(f"✅ Вы в розыгрыше! ({count} уч.)")


async def view_participants_callback(callback_query: types.CallbackQuery):
    raffle_id = callback_query.data.replace("view_participants_", "")
    raffle = active_raffles.get(raffle_id)
    if not raffle:
        await callback_query.answer("❌ Розыгрыш не найден", show_alert=True)
        return

    participants = raffle.get('participants', [])
    if not participants:
        await callback_query.answer("👥 Участников пока нет", show_alert=True)
        return

    participants_text = format_participants_list(participants, limit=50)
    response_text = (
        f"👥 <b>Участники розыгрыша:</b>\n"
        f"Всего: {len(participants)}\n\n"
        f"{participants_text}"
    )

    try:
        await callback_query.message.answer(response_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки списка участников: {e}")
    await callback_query.answer()


async def start_raffle_callback(callback_query: types.CallbackQuery):
    raffle_id = callback_query.data.replace("start_raffle_", "")
    raffle = active_raffles.get(raffle_id)
    if not raffle:
        await callback_query.answer("❌ Розыгрыш не найден", show_alert=True)
        return

    if raffle.get("status") != "waiting":
        await callback_query.answer("❌ Розыгрыш уже запущен/завершён", show_alert=True)
        return

    db = SessionLocal()
    try:
        is_creator = _is_creator(raffle, callback_query.from_user.id)
        is_admin = _is_admin(db, callback_query.from_user.id)

        if not (is_creator or is_admin):
            await callback_query.answer("❌ Начать может только создатель или администратор", show_alert=True)
            return

        if len(raffle.get("participants", [])) < MIN_PARTICIPANTS:
            await callback_query.answer(
                f"❌ Минимум {MIN_PARTICIPANTS} участников для старта. Сейчас: {len(raffle.get('participants', []))}",
                show_alert=True
            )
            return

        raffle["status"] = "active"
        await callback_query.answer("🚦 Запускаю розыгрыш...")

        await finish_raffle(callback_query.bot, raffle_id)

    except Exception as e:
        logger.error(f"Ошибка старта розыгрыша: {e}", exc_info=True)
        await callback_query.answer("❌ Ошибка старта", show_alert=True)
    finally:
        db.close()


async def cancel_raffle_callback(callback_query: types.CallbackQuery):
    raffle_id = callback_query.data.replace("cancel_raffle_", "")
    raffle = active_raffles.get(raffle_id)
    if not raffle:
        await callback_query.answer("❌ Розыгрыш не найден", show_alert=True)
        return

    if raffle.get("status") != "waiting":
        await callback_query.answer("❌ Нельзя отменить: розыгрыш уже запущен/завершён", show_alert=True)
        return

    db = SessionLocal()
    try:
        is_creator = _is_creator(raffle, callback_query.from_user.id)
        is_admin = _is_admin(db, callback_query.from_user.id)

        if not (is_creator or is_admin):
            await callback_query.answer("❌ Отменить может только создатель или администратор", show_alert=True)
            return

        await cancel_raffle_logic(callback_query.bot, raffle_id, "Отмена выполнена вручную.")
        await callback_query.answer("✅ Розыгрыш отменён")

    except Exception as e:
        logger.error(f"Ошибка отмены розыгрыша: {e}", exc_info=True)
        await callback_query.answer("❌ Ошибка отмены", show_alert=True)
    finally:
        db.close()


async def cancel_raffle_command(message: types.Message):
    """
    Текстовая команда отмены.
    """
    text = (message.text or "").lower().strip()
    if text not in {"отменить розыгрыш", "!отменить розыгрыш", "отмена розыгрыша"}:
        raise SkipHandler

    raffle_id = _get_active_raffle_in_chat(message.chat.id)
    if not raffle_id:
        raise SkipHandler

    raffle = active_raffles.get(raffle_id)
    if not raffle or raffle.get("status") != "waiting":
        raise SkipHandler

    db = SessionLocal()
    try:
        is_creator = _is_creator(raffle, message.from_user.id)
        is_admin = _is_admin(db, message.from_user.id)

        if not (is_creator or is_admin):
            await message.answer("❌ Отменить розыгрыш может только создатель или администратор")
            return

        await cancel_raffle_logic(message.bot, raffle_id, "Отмена выполнена командой.")
        await message.answer("✅ Розыгрыш отменён")

    finally:
        db.close()


async def finish_raffle(bot: Bot, raffle_id: str):
    """Завершить розыгрыш и определить победителей"""
    raffle = active_raffles.get(raffle_id)
    if not raffle:
        return
    
    # Отменяем таймер если есть
    if 'timer_task' in raffle and raffle['timer_task']:
        raffle['timer_task'].cancel()

    participants = raffle.get('participants', [])

    if len(participants) < MIN_PARTICIPANTS:
        # Недостаточно участников — отменяем
        await cancel_raffle_logic(bot, raffle_id, f"Недостаточно участников (Нужно: {MIN_PARTICIPANTS})")
        return

    raffle['winners'] = calculate_winners(participants, raffle['amount'])
    raffle['status'] = 'finished'

    # Начисляем призы
    db = SessionLocal()
    try:
        # Обновляем статус в БД
        raffle_db = db.query(Raffle).filter(Raffle.id == raffle_id).first()
        if raffle_db:
            raffle_db.status = 'finished'
            raffle_db.winners_count = len(raffle['winners'])

        for winner in raffle['winners']:
            user = UserRepository.get_user_by_telegram_id(db, winner['user_id'])
            if user:
                amount_dec = Decimal(winner["prize"])
                user.coins += amount_dec
                TransactionRepository.create_transaction(
                    db,
                    from_user_id=raffle["creator_id"],
                    to_user_id=winner['user_id'],
                    amount=winner['prize'],
                    description=f"🏆 Выигрыш в розыгрыше (место: {winner['position']})"
                )
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка при начислении призов: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

    winners_text = format_winners_list(raffle['winners'])
    result_text = (
        f"⚡ <b>Розыгрыш завершён!</b> ⚡\n\n"
        f"💰 <b>Фонд:</b> {raffle['amount']:,} монет\n"
        f"👥 <b>Участников:</b> {len(participants)}\n"
        f"🏆 <b>Победителей:</b> {len(raffle['winners'])} (30%)\n\n"
        f"<b>🏆 Получают по {raffle['winners'][0]['prize']:,} монет:</b>\n{winners_text}\n\n"
        f"👏 Поздравляем!"
    )

    try:
        await bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=result_text,
            parse_mode="HTML",
            reply_markup=create_winner_keyboard()
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить финальное сообщение: {e}")

    # Дополнительно: список участников (первые 100)
    participants_text = format_participants_list(participants, limit=100)
    try:
        await bot.send_message(
            chat_id=raffle['chat_id'],
            text=(
                f"📋 <b>Участники:</b>\n\n{participants_text}\n\n"
                f"<i>Всего: {len(participants)}</i>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить список участников: {e}")

    active_raffles.pop(raffle_id, None)


# ==========================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ==========================

def register_raffle_handlers(dp: Dispatcher):
    """Регистрация обработчиков розыгрышей"""

    dp.register_message_handler(
        raffle_rules,
        lambda m: m.text and m.text.lower().strip() in {"розыгрыш", "раффл", "розыгрыши", "раффлы"},
        state="*"
    )

    dp.register_message_handler(
        raffle_start,
        lambda m: m.text and (
            m.text.lower().startswith('!розыгрыш ') or
            m.text.lower().startswith('!раффл ') or
            m.text.lower().startswith('розыгрыш ') or
            m.text.lower().startswith('раффл ')
        ),
        state="*"
    )

    dp.register_callback_query_handler(
        join_raffle_callback,
        lambda c: c.data and c.data.startswith("join_raffle_"),
        state="*"
    )

    dp.register_callback_query_handler(
        view_participants_callback,
        lambda c: c.data and c.data.startswith("view_participants_"),
        state="*"
    )

    dp.register_callback_query_handler(
        start_raffle_callback,
        lambda c: c.data and c.data.startswith("start_raffle_"),
        state="*"
    )

    dp.register_callback_query_handler(
        cancel_raffle_callback,
        lambda c: c.data and c.data.startswith("cancel_raffle_"),
        state="*"
    )

    dp.register_message_handler(
        cancel_raffle_command,
        state="*"
    )

    logger.info("✅ Обработчики розыгрышей зарегистрированы")
