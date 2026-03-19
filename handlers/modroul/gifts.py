import asyncio
from typing import List, Dict, Optional
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections import defaultdict
from venv import logger

from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import bot
from database import get_db
from database.crud import GiftRepository, UserRepository, TransactionRepository


# =============================================================================
# КОНФИГУРАЦИЯ И МОДЕЛИ
# =============================================================================

@dataclass(frozen=True)
class GiftConfig:
    """Конфигурация системы подарков"""
    MAX_QUANTITY_PER_PURCHASE: int = 100
    MAX_QUANTITY_PER_GIFT: int = 1000
    DEFAULT_QUANTITIES: tuple = (1, 3, 5, 10, 50, 100)
    BULK_DISCOUNTS: Dict[int, float] = None

    def __post_init__(self):
        if self.BULK_DISCOUNTS is None:
            object.__setattr__(self, 'BULK_DISCOUNTS', {
                10: 0.95,  # 5% скидка
                50: 0.90,  # 10% скидка
                100: 0.85,  # 15% скидка
            })


# =============================================================================
# УТИЛИТЫ И СЕРВИСЫ
# =============================================================================

class DatabaseManager:
    """Менеджер для работы с базой данных"""

    __slots__ = ()

    @staticmethod
    @asynccontextmanager
    async def db_session():
        """Асинхронный контекстный менеджер для БД"""
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()


class GiftFormatter:
    """Утилиты для форматирования подарков"""

    __slots__ = ()

    @staticmethod
    def format_price(price: int) -> str:
        """Форматирует цену с разделителями"""
        return f"{price:,}".replace(",", ".")

    @staticmethod
    def format_quantity(quantity: int) -> str:
        """Форматирует количество"""
        return f"{quantity:,}".replace(",", ".")

    @staticmethod
    def calculate_discounted_price(original_price: int, quantity: int, discounts: Dict[int, float]) -> int:
        """Рассчитывает цену со скидкой за опт"""
        for min_qty, discount in sorted(discounts.items(), reverse=True):
            if quantity >= min_qty:
                return int(original_price * quantity * discount)
        return original_price * quantity

    @staticmethod
    def get_discount_percentage(quantity: int, discounts: Dict[int, float]) -> Optional[int]:
        """Получает процент скидки для количества"""
        for min_qty, discount in sorted(discounts.items(), reverse=True):
            if quantity >= min_qty:
                return int((1 - discount) * 100)
        return None


class UserFormatter:
    """Утилиты для форматирования пользователей"""

    __slots__ = ()

    @staticmethod
    def get_user_link_html(user_id: int, display_name: str) -> str:
        """Создает HTML-ссылку на профиль пользователя"""
        safe_name = display_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

    @staticmethod
    def format_user_html(user: types.User) -> str:
        """Форматирует объект пользователя с HTML-ссылкой"""
        display_name = user.first_name or f"@{user.username}" if user.username else "Аноним"
        return UserFormatter.get_user_link_html(user.id, display_name)


# =============================================================================
# ДАННЫЕ ПОДАРКОВ
# =============================================================================

