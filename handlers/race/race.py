# handlers/race/race.py
import re
import asyncio
import random
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from aiogram import types, Dispatcher, Bot
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.handler import SkipHandler
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import escape_md

from database import SessionLocal
from database.crud import UserRepository
from aiogram.utils.exceptions import RetryAfter, BadRequest

logger = logging.getLogger(__name__)

# ==========================
# НАСТРОЙКИ И КОНСТАНТЫ
# ==========================

MIN_BET = 1000
MAX_PLAYERS = 10
TRACK_LENGTH = 19
FINISH_LINE = "🏁"
START_LINE = "🚦"
CARS = ["🏎️", "🚗", "🚕", "🚙", "🚌", "🚓", "🚑", "🚒", "🚚", "🏍️"]
FPS_DELAY = 1.5  # увеличенная задержка для избежания flood control
RACE_DURATION = 6

active_races: Dict[str, Dict] = {}

# ВАЖНО: сохраняем dp, чтобы уметь чистить FSM-состояния в фоне (run_race/finish_race)
_dp_ref: Optional[Dispatcher] = None


# ==========================
# FSM
# ==========================

class RaceState(StatesGroup):
    waiting_for_players = State()
    race_in_progress = State()


# ==========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================

def generate_race_id() -> str:
    return f"race_{datetime.now().timestamp()}"


