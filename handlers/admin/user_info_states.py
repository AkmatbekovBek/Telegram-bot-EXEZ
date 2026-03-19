# handlers/admin/user_info_states.py

from aiogram.dispatcher.filters.state import State, StatesGroup


class UserInfoStates(StatesGroup):
    """Состояния FSM для управления информацией о пользователях"""
    waiting_for_ban_reason = State()
    waiting_for_reset_confirm = State()