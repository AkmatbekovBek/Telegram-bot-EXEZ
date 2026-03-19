# 🎰 RouletteBotTelegram — @gameexez_bot

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/aiogram-2.25.1-orange?style=for-the-badge&logo=telegram" />
  <img src="https://img.shields.io/badge/PostgreSQL-Shared-336791?style=for-the-badge&logo=postgresql" />
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-red?style=for-the-badge" />
</p>

> **Уникальный игровой эко-бот для Telegram.** Сочетает в себе азартные игры, ролевую модель (RP) и продвинутую систему администрирования сообществ.

---

## 🎮 Основные игровые механики

### 🎲 Азарт и Казино
* **Advanced Roulette** — система ставок на числа, цвета и сектора с защитой от сбоев.
* **Slot Machine** — классические игровые автоматы.
* **PvP Игры** — кости и "Камень-Ножницы-Бумага" напрямую между игроками.
* **Raffles** — автоматизированная система розыгрышей внутри чата.

### 🎭 Ролевые взаимодействия (RP)
* **Police vs Thief** — игроки могут грабить друг друга или производить аресты.
* **Система Браков** — регистрация союзов в локальной базе чата.
* **Магазин Подарков** — покупка и передача уникальных предметов другим юзерам.

### 💰 Экономика и Донат
* Гибкая система валюты (монеты).
* Реферальная программа с бонусами за приглашение участников.
* Поддержка VIP-статусов, кастомных ников и расширенных лимитов через донат-систему.

---

## 🛠 Технологический стек

| Компонент | Технология |
| :--- | :--- |
| **Core** | `Python 3.11` + `asyncio` |
| **Framework** | `Aiogram 2.25` |
| **Database** | `PostgreSQL` / `SQLite` |
| **ORM** | `SQLAlchemy 2.0` |
| **Migrations** | `Alembic` |
| **Config** | `python-decouple` (.env) |

---

⚙️ Быстрый запуск
Подготовка окружения:

Bash
git clone [https://github.com/AkmatbekovBek/RouletteBotTelegram.git](https://github.com/AkmatbekovBek/RouletteBotTelegram.git)
cd RouletteBotTelegram
python -m venv venv
source venv/bin/activate # Windows: venv\Scripts\activate
pip install -r requirements.txt
Настройка констант (.env):
Создайте файл .env и заполните данные:

Фрагмент кода
TGBOTtoken="123456:ABC-DEF..."
DATABASE_URL="postgresql://user:pass@localhost/dbname"
Инициализация БД:

Bash
alembic upgrade head
Запуск:

Bash
python main.py
<p align="center">
<b>Developed by Akmatbekov Bek</b>


<i>Проект создан для демонстрации навыков асинхронного программирования и работы с БД</i>
</p>

---

## 📂 Архитектура проекта
```bash
├── 📁 alembic/          # Миграции базы данных
├── 📁 database/         # Модели SQLAlchemy и сессии
├── 📁 handlers/         # Модульная логика (Games, RP, Admin)
├── 📁 keyboards/        # Сборка Inline/Reply меню
├── 📁 middlewares/      # Антиспам (Throttling) и Авторегистрация
├── 📄 main.py           # Точка входа и запуск бота
└── 📄 config.py         # Загрузка настроек окружения