async def safe_edit_message(
        bot: Bot,
        chat_id: int,
        message_id: Optional[int],
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        disable_web_page_preview: bool = True
) -> bool:
    """
    Безопасное редактирование сообщения с обработкой ошибок
    """
    if not message_id:
        logger.error("Попытка редактировать сообщение без message_id")
        return False

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview
        )
        return True
    except RetryAfter as e:
        logger.warning(f"Flood control. Sleeping for {e.timeout} seconds")
        await asyncio.sleep(e.timeout)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview
            )
            return True
        except Exception as e2:
            logger.error(f"Ошибка при повторном редактировании: {e2}")
            return False
    except BadRequest as e:
        if "message to edit not found" in str(e) or "message identifier is not specified" in str(e):
            logger.error(f"Сообщение не найдено: {e}")
        else:
            logger.error(f"BadRequest при редактировании: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        return False


def _sanitize_name(name: str) -> str:
    """Очистка имени от невидимых символов (как в transfer.py)"""
    if not name:
        return "Аноним"

    cleaned = ''.join(c for c in name.strip()
                      if ord(c) >= 32 and c not in ['\u200B', '\u0000', '\x00'])[:100]
    return cleaned or "Аноним"

def _norm_cmd(s: str) -> str:
    if not s:
        return ""
    s = s.lower()

    # NBSP и невидимые символы
    s = (s.replace("\u00a0", " ")
           .replace("\u200b", "")
           .replace("\ufeff", "")
           .replace("\u2060", "")
           .replace("\u200c", "")
           .replace("\u200d", ""))

    # любые пробелы/переносы -> один пробел
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _get_user_display_name(user) -> str:
    """Точная копия метода из transfer.py (user из БД)"""
    if not user:
        return "Аноним"

    if getattr(user, "nickname", None):
        nn = _sanitize_name(str(getattr(user, "nickname")))
        if nn != "Аноним":
            return nn

    if getattr(user, "first_name", None):
        sanitized_name = _sanitize_name(str(getattr(user, "first_name")))
        if sanitized_name != "Аноним":
            return sanitized_name

    if getattr(user, "username", None):
        return f"@{getattr(user, 'username')}"

    return "Аноним"


async def _finish_users_states(chat_id: int, user_ids: List[int]):
    """
    Ключевая функция: снимает FSM-состояние у пользователей.
    Это лечит баг "создатель гонки после окончания не может писать команды".
    """
    global _dp_ref
    if not _dp_ref:
        return

    unique_ids = list({int(uid) for uid in user_ids if uid})
    if not unique_ids:
        return

    async def _finish_one(uid: int):
        try:
            st = _dp_ref.current_state(chat=chat_id, user=uid)
            await st.finish()
        except Exception:
            pass

    await asyncio.gather(*[_finish_one(uid) for uid in unique_ids], return_exceptions=True)


def render_track(players: List[Dict], finished_positions: Dict[int, int] = None) -> str:
    """
    Рендерит трек.
    Движение: ФИНИШ 🏁 ... [путь] ... 🚦 СТАРТ
    Теперь машины едут справа налево!
    """
    lines = []

    if finished_positions:
        sorted_players = sorted(players, key=lambda x: finished_positions.get(x['user_id'], 99))

        for player in sorted_players:
            nickname = player["nickname"][:12]
            car = player["car"]
            position = finished_positions.get(player['user_id'], 99)

            if position == 1:
                right_track = "─" * (TRACK_LENGTH - 1)
                line = f"{FINISH_LINE}{car}{right_track}{START_LINE} {nickname} 🏆"
            else:
                distance_from_finish = min(TRACK_LENGTH - 1, (position + 1) * 2)
                right_track = "─" * (TRACK_LENGTH - distance_from_finish - 1)
                car_position = "─" * (distance_from_finish - 1)
                line = f"{FINISH_LINE}{car_position}{car}{right_track}{START_LINE} {nickname}"
            lines.append(line)
    else:
        for player in players:
            nickname = player["nickname"][:12]
            car = player["car"]
            line = f"{FINISH_LINE}{'─' * (TRACK_LENGTH - 1)}{car}{START_LINE} {nickname}"
            lines.append(line)

    return "\n".join(lines)


def render_race_track(players: List[Dict], winner_finished: bool = False) -> str:
    """Рендерит трек во время гонки с текущими позициями (движение справа налево)"""
    lines = []
    for player in players:
        nickname = player["nickname"][:12]
        car = player["car"]

        position_int = int(min(player["position"], TRACK_LENGTH))

        left_track = "─" * (TRACK_LENGTH - position_int)
        right_track = "─" * max(0, position_int - 1)

        if player['finished']:
            if player.get('winner', False):
                line = f"{FINISH_LINE}{car}{'─' * (TRACK_LENGTH - 1)}{START_LINE} {nickname} 🏆"
            else:
                line = f"{FINISH_LINE}{'─' * (TRACK_LENGTH - position_int)}{car}{'─' * max(0, position_int - 1)}{START_LINE} {nickname}"
        else:
            line = f"{FINISH_LINE}{left_track}{car}{right_track}{START_LINE} {nickname}"

        lines.append(line)

    return "\n".join(lines)


def calculate_winnings(total_pool: int, player_count: int) -> Dict[int, int]:
    """Расчет выигрыша: весь пул получает победитель"""
    distribution = {}
    if player_count == 1:
        distribution[0] = total_pool
    elif player_count == 2:
        distribution[0] = total_pool
        distribution[1] = 0
    elif player_count >= 3:
        distribution[0] = total_pool
        distribution[1] = 0
        distribution[2] = 0
    return distribution


def create_race_keyboard(race_id: str, creator_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="🏎️ Присоединиться", callback_data=f"join_race_{race_id}"),
        InlineKeyboardButton(text="🚦 Старт", callback_data=f"start_race_{race_id}")
    )
    keyboard.add(
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_race_{race_id}")
    )
    return keyboard


def _find_waiting_race_in_chat(chat_id: int) -> Optional[str]:
    for rid, r in active_races.items():
        if r.get("chat_id") == chat_id and r.get("status") == "waiting":
            return rid
    return None


# ==========================
# ХЕНДЛЕРЫ
# ==========================

async def race_rules(message: types.Message):
    await message.answer(
        "🏎️ <b>Гонки</b> 🏁\n\n"
        "До 10 игроков могут участвовать!\n"
        "Ставки делаются перед началом.\n\n"
        "<b>Правила:</b>\n"
        "1. Каждый игрок делает одинаковую ставку\n"
        "2. Весь банк получает победитель\n"
        "3. Проигравшие теряют ставку\n\n"
        "Команды без /:\n"
        "• гонка &lt;ставка&gt; — открыть новую гонку\n"
        "• старт — начать гонку (может любой участник)\n"
        "• отмена гонки — отменить гонку (создатель)\n"
        f"Минимальная ставка: {MIN_BET} монет",
        parse_mode="HTML"
    )