class GiftData:
    """Данные подарков"""

    __slots__ = ()

    @staticmethod
    def get_default_gifts():
        """Возвращает список подарков по умолчанию"""
        return [
            {
                'name': 'Кольцо',
                'sticker': '💍',
                'price': 5000000,
                'compliment': '{giver} предлагает {receiver} кольцо! 💍'
            },
            {
                'name': 'Бриллиант',
                'sticker': '💎',
                'price': 10000000,
                'compliment': '{giver} дарит {receiver} роскошный бриллиант! 💎'
            },
            {
                'name': 'Тигр',
                'sticker': '🐯',
                'price': 15000000,
                'compliment': '{giver} отправляет {receiver} грозного тигра! 🐯'
            },
            {
                'name': 'Панда',
                'sticker': '🐼',
                'price': 7000000,
                'compliment': '{giver} отправляет {receiver} милую панду! 🐼'
            },
            {
                'name': 'Цыплёнок',
                'sticker': '🐥',
                'price': 3000000,
                'compliment': '{giver} дарит {receiver} милого цыплёнка! 🐥'
            },
            {
                'name': 'Чебурашка',
                'sticker': '🐻',
                'price': 4500000,
                'compliment': '{giver} отправляет {receiver} легендарного Чебурашку! 🐻'
            },
            {
                'name': 'Кулон',
                'sticker': '💫',
                'price': 2500000,
                'compliment': '{giver} дарит {receiver} элегантный кулон! 💫'
            },
            {
                'name': 'Лимон',
                'sticker': '🍋',
                'price': 1000000,
                'compliment': 'Ты, как лимон, всегда добавляешь яркость и свежесть в любое общение! Твоя энергия и позитив заряжают'
            },
            {
                'name': 'Шаурма',
                'sticker': '🌯',
                'price': 150000,
                'compliment': '{giver} угощает {receiver} вкусной шаурмой! 🌯'
            },
            {
                'name': 'Хуй',
                'sticker': '🍌',
                'price': 1000000,
                'compliment': '{giver} шутливо дарит {receiver} особый подарок! 🍌'
            },
            {
                'name': 'Лев',
                'sticker': '🦁',
                'price': 4000000,
                'compliment': '{giver} дарит {receiver} царственного льва! 🦁'
            },
            {
                'name': 'Роза',
                'sticker': '🌹',
                'price': 1000000,
                'compliment': '{giver} дарит {receiver} прекрасную розу! 🌹'
            },
            {
                'name': 'Шоколад',
                'sticker': '🍫',
                'price': 5000000,
                'compliment': '{giver} угощает {receiver} вкусным шоколадом! 🍫'
            },
            {
                'name': 'Сердце',
                'sticker': '❤️',
                'price': 2000000,
                'compliment': '{giver} отправляет {receiver} сердце, полное любви! ❤️'
            },
            {
                'name': 'Подарок',
                'sticker': '🎁',
                'price': 1500000,
                'compliment': '{giver} дарит {receiver} праздничный подарок! 🎁'
            },
            {
                'name': 'Мишка',
                'sticker': '🧸',
                'price': 5000000,
                'compliment': '{giver} дарит {receiver} милого мишку! 🧸'
            }
        ]

    @staticmethod
    async def ensure_gifts_exist():
        """Обеспечивает наличие подарков в базе данных"""
        try:
            async with DatabaseManager.db_session() as db:
                existing_gifts = GiftRepository.get_all_gifts(db)
                existing_names = {gift.name for gift in existing_gifts}

                default_gifts = GiftData.get_default_gifts()
                created_count = 0

                for gift_data in default_gifts:
                    if gift_data['name'] not in existing_names:
                        # Создаем подарок
                        GiftRepository.create_gift(
                            db=db,
                            name=gift_data['name'],
                            sticker=gift_data['sticker'],
                            price=gift_data['price'],
                            compliment=gift_data['compliment']
                        )
                        created_count += 1
                        logger.info(f"✅ Создан подарок: {gift_data['name']}")

                if created_count > 0:
                    db.commit()
                    logger.info(f"✅ Создано {created_count} подарков")
                else:
                    logger.info("✅ Все подарки уже существуют в базе")

        except Exception as e:
            logger.error(f"❌ Ошибка создания подарков: {e}")


# =============================================================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# =============================================================================

