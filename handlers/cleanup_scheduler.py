# services/cleanup_scheduler.py
import asyncio
import logging
import pytz
from datetime import datetime, timedelta
from contextlib import contextmanager

from database import SessionLocal, get_db
from database.crud import TransferLimitRepository, DonateRepository, PoliceRepository

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """Планировщик для ежедневной очистки данных"""

    def __init__(self):
        self.kg_tz = pytz.timezone("Asia/Bishkek")
        self._is_running = False
        self._cleanup_task = None

    @contextmanager
    def get_db_session(self):
        """Контекстный менеджер для работы с сессией БД"""
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    async def start_daily_cleanup(self):
        """Запускает ежедневную очистку в 00:00 по времени Кыргызстана"""
        self._is_running = True
        logger.info("🔄 Планировщик очистки запущен")

        try:
            while self._is_running:
                now = datetime.now(self.kg_tz)

                # Следующая полуночь (00:00) в Asia/Bishkek
                target_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

                # Если сейчас уже после/в 00:00 текущего дня — переносим на следующую дату
                # ВАЖНО: НЕ используем replace(day=day+1), потому что это ломается на конце месяца.
                if now >= target_time:
                    target_time = target_time + timedelta(days=1)

                wait_seconds = (target_time - now).total_seconds()

                # Логируем человечески
                logger.info(
                    f"⏰ Следующая очистка через {wait_seconds:.0f} секунд ({wait_seconds / 3600:.1f} часов)"
                )

                # Ждём, но проверяем флаг остановки каждые <= 60 секунд
                waited = 0.0
                while self._is_running and waited < wait_seconds:
                    step = min(60.0, wait_seconds - waited)
                    await asyncio.sleep(step)
                    waited += step

                if self._is_running:
                    await self.run_cleanup()

        except asyncio.CancelledError:
            logger.info("⏹️ Планировщик очистки остановлен (cancelled)")
            raise
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в планировщике очистки: {e}", exc_info=True)
            raise

    async def cleanup_expired_privileges(self):
        """Очищает просроченные привилегии"""
        db = next(get_db())
        try:
            from sqlalchemy import text

            now = datetime.now(self.kg_tz)
            result = db.execute(
                text(
                    """
                    DELETE FROM user_purchases
                    WHERE expires_at IS NOT NULL
                      AND expires_at < :now
                    """
                ),
                {"now": now},
            )
            db.commit()

            if result.rowcount and result.rowcount > 0:
                logger.info(f"🧹 Cleaned up {result.rowcount} expired privileges")

        except Exception as e:
            logger.error(f"❌ Error cleaning expired privileges: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    async def cleanup_expired_arrests_periodically(self):
        """Периодическая очистка истекших арестов (раз в час)"""
        while True:
            try:
                db = next(get_db())
                cleaned = PoliceRepository.cleanup_expired_arrests(db)
                db.commit()
                if cleaned and cleaned > 0:
                    logger.info(f"🧹 Auto-cleaned {cleaned} expired arrests")
            except Exception as e:
                logger.error(f"❌ Error in auto-cleaning arrests: {e}", exc_info=True)
            finally:
                await asyncio.sleep(3600)

    async def run_cleanup(self):
        """Выполняет очистку данных"""
        try:
            with self.get_db_session() as db:
                deleted_transfers = TransferLimitRepository.clean_old_transfers(db)
                expired_purchases = DonateRepository.cleanup_expired_purchases(db)

                current_time = datetime.now(self.kg_tz).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"✅ Ежедневная очистка выполнена в {current_time}")
                logger.info(f"📊 Удалено записей трансферов: {deleted_transfers}")
                logger.info(f"📊 Удалено истекших покупок: {expired_purchases}")

                return {"transfers": deleted_transfers, "purchases": expired_purchases}

        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении очистки: {e}", exc_info=True)
            return {"transfers": 0, "purchases": 0}

    async def run_manual_cleanup(self):
        """Ручной запуск очистки (для админов)"""
        try:
            result = await self.run_cleanup()
            return (
                "✅ Очистка выполнена успешно.\n"
                f"Трансферы: {result.get('transfers', 0)}\n"
                f"Покупки: {result.get('purchases', 0)}"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при ручной очистке: {e}", exc_info=True)
            return f"❌ Ошибка при очистке: {e}"

    async def stop(self):
        """Корректная остановка планировщика"""
        self._is_running = False
        logger.info("🛑 Остановка планировщика очистки...")

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ Планировщик очистки остановлен")

    async def start(self):
        """Запуск планировщика и сохранение задачи"""
        if self._cleanup_task and not self._cleanup_task.done():
            # Уже запущен — не создаём второй раз
            return self._cleanup_task

        self._cleanup_task = asyncio.create_task(self.start_daily_cleanup())
        return self._cleanup_task

    def is_running(self):
        """Проверка, работает ли планировщик"""
        return bool(self._is_running and self._cleanup_task and not self._cleanup_task.done())