async def race_start(message: types.Message, state: FSMContext):
    text = (message.text or "").lower().strip()
    if not text.startswith("гонка"):
        raise SkipHandler

    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("❌ Используйте: гонка &lt;ставка&gt;\nПример: гонка 1000", parse_mode=types.ParseMode.HTML)
        return

    bet_amount = int(parts[1])
    if bet_amount < MIN_BET:
        await message.answer(f"❌ Минимальная ставка {MIN_BET}")
        return

    db = SessionLocal()
    try:
        user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден. Начните с команды /start")
            return
        if user.coins < bet_amount:
            await message.answer(f"❌ Недостаточно монет. Ваш баланс: {user.coins}")
            return

        # уже есть ожидание гонки
        if _find_waiting_race_in_chat(message.chat.id):
            await message.answer("❌ В этом чате уже открыта гонка!")
            return

        race_id = generate_race_id()
        car_emoji = random.choice(CARS)

        nickname_display = _get_user_display_name(user)

        active_races[race_id] = {
            'creator_id': message.from_user.id,
            'bet_amount': bet_amount,
            'players': [{
                'user_id': message.from_user.id,
                'nickname': nickname_display,
                'bet': bet_amount,
                'car': car_emoji,
                'position': 0.0,
                'finished': False,
                'winner': False,
                'finish_time': None,
                'coins_before': user.coins
            }],
            'status': 'waiting',
            'chat_id': message.chat.id,
            'message_id': None,
            'start_time': None,
            'total_pool': bet_amount,
            'race_ended': False,
            'winner_id': None
        }

        await state.update_data(race_id=race_id, bet=bet_amount)
        await RaceState.waiting_for_players.set()

        track_display = render_track(active_races[race_id]['players'])
        keyboard = create_race_keyboard(race_id, message.from_user.id)

        msg = await message.answer(
            f"🏎️ <b>Создана гонка!</b>\n"
            f"💵 Ставка: {bet_amount}\n"
            f"💰 Банк: {bet_amount}\n"
            f"👥 Игроков: 1/{MAX_PLAYERS}\n"
            f"👑 Создатель: {nickname_display}\n\n"
            f"{track_display}\n\n"
            f"Нажмите 'Присоединиться' для участия\n"
            f"Чтобы начать: кнопка «Старт» или команда «старт» (любым участником)\n"
            f"Чтобы отменить: команда «cancel race» (создатель)",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        active_races[race_id]['message_id'] = msg.message_id

    finally:
        db.close()


async def join_race_callback(callback_query: types.CallbackQuery, state: FSMContext):
    race_id = callback_query.data.replace("join_race_", "")

    if race_id not in active_races:
        await callback_query.answer("❌ Гонка не найдена или уже началась")
        return

    race = active_races[race_id]

    if race["status"] != "waiting":
        await callback_query.answer("❌ Гонка уже началась!")
        return

    for p in race["players"]:
        if p["user_id"] == callback_query.from_user.id:
            await callback_query.answer("❌ Вы уже участвуете!")
            return

    if len(race["players"]) >= MAX_PLAYERS:
        await callback_query.answer(f"❌ Максимум {MAX_PLAYERS} игроков")
        return

    db = SessionLocal()
    try:
        user = UserRepository.get_user_by_telegram_id(db, callback_query.from_user.id)
        if not user or user.coins < race["bet_amount"]:
            await callback_query.answer("❌ Недостаточно монет")
            return

        used_cars = [p['car'] for p in race['players']]
        available_cars = [c for c in CARS if c not in used_cars]
        car_emoji = random.choice(available_cars) if available_cars else random.choice(CARS)

        nickname_display = _get_user_display_name(user)

        race['players'].append({
            'user_id': callback_query.from_user.id,
            'nickname': nickname_display,
            'bet': race['bet_amount'],
            'car': car_emoji,
            'position': 0.0,
            'finished': False,
            'winner': False,
            'finish_time': None,
            'coins_before': user.coins
        })

        race['total_pool'] = sum(p['bet'] for p in race['players'])

        track_display = render_track(race['players'])
        keyboard = create_race_keyboard(race_id, race['creator_id'])

        creator_name = next(p['nickname'] for p in race['players'] if p['user_id'] == race['creator_id'])

        success = await safe_edit_message(
            bot=callback_query.bot,
            chat_id=race['chat_id'],
            message_id=race['message_id'],
            text=f"🏎️ <b>Гонка!</b>\n"
                 f"💵 Ставка: {race['bet_amount']}\n"
                 f"💰 Банк: {race['total_pool']}\n"
                 f"👥 Игроков: {len(race['players'])}/{MAX_PLAYERS}\n"
                 f"👑 Создатель: {creator_name}\n\n"
                 f"{track_display}",
            reply_markup=keyboard
        )

        if not success:
            try:
                msg = await callback_query.bot.send_message(
                    chat_id=race['chat_id'],
                    text=f"🏎️ <b>Гонка!</b>\n"
                         f"💵 Ставка: {race['bet_amount']}\n"
                         f"💰 Банк: {race['total_pool']}\n"
                         f"👥 Игроков: {len(race['players'])}/{MAX_PLAYERS}\n"
                         f"👑 Создатель: {creator_name}\n\n"
                         f"{track_display}",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                race['message_id'] = msg.message_id
            except Exception as e:
                logger.error(f"Ошибка отправки нового сообщения: {e}")

        await callback_query.answer(f"✅ Вы присоединились! Машинка: {car_emoji}")

    finally:
        db.close()


async def start_race_callback(callback_query: types.CallbackQuery, state: FSMContext):
    race_id = callback_query.data.replace("start_race_", "")

    if race_id not in active_races:
        await callback_query.answer("❌ Гонка не найдена")
        return

    race = active_races[race_id]

    starter_id = callback_query.from_user.id

    if starter_id not in [p['user_id'] for p in race.get('players', [])]:
        await callback_query.answer("❌ Стартовать может только участник гонки!")
        return

    if len(race['players']) < 2:
        await callback_query.answer("❌ Нужно минимум 2 игрока!")
        return

    db = SessionLocal()
    try:
        for player in race['players']:
            user = UserRepository.get_user_by_telegram_id(db, player['user_id'])
            if user:
                user.coins -= Decimal(player['bet'])
                player['coins_before'] = user.coins + Decimal(player['bet'])
        db.commit()
        await callback_query.answer("🏎️ Ставки списаны, гонка начинается!")
    except Exception as e:
        logger.error(f"Ошибка при списании ставок: {e}")
        db.rollback()
        await callback_query.answer("❌ Ошибка при старте гонки")
        return
    finally:
        db.close()

    # КРИТИЧНО: снимаем FSM-состояния у ВСЕХ участников (особенно у создателя)
    await _finish_users_states(race['chat_id'], [p['user_id'] for p in race.get('players', [])])
    try:
        await state.finish()
    except Exception:
        pass

    race["status"] = "racing"
    race["start_time"] = datetime.now()

    try:
        await callback_query.bot.edit_message_reply_markup(
            chat_id=race['chat_id'],
            message_id=race['message_id'],
            reply_markup=None
        )
    except Exception:
        pass

    asyncio.create_task(run_race(callback_query.bot, race_id))


async def start_race_command(message: types.Message, state: FSMContext):
    text = (message.text or "").lower().strip()
    if text != "старт":
        raise SkipHandler

    race_id = _find_waiting_race_in_chat(message.chat.id)
    if not race_id:
        raise SkipHandler

    race = active_races[race_id]
    starter_id = message.from_user.id

    if starter_id not in [p['user_id'] for p in race.get('players', [])]:
        await message.answer("❌ Стартовать может только участник гонки!")
        return

    if len(race.get('players', [])) < 2:
        await message.answer("❌ Нужно минимум 2 игрока!")
        return

    db = SessionLocal()
    try:
        for player in race['players']:
            user = UserRepository.get_user_by_telegram_id(db, player['user_id'])
            if user:
                user.coins -= Decimal(player['bet'])
                player['coins_before'] = user.coins + Decimal(player['bet'])
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка при списании ставок (старт командой): {e}")
        db.rollback()
        await message.answer("❌ Ошибка при старте гонки")
        return
    finally:
        db.close()

    # КРИТИЧНО: снимаем FSM-состояния у ВСЕХ участников
    await _finish_users_states(race['chat_id'], [p['user_id'] for p in race.get('players', [])])
    try:
        await state.finish()
    except Exception:
        pass

    race["status"] = "racing"
    race["start_time"] = datetime.now()

    try:
        await message.bot.edit_message_reply_markup(
            chat_id=race['chat_id'],
            message_id=race['message_id'],
            reply_markup=None
        )
    except Exception:
        pass

    await message.answer("🏎️ Гонка началась!")
    asyncio.create_task(run_race(message.bot, race_id))


async def cancel_race_command(message: types.Message, state: FSMContext):
    cmd = _norm_cmd(message.text)
    logger.info("CANCEL_RACE raw=%r norm=%r", message.text, _norm_cmd(message.text))

    # поддержка /cancel_race и /cancel_race@BotName
    if cmd.startswith("/cancel_race"):
        cmd = "cancel_race"

    # допускаем "отмена гонки" даже с лишними пробелами (после нормализации они уже схлопнуты)
    if cmd not in {"отмена гонки", "!отмена гонки", "cancel race", "cancel_race"}:
        raise SkipHandler


    race_id = _find_waiting_race_in_chat(message.chat.id)
    if not race_id:
        await message.answer("❌ В этом чате нет гонки для отмены")
        return

    race = active_races[race_id]
    if race.get("creator_id") != message.from_user.id:
        await message.answer("❌ Отменить гонку может только создатель")
        return

    try:
        await message.bot.delete_message(chat_id=race['chat_id'], message_id=race['message_id'])
    except Exception:
        pass

    await _finish_users_states(race['chat_id'], [p['user_id'] for p in race.get('players', [])])

    try:
        await state.finish()
    except Exception:
        pass

    active_races.pop(race_id, None)
    await message.answer("✅ Гонка отменена")


async def run_race(bot: Bot, race_id: str):
    if race_id not in active_races:
        return

    race = active_races[race_id]

    if not race.get('message_id'):
        logger.error(f"Message ID не установлен для гонки {race_id}")
        try:
            track_display = render_track(race['players'])
            msg = await bot.send_message(
                chat_id=race["chat_id"],
                text=f"🏎️ <b>Гонка начинается!</b>\n🚦 СТАРТ!\n\n{track_display}",
                parse_mode="HTML"
            )
            race['message_id'] = msg.message_id
        except Exception as e:
            logger.error(f"Не удалось создать сообщение гонки: {e}")
            return

    track_display = render_track(race['players'])

    success = await safe_edit_message(
        bot=bot,
        chat_id=race["chat_id"],
        message_id=race["message_id"],
        text=f"🏎️ <b>Гонка начинается!</b>\n🚦 СТАРТ!\n\n{track_display}"
    )

    if not success:
        logger.error("Не удалось обновить сообщение гонки при старте")
        return

    await asyncio.sleep(0.5)

    winner_finished = False

    players_count = len(race['players'])
    winner_index = random.randint(0, players_count - 1)
    if random.random() < 0.3:
        winner_index = 0

    race['winner_id'] = race['players'][winner_index]['user_id']

    num_updates = int(RACE_DURATION / FPS_DELAY)

    for i, player in enumerate(race['players']):
        if player['user_id'] == race['winner_id']:
            player['base_speed'] = 3.5
            player['speed_variation'] = 0.5
        else:
            player['base_speed'] = random.uniform(1.5, 2.5)
            player['speed_variation'] = random.uniform(0.7, 1.2)

    race_in_progress = True
    update_count = 0

    while race_in_progress and update_count < num_updates:
        # Если гонку удалили/отменили
        if race_id not in active_races:
            return

        update_count += 1

        finished_players = [p for p in race['players'] if p['finished']]

        if winner_finished and len(finished_players) > 0:
            race_in_progress = False
            break

        for i, player in enumerate(race['players']):
            if not player['finished']:
                progress = update_count / num_updates

                if player['user_id'] == race['winner_id']:
                    speed_multiplier = 1.0 + progress * 2.0
                    speed = random.uniform(2.0, 4.0) * speed_multiplier

                    if not winner_finished and update_count > num_updates * 0.6:
                        speed *= 1.5

                    if player['position'] >= TRACK_LENGTH - 2 and not winner_finished:
                        speed *= 2.0
                else:
                    speed_multiplier = 0.8 + progress * 1.2
                    speed = random.uniform(1.0, 2.5) * speed_multiplier

                    if winner_finished:
                        speed *= 0.3

                player['position'] += speed * FPS_DELAY

                if player['position'] >= TRACK_LENGTH and not player['finished']:
                    player['position'] = TRACK_LENGTH
                    player['finished'] = True
                    player['finish_time'] = datetime.now()

                    if player['user_id'] == race['winner_id']:
                        player['winner'] = True
                        winner_finished = True

        if update_count % 2 == 0:
            track_display = render_race_track(race['players'], winner_finished)
            status_text = "🏎️ <b>Гонка в процессе!</b>"

            if winner_finished:
                for player in race['players']:
                    if player.get('winner', False):
                        status_text = f"🏎️ <b>Гонка завершается!</b>\n🏆 {player['nickname']} первым у финиша!"
                        break

            await safe_edit_message(
                bot=bot,
                chat_id=race["chat_id"],
                message_id=race["message_id"],
                text=f"{status_text}\n\n{track_display}"
            )

        await asyncio.sleep(FPS_DELAY)

    if not winner_finished:
        for player in race['players']:
            if player['user_id'] == race['winner_id'] and not player['finished']:
                player['position'] = TRACK_LENGTH
                player['finished'] = True
                player['winner'] = True
                player['finish_time'] = datetime.now()
                winner_finished = True
                break

    await finish_race(bot, race_id)


async def finish_race(bot: Bot, race_id: str):
    if race_id not in active_races:
        return

    race = active_races[race_id]

    finished_players = [p for p in race['players'] if p['finished']]

    winner = None
    other_players = []

    for player in race['players']:
        if player.get('winner', False):
            winner = player
        elif player['finished']:
            other_players.append(player)

    other_players.sort(key=lambda x: x['position'], reverse=True)

    all_players = [winner] if winner else []
    all_players.extend(other_players)

    finished_positions = {}
    for i, player in enumerate(all_players):
        if player:
            finished_positions[player['user_id']] = i + 1

    total_pool = race['total_pool']
    distribution = calculate_winnings(total_pool, len(all_players))

    db = SessionLocal()
    results_text = "🏁 <b>Гонка завершена!</b>\n\n<b>Результаты:</b>\n"

    try:
        for i, player in enumerate(all_players):
            if not player:
                continue

            winnings = distribution.get(i, 0)
            user = UserRepository.get_user_by_telegram_id(db, player['user_id'])
            if user:
                if winnings > 0 and player.get('winner', False):
                    user.coins += Decimal(total_pool)
                    user.win_coins += Decimal(total_pool)
                    net_winnings = total_pool - player['bet']
                    results_text += f"🏆 {player['nickname']} {player['car']} - +{net_winnings} монет (ПОБЕДИТЕЛЬ!)\n"
                else:
                    results_text += f"{i + 1}. {player['nickname']} {player['car']} - -{player['bet']} монет\n"

        db.commit()
        results_text += f"\n💰 <b>Общий банк:</b> {total_pool} монет"

    except Exception as e:
        logger.error(f"Ошибка при начислении выигрыша: {e}")
        db.rollback()
        results_text += "\n❌ Ошибка при обработке результатов"
    finally:
        db.close()

    final_track = render_track(race['players'], finished_positions)

    await safe_edit_message(
        bot=bot,
        chat_id=race["chat_id"],
        message_id=race["message_id"],
        text=f"🏁 <b>Гонка завершена!</b>\n\n{final_track}"
    )

    try:
        await bot.send_message(
            chat_id=race["chat_id"],
            text=results_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки результатов: {e}")

    # КРИТИЧНО: снимаем FSM-состояния у всех участников после завершения
    await _finish_users_states(race["chat_id"], [p['user_id'] for p in race.get('players', [])])

    active_races.pop(race_id, None)


async def cancel_race_callback(callback_query: types.CallbackQuery, state: FSMContext):
    race_id = callback_query.data.replace("cancel_race_", "")

    if race_id not in active_races:
        await callback_query.answer("❌ Гонка не найдена")
        return

    race = active_races[race_id]

    if race["creator_id"] != callback_query.from_user.id:
        await callback_query.answer("❌ Только создатель может отменить гонку!")
        return

    if race["status"] != "waiting":
        await callback_query.answer("❌ Гонка уже началась, нельзя отменить!")
        return

    try:
        await callback_query.bot.delete_message(
            chat_id=race['chat_id'],
            message_id=race['message_id']
        )
    except Exception:
        pass

    # чистим FSM всем
    await _finish_users_states(race['chat_id'], [p['user_id'] for p in race.get('players', [])])

    try:
        await state.finish()
    except Exception:
        pass

    active_races.pop(race_id, None)
    await callback_query.answer("✅ Гонка отменена")


async def cancel_race_message(message: types.Message, state: FSMContext):
    """
    Оставляем старые короткие команды, но добавляем "отмена гонки" как отдельную (выше).
    """
    text = (message.text or "").lower().strip()
    if text not in {"отмена", "cancel"}:
        raise SkipHandler

    found_race = None
    for rid, race in active_races.items():
        if race["creator_id"] == message.from_user.id and race["chat_id"] == message.chat.id and race["status"] == "waiting":
            found_race = rid
            break

    if not found_race:
        await message.answer("❌ Нет активной гонки для отмены")
        return

    race = active_races[found_race]

    try:
        await message.bot.delete_message(chat_id=race['chat_id'], message_id=race['message_id'])
    except Exception:
        pass

    await _finish_users_states(race['chat_id'], [p['user_id'] for p in race.get('players', [])])

    try:
        await state.finish()
    except Exception:
        pass

    active_races.pop(found_race, None)
    await message.answer("✅ Гонка отменена")


# ==========================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ==========================

def register_race_handlers(dp: Dispatcher):
    global _dp_ref
    _dp_ref = dp

    dp.register_message_handler(
        race_rules,
        lambda m: m.text and m.text.lower() in ["гонка", "правила", "race_help"],
        state="*"
    )

    # ВАЖНО: было state=None — из-за этого создатель (зависший в FSM) не мог создать новую гонку
    dp.register_message_handler(
        race_start,
        lambda m: m.text and m.text.lower().startswith("гонка"),
        state="*"
    )

    dp.register_message_handler(
        start_race_command,
        lambda m: m.text and m.text.lower().strip() == "старт",
        state="*"
    )

    # Новая команда: "отмена гонки"
    dp.register_message_handler(
        cancel_race_command,
        lambda m: m.text and (
                _norm_cmd(m.text) in {"отмена гонки", "!отмена гонки", "cancel race", "cancel_race"}
                or _norm_cmd(m.text).startswith("/cancel_race")
        ),
        state="*"
    )

    dp.register_callback_query_handler(
        join_race_callback,
        lambda c: c.data and c.data.startswith("join_race_"),
        state="*"
    )
    dp.register_callback_query_handler(
        start_race_callback,
        lambda c: c.data and c.data.startswith("start_race_"),
        state="*"
    )
    dp.register_callback_query_handler(
        cancel_race_callback,
        lambda c: c.data and c.data.startswith("cancel_race_"),
        state="*"
    )

    dp.register_message_handler(
        cancel_race_message,
        lambda m: m.text and m.text.lower().strip() in ["отмена", "cancel"],
        state="*"
    )
