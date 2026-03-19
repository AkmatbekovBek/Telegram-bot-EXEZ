# handlers/donate/payment.py

import logging
from aiogram import types
from aiogram.types import LabeledPrice
from .config import COIN_PACKAGES, DONATE_ITEMS, AMMERPAY_PROVIDER_TOKEN

logger = logging.getLogger(__name__)


class PaymentHandler:
    """Класс для обработки платежей через Telegram Stars"""

    def __init__(self, bot):
        self.bot = bot
        self.provider_token = AMMERPAY_PROVIDER_TOKEN

    async def send_stars_invoice(self, chat_id: int, item_type: str, item_id: int):
        """Отправляет счет для оплаты звездами"""
        try:
            if item_type == "coins":
                package = next((p for p in COIN_PACKAGES if p["id"] == item_id), None)
                if not package:
                    return False

                title = f"💎 {package['amount']:,} монет"
                description = f"Покупка {package['amount']:,} монет за {package['stars_text']}"
                # Изменено: используем stars_price без умножения на 100
                # и меняем currency на "USD" или другую, где 1 единица = 1 звезда
                prices = [LabeledPrice(label="Звезды", amount=package['stars_price'])]

            elif item_type == "privilege":
                item = next((i for i in DONATE_ITEMS if i["id"] == item_id), None)
                if not item or not item.get("stars_price"):
                    return False

                title = item['name']
                description = f"{item['description']}\nДлительность: {item['duration']}"
                # Изменено: используем stars_price без умножения на 100
                prices = [LabeledPrice(label="Звезды", amount=item['stars_price'])]

            else:
                return False

            # Отправляем счет
            await self.bot.send_invoice(
                chat_id=chat_id,
                title=title,
                description=description,
                payload=f"{item_type}_{item_id}",
                provider_token=self.provider_token,
                currency="XTR",  # Telegram Stars
                prices=prices,
                start_parameter=f"{item_type}_{item_id}",
                need_email=False,
                need_phone_number=False,
                need_shipping_address=False,
                is_flexible=False,
                max_tip_amount=0
            )

            return True

        except Exception as e:
            logger.error(f"Error sending stars invoice: {e}")
            return False