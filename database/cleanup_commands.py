"""
Команды для очистки базы данных
"""
from database import SessionLocal
from database.models import *
from database.crud import TransferLimitRepository
from datetime import datetime, date
import time


class CleanupCommands:
    @staticmethod
    def full_cleanup():
        """
        Полная очистка всех данных (кроме структуры таблиц)
        """
        db = SessionLocal()
        try:
            print("🧹 НАЧИНАЕТСЯ ПОЛНАЯ ОЧИСТКА ВСЕХ ДАННЫХ...")
            print("=" * 60)

            # Словарь для статистики
            stats = {}

            # Список таблиц в правильном порядке (чтобы не нарушить foreign keys)
            cleanup_sequence = [
                ("Попытки кражи", StealAttempt),
                ("Аресты вора", ThiefArrest),
                ("Аресты пользователей", UserArrest),
                ("Запросы на развод", DivorceRequest),
                ("Браки", Marriage),
                ("Донат покупки", DonatePurchase),
                ("Поиск ников", UserNickSearch),
                ("Поиск чатов", UserChatSearch),
                ("Блокировки бот-стоп", BotStop),
                ("Логи модерации", ModerationLog),
                ("Лимиты рулетки", RouletteLimit),
                ("Лимиты переводов", TransferLimit),
                ("Покупки пользователей", UserPurchase),
                ("Транзакции рулетки", RouletteTransaction),
                ("Ежедневные рекорды", DailyRecord),
                ("Ежедневные проигрыши", DailyLossRecord),
                ("Транзакции переводов", Transaction),
                ("Рефералы", ReferenceUser),
                ("Логи игр рулетки", RouletteGameLog),
                ("Пользователи в чатах", UserChat),
                ("Подарки пользователей", UserGift),
                ("Подарки", Gift),
                ("Чаты", Chat),
                ("Старая таблица пользователей", User),
            ]

            # Очищаем таблицы по порядку
            for table_name, table_model in cleanup_sequence:
                try:
                    count = db.query(table_model).count()
                    if count > 0:
                        db.query(table_model).delete()
                        db.commit()
                        stats[table_name] = count
                        print(f"✅ {table_name}: очищено {count} записей")
                    else:
                        stats[table_name] = 0
                        print(f"ℹ️  {table_name}: уже пустая")
                except Exception as e:
                    db.rollback()
                    print(f"❌ Ошибка очистки {table_name}: {str(e)[:100]}")
                    stats[table_name] = f"Ошибка: {str(e)[:50]}"

            # Особый случай: таблица TelegramUser - очищаем данные но сохраняем структуру
            try:
                print("\n🧹 ОЧИСТКА ПОЛЬЗОВАТЕЛЕЙ...")

                # Получаем всех пользователей
                users_count = db.query(TelegramUser).count()

                if users_count > 0:
                    # Сбрасываем все данные пользователей, но не удаляем записи
                    users = db.query(TelegramUser).all()
                    for user in users:
                        # Сбрасываем балансы и статистику
                        user.coins = 5000  # Начальный баланс
                        user.win_coins = 0
                        user.defeat_coins = 0
                        user.max_win_coins = 0
                        user.min_win_coins = 0
                        user.max_bet = 0
                        user.is_admin = False
                        user.reference_link = None
                        user.robberies_today = 0
                        user.last_robbery_reset = None
                        user.action = None
                        user.duration_minutes = 0

                    db.commit()
                    stats["Пользователи Telegram"] = f"Сброшено {users_count} пользователей"
                    print(f"✅ Пользователи Telegram: сброшены данные {users_count} пользователей")
                else:
                    stats["Пользователи Telegram"] = 0
                    print("ℹ️  Пользователи Telegram: нет пользователей")

            except Exception as e:
                db.rollback()
                print(f"❌ Ошибка очистки пользователей: {e}")
                stats["Пользователи Telegram"] = f"Ошибка: {str(e)[:50]}"

            print("=" * 60)
            print("🎯 ПОЛНАЯ ОЧИСТКА ЗАВЕРШЕНА!")
            print("\n📊 СТАТИСТИКА ОЧИСТКИ:")
            for table_name, count in stats.items():
                print(f"  {table_name}: {count}")

            return True

        except Exception as e:
            print(f"❌ Критическая ошибка при полной очистке: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def cleanup_balances_only():
        """
        Очищает только балансы и статистику, сохраняя остальные данные
        """
        db = SessionLocal()
        try:
            print("💰 НАЧИНАЕТСЯ ОЧИСТКА БАЛАНСОВ И СТАТИСТИКИ...")
            print("=" * 60)

            # Словарь для статистики
            stats = {}

            # 1. Очищаем финансовые таблицы
            financial_tables = [
                ("Транзакции переводов", Transaction),
                ("Транзакции рулетки", RouletteTransaction),
                ("Лимиты переводов", TransferLimit),
                ("Ежедневные рекорды", DailyRecord),
                ("Ежедневные проигрыши", DailyLossRecord),
            ]

            for table_name, table_model in financial_tables:
                try:
                    count = db.query(table_model).count()
                    if count > 0:
                        db.query(table_model).delete()
                        db.commit()
                        stats[table_name] = count
                        print(f"✅ {table_name}: очищено {count} записей")
                    else:
                        stats[table_name] = 0
                        print(f"ℹ️  {table_name}: уже пустая")
                except Exception as e:
                    db.rollback()
                    print(f"❌ Ошибка очистки {table_name}: {str(e)[:100]}")
                    stats[table_name] = f"Ошибка: {str(e)[:50]}"

            # 2. Сбрасываем балансы и статистику пользователей
            try:
                users = db.query(TelegramUser).all()
                users_count = len(users)
                reset_count = 0

                for user in users:
                    # Сбрасываем только финансовые данные
                    user.coins = 5000  # Возвращаем начальный баланс
                    user.win_coins = 0
                    user.defeat_coins = 0
                    user.max_win_coins = 0
                    user.min_win_coins = 0
                    user.max_bet = 0
                    # Не сбрасываем: is_admin, username, reference_link и т.д.
                    reset_count += 1

                db.commit()
                stats["Балансы пользователей"] = f"Сброшено {reset_count} пользователей"
                print(f"✅ Балансы пользователей: сброшены у {reset_count} пользователей")

            except Exception as e:
                db.rollback()
                print(f"❌ Ошибка сброса балансов пользователей: {e}")
                stats["Балансы пользователей"] = f"Ошибка: {str(e)[:50]}"

            # 3. Очищаем старые лимиты (ежедневная очистка)
            try:
                deleted_stats = TransferLimitRepository.clean_daily_old_data(db)
                stats["Старые лимиты"] = deleted_stats
                print(f"✅ Очищены старые лимиты: {deleted_stats}")
            except Exception as e:
                print(f"❌ Ошибка очистки старых лимитов: {e}")
                stats["Старые лимиты"] = f"Ошибка: {str(e)[:50]}"

            print("=" * 60)
            print("💰 ОЧИСТКА БАЛАНСОВ ЗАВЕРШЕНА!")
            print("\n📊 СТАТИСТИКА ОЧИСТКИ:")
            for table_name, count in stats.items():
                print(f"  {table_name}: {count}")

            return True

        except Exception as e:
            print(f"❌ Критическая ошибка при очистке балансов: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def cleanup_transactions_only():
        """
        Очищает только историю транзакций (переводы и рулетку)
        """
        db = SessionLocal()
        try:
            print("📊 НАЧИНАЕТСЯ ОЧИСТКА ИСТОРИИ ТРАНЗАКЦИЙ...")

            stats = {}

            # Очищаем только транзакции
            tables = [
                ("История переводов", Transaction),
                ("История рулетки", RouletteTransaction),
                ("Лимиты переводов", TransferLimit),
            ]

            for table_name, table_model in tables:
                try:
                    count = db.query(table_model).count()
                    if count > 0:
                        db.query(table_model).delete()
                        db.commit()
                        stats[table_name] = count
                        print(f"✅ {table_name}: очищено {count} записей")
                    else:
                        stats[table_name] = 0
                        print(f"ℹ️  {table_name}: уже пустая")
                except Exception as e:
                    db.rollback()
                    print(f"❌ Ошибка очистки {table_name}: {str(e)[:100]}")

            print("📊 ОЧИСТКА ИСТОРИИ ТРАНЗАКЦИЙ ЗАВЕРШЕНА!")
            return stats

        except Exception as e:
            print(f"❌ Ошибка очистки транзакций: {e}")
            db.rollback()
            return {}
        finally:
            db.close()

    @staticmethod
    def cleanup_game_data_only():
        """
        Очищает только игровые данные (рулетка, кражи, браки и т.д.)
        """
        db = SessionLocal()
        try:
            print("🎮 НАЧИНАЕТСЯ ОЧИСТКА ИГРОВЫХ ДАННЫХ...")

            stats = {}

            tables = [
                ("Попытки кражи", StealAttempt),
                ("Аресты вора", ThiefArrest),
                ("Аресты пользователей", UserArrest),
                ("Запросы на развод", DivorceRequest),
                ("Браки", Marriage),
                ("Транзакции рулетки", RouletteTransaction),
                ("Логи игр рулетки", RouletteGameLog),
                ("Лимиты рулетки", RouletteLimit),
            ]

            for table_name, table_model in tables:
                try:
                    count = db.query(table_model).count()
                    if count > 0:
                        db.query(table_model).delete()
                        db.commit()
                        stats[table_name] = count
                        print(f"✅ {table_name}: очищено {count} записей")
                    else:
                        stats[table_name] = 0
                        print(f"ℹ️  {table_name}: уже пустая")
                except Exception as e:
                    db.rollback()
                    print(f"❌ Ошибка очистки {table_name}: {str(e)[:100]}")

            print("🎮 ОЧИСТКА ИГРОВЫХ ДАННЫХ ЗАВЕРШЕНА!")
            return stats

        except Exception as e:
            print(f"❌ Ошибка очистки игровых данных: {e}")
            db.rollback()
            return {}
        finally:
            db.close()

    @staticmethod
    def reset_user_balances_to_default(default_balance: int = 5000):
        """
        Сбрасывает балансы всех пользователей на значение по умолчанию
        """
        db = SessionLocal()
        try:
            print(f"🔄 СБРОС БАЛАНСОВ ПОЛЬЗОВАТЕЛЕЙ НА {default_balance}...")

            users = db.query(TelegramUser).all()
            reset_count = 0

            for user in users:
                user.coins = default_balance
                reset_count += 1

            db.commit()
            print(f"✅ Сброшены балансы {reset_count} пользователей на {default_balance} монет")
            return reset_count

        except Exception as e:
            print(f"❌ Ошибка сброса балансов: {e}")
            db.rollback()
            return 0
        finally:
            db.close()