class GiftHandlers:
    """Обработчики системы подарков"""

    __slots__ = ('_config', '_gift_formatter', '_user_formatter')

    def __init__(self):
        self._config = GiftConfig()
        self._gift_formatter = GiftFormatter()
        self._user_formatter = UserFormatter()

    def _group_user_gifts(self, user_gifts: List) -> Dict[int, Dict]:
        """Группирует подарки пользователя по ID подарка"""
        grouped_gifts = defaultdict(lambda: {'gift': None, 'quantity': 0})

        for user_gift in user_gifts:
            gift_id = user_gift.gift.id
            if grouped_gifts[gift_id]['gift'] is None:
                grouped_gifts[gift_id]['gift'] = user_gift.gift
            grouped_gifts[gift_id]['quantity'] += user_gift.quantity

        return grouped_gifts

    # ---------- КЛАВИАТУРЫ ----------

    async def create_gifts_keyboard(self) -> InlineKeyboardMarkup:
        """Создает клавиатуру для раздела подарков"""
        keyboard = InlineKeyboardMarkup(row_width=2)

        async with DatabaseManager.db_session() as db:
            try:
                gifts = GiftRepository.get_all_gifts(db)

                for gift in gifts:
                    keyboard.add(InlineKeyboardButton(
                        text=f"{gift.sticker} {gift.name} - {gift.price:,} монет".replace(",", "."),
                        callback_data=f"gift_select_{gift.id}"
                    ))

                # Кнопка "Мои подарки"
                keyboard.add(InlineKeyboardButton(
                    text="🎁 Мои подарки",
                    callback_data="my_gifts"
                ))

                keyboard.add(InlineKeyboardButton(
                    text="⬅️ Назад в магазин",
                    callback_data="back_to_shop"
                ))

                # Кнопка назад в меню
                keyboard.add(InlineKeyboardButton(
                    text="🏠 В главное меню",
                    callback_data="back_to_main"
                ))

            except Exception as e:
                logger.error(f"❌ Ошибка создания клавиатуры подарков: {e}")

        return keyboard

    def create_quantity_keyboard(self, gift_id: int, max_quantity: int = None) -> InlineKeyboardMarkup:
        """Создает клавиатуру для выбора количества"""
        keyboard = InlineKeyboardMarkup(row_width=3)

        quantities = self._config.DEFAULT_QUANTITIES
        if max_quantity:
            quantities = [q for q in self._config.DEFAULT_QUANTITIES if q <= max_quantity]

        for qty in quantities:
            keyboard.insert(InlineKeyboardButton(
                text=str(qty),
                callback_data=f"gift_buy_{gift_id}_{qty}"
            ))

        keyboard.add(InlineKeyboardButton(
            text="✏️ Ввести количество",
            callback_data=f"enter_gift_qty_{gift_id}"
        ))

        keyboard.row(
            InlineKeyboardButton("⬅️ Назад к подаркам", callback_data="gifts"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")
        )

        return keyboard

    # ---------- ОСНОВНЫЕ ОБРАБОТЧИКИ ----------

    async def gifts_section(self, callback: types.CallbackQuery):
        """Обработчик раздела подарков"""
        try:
            await callback.message.edit_text(
                "🎁 **Магазин подарков**\n\n"
                "💎 **Оптовые скидки:**\n"
                "• 10+ шт. - 5% скидка\n"
                "• 50+ шт. - 10% скидка\n"
                "• 100+ шт. - 15% скидка\n\n"
                "Выберите подарок для покупки:",
                reply_markup=await self.create_gifts_keyboard(),
                parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка в разделе подарков: {e}")
            await callback.message.edit_text(
                "❌ Произошла ошибка при загрузке подарков.",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_shop")
                )
            )
        finally:
            await callback.answer()

    async def select_gift_quantity(self, callback: types.CallbackQuery):
        """Выбор количества для покупки подарка"""
        try:
            gift_id = int(callback.data.split("_")[2])

            async with DatabaseManager.db_session() as db:
                gift = GiftRepository.get_gift_by_id(db, gift_id)
                user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)

                if not gift:
                    await callback.answer("❌ Подарок не найден!", show_alert=True)
                    return

                max_affordable = user.coins // gift.price
                max_quantity = min(max_affordable, self._config.MAX_QUANTITY_PER_PURCHASE)

                quantity_text = ""
                if max_quantity > 0:
                    # Показываем примеры цен со скидками
                    quantity_text = "\n💎 **Примеры цен:**\n"
                    for qty in [1, 10, 50, 100]:
                        if qty <= max_quantity:
                            total_price = self._gift_formatter.calculate_discounted_price(
                                gift.price, qty, self._config.BULK_DISCOUNTS
                            )
                            discount = self._gift_formatter.get_discount_percentage(qty, self._config.BULK_DISCOUNTS)
                            discount_text = f" (-{discount}%)" if discount else ""
                            quantity_text += f"• {qty} шт. - {total_price:,} монет{discount_text}\n".replace(",", ".")

                await callback.message.edit_text(
                    f"🎁 **Выберите количество**\n\n"
                    f"{gift.sticker} **{gift.name}**\n"
                    f"💎 Цена за шт.: {gift.price:,} монет\n"
                    f"💰 Ваш баланс: {user.coins:,} монет\n"
                    f"📦 Макс. можно купить: {max_quantity} шт.\n"
                    f"{quantity_text}",
                    reply_markup=self.create_quantity_keyboard(gift_id, max_quantity),
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка выбора количества: {e}")
            await callback.answer("❌ Ошибка!", show_alert=True)

    async def buy_gift(self, callback: types.CallbackQuery):
        """Покупка подарка с указанным количеством"""
        try:
            parts = callback.data.split("_")
            gift_id = int(parts[2])
            quantity = int(parts[3]) if len(parts) > 3 else 1

            async with DatabaseManager.db_session() as db:
                gift = GiftRepository.get_gift_by_id(db, gift_id)
                user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)

                if not gift:
                    await callback.message.edit_text(
                        "❌ Подарок не найден!",
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("⬅️ Назад", callback_data="gifts")
                        )
                    )
                    return

                # Рассчитываем итоговую цену со скидкой
                total_price = self._gift_formatter.calculate_discounted_price(
                    gift.price, quantity, self._config.BULK_DISCOUNTS
                )
                discount = self._gift_formatter.get_discount_percentage(quantity, self._config.BULK_DISCOUNTS)

                if user.coins >= total_price:
                    # Списываем деньги
                    user.coins -= total_price

                    # Добавляем подарки пользователю
                    for _ in range(quantity):
                        GiftRepository.add_gift_to_user(db, user.telegram_id, gift.id)

                    db.commit()

                    # Формируем сообщение о покупке
                    discount_text = f" (скидка {discount}%)" if discount else ""
                    success_text = (
                        f"✅ **Подарки куплены!**\n\n"
                        f"{gift.sticker} **{gift.name}** × {quantity}\n"
                        f"💎 Спиcано: {total_price:,} монет{discount_text}\n"
                        f"💎 Новый баланс: {user.coins:,} монет\n\n"
                    ).replace(",", ".")

                    if quantity > 1:
                        success_text += f"💝 Чтобы подарить, используйте команду:\n`подарить {gift.name} [количество]` ответом на сообщение друга"
                    else:
                        success_text += f"💝 Чтобы подарить, используйте команду:\n`подарить {gift.name}` ответом на сообщение друга"

                    await callback.message.edit_text(
                        success_text,
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("🎁 Мои подарки", callback_data="my_gifts"),
                            InlineKeyboardButton("🛍️ Еще подарки", callback_data="gifts")
                        ),
                        parse_mode="Markdown"
                    )
                else:
                    missing = total_price - user.coins
                    await callback.message.edit_text(
                        f"❌ **Недостаточно монет!**\n\n"
                        f"💎 Нужно: {total_price:,} монет\n"
                        f"💎 У вас: {user.coins:,} монет\n"
                        f"💸 Не хватает: {missing:,} монет".replace(",", "."),
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("⬅️ Назад", callback_data="gifts")
                        ),
                        parse_mode="Markdown"
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка покупки подарка: {e}")
            async with DatabaseManager.db_session() as db:
                db.rollback()
            await callback.message.edit_text(
                "❌ Ошибка при покупке подарка!",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Назад", callback_data="gifts")
                )
            )
        finally:
            await callback.answer()

    async def enter_gift_quantity(self, callback: types.CallbackQuery):
        """Обработчик ввода пользовательского количества"""
        try:
            gift_id = int(callback.data.split("_")[3])

            async with DatabaseManager.db_session() as db:
                gift = GiftRepository.get_gift_by_id(db, gift_id)
                user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)

                if not gift:
                    await callback.answer("❌ Подарок не найден!", show_alert=True)
                    return

                max_affordable = user.coins // gift.price
                max_quantity = min(max_affordable, self._config.MAX_QUANTITY_PER_PURCHASE)

                await callback.message.edit_text(
                    f"✏️ **Введите количество**\n\n"
                    f"{gift.sticker} **{gift.name}**\n"
                    f"💎 Цена за шт.: {gift.price:,} монет\n"
                    f"💰 Ваш баланс: {user.coins:,} монет\n"
                    f"📦 Максимум: {max_quantity} шт.\n\n"
                    f"Отправьте число от 1 до {max_quantity}:",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("⬅️ Отмена", callback_data=f"gift_select_{gift_id}")
                    ),
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка ввода количества: {e}")
            await callback.answer("❌ Ошибка!", show_alert=True)

    async def process_custom_quantity(self, message: types.Message):
        """Обработка пользовательского ввода количества"""
        try:
            # Это упрощенная версия - в реальности нужно использовать FSM
            if not message.reply_to_message:
                await message.reply("❌ Ответьте на сообщение с выбором подарка!")
                return

            quantity = int(message.text.strip())

            if quantity <= 0:
                await message.reply("❌ Количество должно быть больше 0!")
                return

            if quantity > self._config.MAX_QUANTITY_PER_PURCHASE:
                await message.reply(f"❌ Нельзя купить больше {self._config.MAX_QUANTITY_PER_PURCHASE} шт. за раз!")
                return

            # В реальной реализации здесь нужно получить gift_id из состояния
            await message.reply("⚠️ Функция временно недоступна. Используйте кнопки выбора количества.")

        except ValueError:
            await message.reply("❌ Пожалуйста, введите корректное число!")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки количества: {e}")
            await message.reply("❌ Ошибка обработки!")

    # ---------- МОИ ПОДАРКИ ----------

    async def my_gifts(self, callback: types.CallbackQuery):
        """Просмотр своих подарков"""
        try:
            async with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)
                user_gifts = GiftRepository.get_user_gifts(db, user.telegram_id)

                if not user_gifts:
                    await callback.message.edit_text(
                        "🎁 **Мои подарки**\n\n"
                        "У вас пока нет подарков 😔\n\n"
                        "Приобретите подарки в магазине, чтобы порадовать друзей!",
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("🛍️ В магазин подарков", callback_data="gifts"),
                            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_shop")
                        )
                    )
                    return

                # Группируем подарки по ID
                grouped_gifts = self._group_user_gifts(user_gifts)

                gifts_text = "🎁 **Мои подарки**\n\n"
                total_gifts = 0
                total_value = 0

                # Выводим сгруппированные подарки
                for gift_data in grouped_gifts.values():
                    gift = gift_data['gift']
                    quantity = gift_data['quantity']

                    gifts_text += f"{gift.sticker} **{gift.name}** × {quantity:,}\n".replace(",", ".")
                    total_gifts += quantity
                    total_value += gift.price * quantity

                gifts_text += f"\n📊 **Статистика:**\n"
                gifts_text += f"• Всего подарков: {total_gifts:,}\n".replace(",", ".")
                gifts_text += f"• Общая стоимость: {total_value:,} монет\n\n".replace(",", ".")
                gifts_text += f"💝 **Чтобы подарить:**\n"
                gifts_text += f"Ответьте на сообщение друга командой:\n"
                gifts_text += f"`подарить [название] [количество]`\n\n"
                gifts_text += f"**Примеры:**\n• `подарить Роза`\n• `подарить Роза 5`"

                await callback.message.edit_text(
                    gifts_text,
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("🛍️ В магазин подарков", callback_data="gifts"),
                        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_shop")
                    ),
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения подарков: {e}")
            await callback.message.edit_text(
                "❌ Ошибка при загрузке ваших подарков!",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Назад", callback_data="gifts")
                )
            )
        finally:
            await callback.answer()

    # ---------- ТЕКСТОВЫЕ КОМАНДЫ ----------

    def _is_gift_command(self, text: str) -> bool:
        """Проверяет, является ли текст командой подарка (регистронезависимо)"""
        if not text:
            return False

        # Приводим к нижнему регистру для проверки
        text_lower = text.lower().strip()

        # Проверяем различные варианты написания команды
        gift_commands = ['подарить', 'подарок', 'дарю', 'дарить']

        # Проверяем, начинается ли текст с любой из команд
        for command in gift_commands:
            if text_lower.startswith(command):
                return True

        return False

    async def give_gift_command(self, message: types.Message):
        """Команда для дарения подарков с красивым оформлением"""
        try:
            logger.info(f"🔍 Получена команда: {message.text}")

            # Проверяем, является ли сообщение ответом на другое сообщение
            if not message.reply_to_message:
                await message.reply(
                    "💝 **Как подарить подарок?**\n\n"
                    "1️⃣ **Найдите сообщение друга**\n"
                    "2️⃣ **Ответьте на него командой:**\n"
                    "   `подарить [название] [количество]`\n\n"
                    "✨ **Примеры:**\n"
                    "• `Подарить Роза`\n"
                    "• `подарить Сердце 5`\n"
                    "• `Дарю Шарик 10`\n\n"
                    "🎁 **Доступные подарки:** /подарки",
                    parse_mode="Markdown"
                )
                return

            # Получаем получателя подарка
            recipient_user = message.reply_to_message.from_user

            # Нельзя дарить подарки самому себе
            if recipient_user.id == message.from_user.id:
                await message.reply("❌ Нельзя дарить подарки самому себе! Найдите друга 😊")
                return

            # Парсим команду
            parts = message.text.split()
            logger.info(f"🔍 Части команды: {parts}")

            if len(parts) < 2:
                await message.reply(
                    "💝 **Неверный формат команды!**\n\n"
                    "**Правильный формат:**\n"
                    "`подарить [название подарка] [количество]`\n\n"
                    "✨ **Примеры:**\n"
                    "• `Подарить Роза`\n"
                    "• `подарить Роза 5`\n"
                    "• `Дарю Сердце 10`\n\n"
                    "🎁 **Доступные подарки:** /подарки",
                    parse_mode="Markdown"
                )
                return

            # Парсим количество (по умолчанию 1)
            quantity = 1
            gift_name_parts = parts[1:]

            # Проверяем, последняя часть - число ли
            if gift_name_parts and gift_name_parts[-1].isdigit():
                quantity = int(gift_name_parts[-1])
                gift_name = " ".join(gift_name_parts[:-1])
            else:
                gift_name = " ".join(gift_name_parts)

            # Ограничение на количество
            if quantity <= 0:
                await message.reply("❌ Количество должно быть больше 0!")
                return

            if quantity > self._config.MAX_QUANTITY_PER_GIFT:
                await message.reply(f"❌ Нельзя подарить больше {self._config.MAX_QUANTITY_PER_GIFT} подарков за раз!")
                return

            logger.info(f"🔍 Имя подарка: '{gift_name}', количество: {quantity}")
            logger.info(f"🔍 ID дарителя: {message.from_user.id}, ID получателя: {recipient_user.id}")

            async with DatabaseManager.db_session() as db:
                # Получаем подарок по имени (регистронезависимо)
                gift = GiftRepository.get_gift_by_name(db, gift_name)

                # Если не нашли, пробуем найти по части имени
                if not gift:
                    all_gifts = GiftRepository.get_all_gifts(db)
                    for g in all_gifts:
                        if g.name.lower() == gift_name.lower():
                            gift = g
                            break

                logger.info(f"🔍 Найденный подарок: {gift}")

                if not gift:
                    # Показываем доступные подарки
                    gifts = GiftRepository.get_all_gifts(db)
                    available_gifts = "\n".join([f"• {g.sticker} {g.name}" for g in gifts])
                    logger.info(f"🔍 Доступные подарки: {available_gifts}")

                    await message.reply(
                        f"❌ Подарок `{gift_name}` не найден!\n\n"
                        f"🎁 **Доступные подарки:**\n{available_gifts}\n\n"
                        f"💝 **Попробуйте:**\n`Подарить [название]`",
                        parse_mode="Markdown"
                    )
                    return

                # Получаем отправителя и получателя
                sender = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
                recipient = UserRepository.get_user_by_telegram_id(db, recipient_user.id)

                logger.info(f"🔍 Пользователь даритель: {sender}")
                logger.info(f"🔍 Пользователь получатель: {recipient}")

                if not recipient:
                    await message.reply("❌ Пользователь не найден в базе!")
                    return

                # Проверяем, есть ли у отправителя достаточно подарков
                user_gifts = GiftRepository.get_user_gifts(db, sender.telegram_id)
                # Группируем подарки для проверки общего количества
                grouped_gifts = self._group_user_gifts(user_gifts)

                if gift.id not in grouped_gifts or grouped_gifts[gift.id]['quantity'] < quantity:
                    available_quantity = grouped_gifts[gift.id]['quantity'] if gift.id in grouped_gifts else 0
                    await message.reply(
                        f"❌ Недостаточно подарков {gift.sticker} {gift.name}!\n\n"
                        f"💝 У вас есть: {available_quantity} шт.\n"
                        f"📦 Требуется: {quantity} шт.\n\n"
                        f"🛍️ Приобретите больше в магазине: /подарки",
                        parse_mode="Markdown"
                    )
                    return

                # Передаем подарки
                try:
                    # Убираем подарки у отправителя
                    # Удаляем quantity штук этого подарка
                    gifts_to_remove = quantity
                    user_gift_items = [ug for ug in user_gifts if ug.gift.id == gift.id]

                    # Удаляем записи пока не уберем нужное количество
                    for user_gift in user_gift_items:
                        if gifts_to_remove <= 0:
                            break
                        if user_gift.quantity <= gifts_to_remove:
                            gifts_to_remove -= user_gift.quantity
                            GiftRepository.remove_gift_from_user(db, sender.telegram_id, gift.id, user_gift.quantity)
                        else:
                            GiftRepository.remove_gift_from_user(db, sender.telegram_id, gift.id, gifts_to_remove)
                            gifts_to_remove = 0

                    # Добавляем подарки получателю
                    for _ in range(quantity):
                        GiftRepository.add_gift_to_user(db, recipient.telegram_id, gift.id)

                    # Записываем транзакции в историю для обоих пользователей
                    # Для дарителя
                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=sender.telegram_id,
                        to_user_id=recipient.telegram_id,
                        amount=0,
                        description=f"подарил {quantity} {gift.name.lower()} {gift.sticker} игроку"
                    )

                    # Для получателя
                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=sender.telegram_id,
                        to_user_id=recipient.telegram_id,
                        amount=0,
                        description=f"получил в подарок {quantity} {gift.name.lower()} {gift.sticker} от игрока"
                    )

                    db.commit()

                    # Получаем актуальные имена пользователей с запасными вариантами
                    giver_name = message.from_user.first_name or message.from_user.username or "Аноним"
                    receiver_name = recipient_user.first_name or recipient_user.username or "Аноним"

                    # Форматируем ссылки на профили пользователей
                    giver_link = self._user_formatter.get_user_link_html(message.from_user.id, giver_name)
                    receiver_link = self._user_formatter.get_user_link_html(recipient_user.id, receiver_name)

                    # ИСПРАВЛЕНИЕ: Используем комплимент из базы данных
                    compliment_text = f"{giver_name} подарил(а) подарок {receiver_name}"  # значение по умолчанию

                    # Проверяем есть ли поле compliment у подарка и используем его
                    if hasattr(gift, 'compliment') and gift.compliment:
                        try:
                            compliment_text = gift.compliment.format(giver=giver_name, receiver=receiver_name)
                        except Exception as e:
                            logger.error(f"❌ Ошибка форматирования комплимента: {e}")
                            compliment_text = f"{giver_name} дарит подарок {receiver_name}"

                    # Формируем красивое сообщение о дарении
                    success_message = (
                        f"{gift.sticker} <b>{compliment_text}</b>\n\n"
                        f"🎁 <b>Подарок:</b> {gift.name}\n"
                        f"📦 <b>Количество:</b> {quantity} шт.\n"
                        f"💝 <b>От:</b> {giver_link}\n"
                        f"💖 <b>Для:</b> {receiver_link}"
                    )

                    await message.answer(success_message, parse_mode="HTML")
                    logger.info(f"✅ Подарки успешно переданы! Количество: {quantity}")

                    # Отправляем красивое сообщение получателю
                    try:
                        ls_message = (
                            f"🎉 <b>Вам преподнесли подарок!</b>\n\n"
                            f"{gift.sticker} <i>{compliment_text}</i>\n\n"
                            f"🎁 <b>Подарок:</b> <i>{gift.name}</i>\n"
                            f"📦 <b>Количество:</b> <i>{quantity} шт.</i>\n"
                            f"💌 <b>От кого:</b> {giver_link}\n\n"
                            f"✨ Пусть этот подарок поднимет вам настроение! ✨"
                        )

                        await bot.send_message(
                            recipient_user.id,
                            ls_message,
                            parse_mode="HTML"
                        )
                        logger.info(f"✅ Уведомление отправлено получателю {recipient_user.id}")

                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось отправить уведомление получателю: {e}")

                except Exception as e:
                    db.rollback()
                    logger.error(f"❌ Ошибка при передаче подарка: {e}")
                    import traceback
                    traceback.print_exc()
                    await message.reply("❌ Произошла ошибка при передаче подарка!")

        except Exception as e:
            logger.error(f"❌ Ошибка в команде подарка: {e}")
            import traceback
            traceback.print_exc()
            await message.reply("❌ Произошла ошибка при обработке команды!")

    async def my_gifts_text(self, message: types.Message):
        """Текстовая команда для просмотра подарков"""
        try:
            async with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
                user_gifts = GiftRepository.get_user_gifts(db, user.telegram_id)

                if not user_gifts:
                    await message.answer(
                        "🎁 **Мои подарки**\n\n"
                        "📦 У вас пока нет подарков 😔\n\n"
                        "💝 Приобретите подарки в магазине, чтобы порадовать друзей!\n"
                        "🛍️ Магазин подарков: /подарки",
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("🛍️ В магазин подарков", callback_data="gifts")
                        ),
                        parse_mode="Markdown"
                    )
                    return

                # Группируем подарки по ID
                grouped_gifts = self._group_user_gifts(user_gifts)

                gifts_text = "🎁 **Мои подарки**\n\n"
                total_gifts = 0

                # Выводим сгруппированные подарки
                for gift_data in grouped_gifts.values():
                    gift = gift_data['gift']
                    quantity = gift_data['quantity']

                    gifts_text += f"{gift.sticker} {gift.name} × {quantity:,}\n".replace(",", ".")
                    total_gifts += quantity

                gifts_text += f"\n📊 <b>Всего подарков:</b> {total_gifts:,}\n".replace(",", ".")
                gifts_text += f"\n💝 <b>Как подарить?</b>\n"
                gifts_text += f"Ответьте на сообщение друга:\n"
                gifts_text += f"<code>подарить [название] [количество]</code>\n\n"
                gifts_text += f"✨ <b>Примеры:</b>\n• <code>Подарить Роза</code>\n• <code>дарю Роза 5</code>"

                await message.answer(
                    gifts_text,
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("🛍️ В магазин подарков", callback_data="gifts")
                    ),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка получения подарков: {e}")
            await message.answer("❌ Ошибка при загрузке ваших подарков!")

    async def gifts_text(self, message: types.Message):
        """Текстовая команда для открытия магазина подарков"""
        try:
            await message.answer(
                "🎁 **Магазин подарков**\n\n"
                "💎 **Оптовые скидки:**\n"
                "• 10+ шт. - 5% скидка\n"
                "• 50+ шт. - 10% скидка\n"
                "• 100+ шт. - 15% скидка\n\n"
                "💝 **Как подарить?**\n"
                "Ответьте на сообщение друга:\n"
                "<code>подарить [название]</code>\n\n"
                "Выберите подарок для покупки:",
                reply_markup=await self.create_gifts_keyboard(),
                parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка в разделе подарков: {e}")
            await message.answer("❌ Произошла ошибка при загрузке подарков.")


# =============================================================================
# РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================================================

async def ensure_gifts_on_startup():
    """Обеспечивает наличие подарков при запуске бота"""
    logger.info("🎁 Проверка подарков в базе данных...")
    await GiftData.ensure_gifts_exist()


def register_gift_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков подарков"""
    handlers = GiftHandlers()

    # Основные обработчики (callback)
    dp.register_callback_query_handler(handlers.gifts_section, lambda c: c.data == "gifts", state="*")
    dp.register_callback_query_handler(handlers.select_gift_quantity, lambda c: c.data.startswith("gift_select_"),
                                       state="*")
    dp.register_callback_query_handler(handlers.buy_gift, lambda c: c.data.startswith("gift_buy_"), state="*")
    dp.register_callback_query_handler(handlers.my_gifts, lambda c: c.data == "my_gifts", state="*")
    dp.register_callback_query_handler(handlers.enter_gift_quantity, lambda c: c.data.startswith("enter_gift_qty_"),
                                       state="*")

    # Текстовые команды (регистронезависимые)
    dp.register_message_handler(
        handlers.give_gift_command,
        lambda m: m.text and handlers._is_gift_command(m.text),
        state="*"
    )
    dp.register_message_handler(
        handlers.my_gifts_text,
        lambda m: m.text and m.text.lower() in ["мои подарки", "мои_подарки"],
        state="*"
    )
    dp.register_message_handler(
        handlers.gifts_text,
        lambda m: m.text and m.text.lower() in ["подарки", "магазин подарков"],
        state="*"
    )

    logger.info("✅ Обработчики подарков зарегистрированы с группировкой подарков")