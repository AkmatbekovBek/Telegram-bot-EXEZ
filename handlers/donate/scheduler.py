import logging
from datetime import datetime, timedelta
from database import get_db
import asyncio
from sqlalchemy import and_
from database.models import UserPurchase

logger = logging.getLogger(__name__)


class DonateScheduler:
    """Планировщик для автоматической очистки истекших привилегий"""

    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        logger.info("💰 Инициализация DonateScheduler")

    async def start_scheduler(self):
        """Запускает планировщик"""
        self.is_running = True
        logger.info("🚀 Запуск планировщика очистки истекших привилегий")

        # Запускаем сразу первую проверку
        await self.cleanup_expired_privileges()

        # Запускаем цикл проверок
        while self.is_running:
            try:
                # Проверяем каждые 6 часов
                await asyncio.sleep(6 * 3600)
                await self.cleanup_expired_privileges()

                # Проверяем каждый день в 12:00 для уведомлений
                if datetime.now().hour == 12:
                    await self.check_expiring_soon()

            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике: {e}")
                await asyncio.sleep(3600)

    async def cleanup_expired_privileges(self):
        """Очищает истекшие привилегии"""
        try:
            logger.info("🧹 Проверка истекших привилегий...")
            db = next(get_db())

            current_time = datetime.now()

            # Находим истекшие покупки
            expired_purchases = db.query(UserPurchase).filter(
                and_(
                    UserPurchase.expires_at.isnot(None),
                    UserPurchase.expires_at <= current_time
                )
            ).all()

            expired_count = 0
            for purchase in expired_purchases:
                try:
                    # Получаем имя пользователя для логов
                    from database.crud import UserRepository
                    user = UserRepository.get_user_by_telegram_id(db, purchase.user_id)
                    username = f"@{user.username}" if user and user.username else f"ID:{purchase.user_id}"

                    # Помечаем покупку как неактивную (если есть поле)
                    if hasattr(purchase, 'is_active'):
                        purchase.is_active = False
                        logger.info(f"❌ Привилегия истекла: {username}, item_id={purchase.item_id}")
                        expired_count += 1
                    else:
                        # Если нет поля is_active, удаляем запись
                        db.delete(purchase)
                        logger.info(f"🗑️ Удалена истекшая привилегия: {username}, item_id={purchase.item_id}")
                        expired_count += 1

                except Exception as e:
                    logger.error(f"❌ Ошибка обработки покупки {purchase.id}: {e}")
                    continue

            if expired_count > 0:
                db.commit()
                logger.info(f"✅ Очищено {expired_count} истекших привилегий")
            else:
                logger.info("✅ Истекших привилегий не найдено")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки привилегий: {e}")

    async def check_expiring_soon(self):
        """Проверяет привилегии, которые скоро истекут"""
        try:
            logger.info("🔔 Проверка привилегий, которые скоро истекут...")
            db = next(get_db())

            tomorrow = datetime.now() + timedelta(days=1)
            day_after_tomorrow = datetime.now() + timedelta(days=2)

            # Находим привилегии, которые истекают завтра
            expiring_soon = db.query(UserPurchase).filter(
                and_(
                    UserPurchase.expires_at.isnot(None),
                    UserPurchase.expires_at >= tomorrow,
                    UserPurchase.expires_at <= day_after_tomorrow
                )
            ).all()

            # Отправляем уведомления пользователям
            notification_count = 0
            for purchase in expiring_soon:
                try:
                    if await self.send_expiration_notification(purchase):
                        notification_count += 1
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки уведомления для покупки {purchase.id}: {e}")

            if notification_count > 0:
                logger.info(f"📢 Отправлено {notification_count} уведомлений об истечении")

        except Exception as e:
            logger.error(f"❌ Ошибка проверки истекающих привилегий: {e}")

    async def send_expiration_notification(self, purchase):
        """Отправляет уведомление об истечении привилегии"""
        try:
            item_names = {
                1: "👑 Вор в законе",
                2: "👮‍♂️ Полицейский",
                3: "🔐 Снятие лимита перевода"
            }

            item_name = item_names.get(purchase.item_id, "привилегия")
            expires_date = purchase.expires_at.strftime("%d.%m.%Y")

            message = (
                f"⚠️ <b>Внимание!</b>\n\n"
                f"Ваша привилегия <b>{item_name}</b> истекает {expires_date}!\n\n"
                f"Чтобы продлить, обратитесь к @EXEZ_Kassa"
            )

            await self.bot.send_message(purchase.user_id, message, parse_mode="HTML")
            logger.info(f"📢 Отправлено уведомление пользователю {purchase.user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления пользователю {purchase.user_id}: {e}")
            return False

    async def stop_scheduler(self):
        """Останавливает планировщик"""
        self.is_running = False
        logger.info("🛑 Остановка планировщика очистки привилегий")