import asyncio
import logging
import random
import time
import aiosqlite
import datetime
import os
import sys
from typing import Callable, Dict, Any, Awaitable, Union, List, Optional

# Основные импорты aiogram 3.x
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    BotCommand,
    Message,
    ContentType,
    InputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# =================================================================================
# ⚙️ ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ И НАСТРОЙКИ СЕРВЕРА
# =================================================================================
# Токен и ID администратора для управления проектом
TOKEN = "8542233717:AAEfuFgvdkHLRDMshwzWq885r2dECOiYW0s" 
ADMIN_ID = 5394084759
CHANNEL_TAG = "@chaihanabotprom"
DB_NAME = "chaihana_v3.db"

# Рекламный текст, добавляемый к ключевым сообщениям согласно техническому заданию
AD_TEXT = f"\n\n📢 Промокоды, информация и какой-то Даниил Родионов: {CHANNEL_TAG}"

# Настройка расширенного логирования для мониторинга состояния бота на сервере
# Логи сохраняются в файл bot_runtime.log и выводятся в консоль VS Code
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot_runtime.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ChaihanaCore")

# Инициализация объектов Bot и Dispatcher
# Мы используем MemoryStorage для хранения состояний FSM
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# =================================================================================
# 📈 МОДУЛЬ ГЛОБАЛЬНОЙ ЭКОНОМИКИ (ALICOIN MARKET)
# =================================================================================
class Market:
    """
    Класс, отвечающий за симуляцию рыночных отношений.
    Курс AliCoin меняется динамически, создавая игровой азарт.
    """
    price: int = 100
    manual_override: bool = False  # Режим ручной установки курса администратором
    price_history: List[int] = []  # История цен для будущих графиков

    @classmethod
    async def updater(cls):
        """
        Фоновый процесс, который обновляет стоимость валюты каждые 25 секунд.
        Включает в себя логику 'пампов' и 'дампов' рынка.
        """
        logger.info("Market Updater service started.")
        while True:
            try:
                if not cls.manual_override:
                    # Определение типа рыночного события (шанс 100-градусный)
                    event_roll = random.randint(1, 100)
                    
                    if event_roll <= 7: 
                        # Резкое падение (Кризис)
                        cls.price = random.randint(1, 45)
                        logger.warning(f"MARKET EVENT: CRASH! Price dropped to {cls.price}")
                    elif event_roll >= 94: 
                        # Резкий взлет (Буллран)
                        cls.price = random.randint(3800, 5000)
                        logger.info(f"MARKET EVENT: MOON! Price skyrocketed to {cls.price}")
                    else:
                        # Стандартное рыночное колебание
                        volatility = random.randint(-90, 120)
                        cls.price += volatility
                    
                    # Удержание курса в пределах разумного (1 - 5000)
                    cls.price = max(1, min(5000, cls.price))
                    cls.price_history.append(cls.price)
                    
                    # Ограничение размера истории для экономии памяти сервера
                    if len(cls.price_history) > 100:
                        cls.price_history.pop(0)
                
                # Интервал обновления согласно ТЗ
                await asyncio.sleep(25)
            except Exception as e:
                logger.error(f"Critical error in Market Updater: {e}")
                await asyncio.sleep(10)

# =================================================================================
# 🗄️ СИСТЕМА УПРАВЛЕНИЯ БАЗОЙ ДАННЫХ (SQLITE)
# =================================================================================
class DatabaseManager:
    """
    Класс для асинхронного взаимодействия с базой данных aiosqlite.
    Обеспечивает надежное хранение данных пользователей и логов.
    """
    def __init__(self, path: str):
        self.path = path

    async def query(self, sql: str, params: tuple = (), fetch: str = None) -> Any:
        """Выполнение SQL-запроса с автоматическим коммитом."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                if fetch == "one":
                    result = await cursor.fetchone()
                elif fetch == "all":
                    result = await cursor.fetchall()
                else:
                    result = None
                await db.commit()
                return result

    async def initialize_schema(self):
        """Создание необходимых таблиц при первом запуске бота."""
        logger.info("Initializing database schema...")
        
        # Таблица пользователей: хранит баланс, уровни питомцев и КД
        await self.query("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            custom_name TEXT,
            points INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            monkey_lvl INTEGER DEFAULT 0,
            monkey_name TEXT DEFAULT 'Бибизян',
            pig_lvl INTEGER DEFAULT 0,
            pig_name TEXT DEFAULT 'Свин',
            last_chaihana INTEGER DEFAULT 0,
            last_farm_monkey INTEGER DEFAULT 0,
            last_farm_pig INTEGER DEFAULT 0,
            registration_date TEXT
        )""")
        
        # Таблица промокодов
        await self.query("""CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            min_val INTEGER,
            max_val INTEGER,
            activations_count INTEGER DEFAULT 0
        )""")
        
        # Таблица связей 'пользователь - промокод' (защита от мульти-активации)
        await self.query("""CREATE TABLE IF NOT EXISTS promo_history (
            user_id INTEGER,
            code TEXT,
            activated_at TEXT,
            PRIMARY KEY (user_id, code)
        )""")
        
        # Таблица участников чатов для формирования локальных рейтингов
        await self.query("""CREATE TABLE IF NOT EXISTS chat_registry (
            chat_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )""")
        
        # Таблица для системных логов и транзакций
        await self.query("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            type TEXT,
            amount INTEGER,
            ts INTEGER
        )""")
        logger.info("Database schema initialized successfully.")

# Инициализация глобального менеджера БД
db = DatabaseManager(DB_NAME)

# =================================================================================
# 🛡️ MIDDLEWARES (ПРОМЕЖУТОЧНОЕ ПО)
# =================================================================================
class ServerAnalyticsMiddleware(BaseMiddleware):
    """
    Middleware для автоматической регистрации пользователей в БД чата.
    Это исправленная версия, которая вынесена из тела функций для устранения SyntaxError.
    """
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Логика работает только если событие является сообщением от человека
        if isinstance(event, Message) and event.from_user and not event.from_user.is_bot:
            # Если сообщение пришло из группы, записываем связь юзера с чатом
            if event.chat.type in [ContentType.GROUP, "supergroup", "group"]:
                asyncio.create_task(db.query(
                    "INSERT OR IGNORE INTO chat_registry (chat_id, user_id) VALUES (?, ?)",
                    (event.chat.id, event.from_user.id)
                ))
            
            # Логирование активности для отладки на сервере
            logger.debug(f"Input from {event.from_user.id} in {event.chat.id}")
            
        return await handler(event, data)

# Регистрация Middleware в системе
dp.message.middleware(ServerAnalyticsMiddleware())

# =================================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ИНСТРУМЕНТЫ (UTILITIES)
# =================================================================================
def format_currency(value: int) -> str:
    """Форматирует число в читаемый вид: 10000 -> 10.000"""
    return f"{value:,}".replace(",", ".")

async def ensure_user(user_id: int, username: str = None) -> aiosqlite.Row:
    """Проверяет наличие пользователя и создает его при необходимости."""
    user_record = await db.query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch="one")
    
    if not user_record:
        reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.query(
            "INSERT INTO users (user_id, username, registration_date) VALUES (?, ?, ?)",
            (user_id, username or f"user_{user_id}", reg_date)
        )
        return await ensure_user(user_id, username)
    
    # Синхронизация юзернейма при изменении в ТГ
    if username and user_record['username'] != username:
        await db.query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        
    return user_record

async def log_transaction(uid: int, t_type: str, amount: int):
    """Запись финансовых операций в лог-таблицу."""
    await db.query(
        "INSERT INTO transactions (uid, type, amount, ts) VALUES (?, ?, ?, ?)",
        (uid, t_type, amount, int(time.time()))
    )

# =================================================================================
# 💬 ОБРАБОТЧИКИ КОМАНД (COMMAND HANDLERS)
# =================================================================================

@dp.message(Command("start", "help", "помощь"))
async def process_start_command(message: Message, command: CommandObject):
    """Стартовое меню и вывод справочной информации."""
    # Специальный вход для администратора
    if command.args == "admin" and message.from_user.id == ADMIN_ID:
        adm_text = (
            "🛠 <b>ADMIN CONTROL PANEL</b>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "• <code>!рассылка [текст]</code> — Сообщение всем\n"
            "• <code>/addpromo [код] [мин] [макс]</code> — Новый промо\n"
            "• <code>/set [id] [сумма]</code> — Изменить PTS\n"
            "• <code>/set_rate [цена]</code> — Фикс AliCoin\n"
            "• <code>/reset_rate</code> — Включить рынок\n"
            "• <code>/server_info</code> — Статус системы"
        )
        return await message.answer(adm_text, parse_mode="HTML")

    # Регистрация пользователя в БД
    await ensure_user(message.from_user.id, message.from_user.username)
    
    welcome_msg = (
        "👋 <b>Добро пожаловать в Чайхану v3.0!</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "☕️ <code>/chaihana</code> — Получить очки преданности\n"
        "👤 <code>/profile</code> — Твой личный кабинет\n"
        "🏆 <code>/top</code> — Лидеры этого чата\n"
        "🌍 <code>/world</code> — Глобальный топ богачей\n\n"
        "<b>🎮 Игры и Рента:</b>\n"
        "🎰 <code>/casino [ставка]</code> — Испытать удачу\n"
        "⚔️ <code>/duel [ставка]</code> — Вызвать на бой\n"
        "🐒 <code>/monkey</code> — Твой личный майнер\n"
        "🐷 <code>/pig</code> — Ферма очков\n\n"
        "<b>📈 Экономика:</b>\n"
        "💸 <code>/rate</code> — Курс криптовалюты ALI\n"
        "🛒 <code>/buy</code> | <code>/sell</code> — Торговля\n"
        "🎫 <code>/promo [код]</code> — Активация бонусов"
        f"{AD_TEXT}"
    )
    await message.answer(welcome_msg, parse_mode="HTML")

@dp.message(Command("chaihana", "чайхана"))
@dp.message(F.text.lower() == "чайхана")
async def process_chaihana_collect(message: Message):
    """Механика сбора очков раз в 25 минут."""
    user = await ensure_user(message.from_user.id, message.from_user.username)
    current_time = int(time.time())
    cooldown_period = 1500 # Секунды

    if current_time - user['last_chaihana'] < cooldown_period:
        remaining = cooldown_period - (current_time - user['last_chaihana'])
        minutes, seconds = divmod(remaining, 60)
        return await message.answer(
            f"⏳ <b>Чай еще не настоялся!</b>\n"
            f"Подождите еще {minutes} мин. {seconds} сек.{AD_TEXT}",
            parse_mode="HTML"
        )

    # Случайная награда или штраф (игровой момент)
    reward_points = random.randint(-15, 20)
    new_total = user['points'] + reward_points
    
    await db.query(
        "UPDATE users SET points = ?, last_chaihana = ? WHERE user_id = ?",
        (new_total, current_time, message.from_user.id)
    )
    
    status_emoji = "🔥" if reward_points > 10 else "🍃" if reward_points >= 0 else "💀"
    await message.answer(
        f"{status_emoji} <b>Результат посещения:</b>\n"
        f"Вы получили: <b>{reward_points:+d}</b> PTS\n"
        f"Теперь у вас: <b>{format_currency(new_total)}</b> очков!{AD_TEXT}",
        parse_mode="HTML"
    )

@dp.message(Command("profile", "профиль"))
async def process_profile_view(message: Message):
    """Отображение карточки профиля с данными сервера."""
    u = await ensure_user(message.from_user.id, message.from_user.username)
    
    # Расчет места в мире
    rank_query = await db.query(
        "SELECT COUNT(*) as pos FROM users WHERE points > ?",
        (u['points'],), fetch="one"
    )
    global_pos = rank_query['pos'] + 1
    
    # Поиск места в чате (если применимо)
    chat_rank_str = ""
    if message.chat.type in ["group", "supergroup"]:
        c_rank = await db.query("""
            SELECT COUNT(*) as pos FROM users u 
            JOIN chat_registry r ON u.user_id = r.user_id 
            WHERE r.chat_id = ? AND u.points > ?
        """, (message.chat.id, u['points']), fetch="one")
        chat_rank_str = f"🏘 <b>Место в чате:</b> #{c_rank['pos'] + 1}\n"

    name_to_show = u['custom_name'] or u['username'] or "Инкогнито"
    
    profile_text = (
        f"👤 <b>ЛИЧНЫЙ ПРОФИЛЬ</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🆔 <b>UID:</b> <code>{u['user_id']}</code>\n"
        f"🏷 <b>Ник:</b> {name_to_show}\n"
        f"💰 <b>Баланс:</b> {format_currency(u['points'])} PTS\n"
        f"🪙 <b>AliCoin:</b> {format_currency(u['coins'])} ALI\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🌍 <b>Глобальный топ:</b> #{global_pos}\n"
        f"{chat_rank_str}"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🐒 {u['monkey_name']}: {u['monkey_lvl']} ур.\n"
        f"🐷 {u['pig_name']}: {u['pig_lvl']} ур."
        f"{AD_TEXT}"
    )
    
    # Попытка отправить с фото профиля
    try:
        user_pics = await message.from_user.get_profile_photos(limit=1)
        if user_pics.total_count > 0:
            await message.answer_photo(
                user_pics.photos[0][-1].file_id, 
                caption=profile_text, 
                parse_mode="HTML"
            )
        else:
            await message.answer(profile_text, parse_mode="HTML")
    except Exception:
        await message.answer(profile_text, parse_mode="HTML")

@dp.message(Command("name", "ник"))
async def process_name_change(message: Message, command: CommandObject):
    """Смена игрового имени пользователем."""
    if not command.args:
        return await message.answer("📝 <b>Использование:</b> <code>/name [Ваш ник]</code>", parse_mode="HTML")
    
    # Валидация ввода: обрезка лишнего и защита от тегов
    sanitized_name = command.args[:32].replace("<", "&lt;").replace(">", "&gt;").strip()
    
    if len(sanitized_name) < 2:
        return await message.answer("❌ Слишком короткое имя!")

    await db.query("UPDATE users SET custom_name = ? WHERE user_id = ?", (sanitized_name, message.from_user.id))
    await message.answer(f"✅ Имя успешно изменено на: <b>{sanitized_name}</b>{AD_TEXT}", parse_mode="HTML")

# =================================================================================
# 🏆 МОДУЛЬ ТАБЛИЦ ЛИДЕРОВ (RANKINGS)
# =================================================================================
async def build_leaderboard(title: str, users_list: list) -> str:
    """Генератор форматированного текста для топов."""
    board = f"🏆 <b>{title}</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
    if not users_list:
        return board + "<i>Список пока пуст...</i>"
    
    for idx, row in enumerate(users_list, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"<b>{idx}.</b>"
        name = row['custom_name'] or row['username'] or f"ID{row['user_id']}"
        board += f"{medal} {name} — <code>{format_currency(row['points'])}</code>\n"
    
    return board + AD_TEXT

@dp.message(Command("top", "топ"))
async def process_chat_top(message: Message):
    """Вывод 10 богатейших участников текущего чата."""
    if message.chat.type == "private":
        return await message.answer("❌ Данная команда работает только в группах.")
    
    leaders = await db.query("""
        SELECT u.user_id, u.username, u.custom_name, u.points 
        FROM users u
        JOIN chat_registry r ON u.user_id = r.user_id
        WHERE r.chat_id = ?
        ORDER BY u.points DESC LIMIT 10
    """, (message.chat.id,), fetch="all")
    
    text = await build_leaderboard(f"ТОП-10 ЧАТА: {message.chat.title}", leaders)
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("world", "мир"))
async def process_world_top(message: Message):
    """Вывод 10 богатейших участников всего бота."""
    leaders = await db.query(
        "SELECT user_id, username, custom_name, points FROM users ORDER BY points DESC LIMIT 10",
        fetch="all"
    )
    text = await build_leaderboard("ГЛОБАЛЬНЫЙ МИРОВОЙ ТОП", leaders)
    await message.answer(text, parse_mode="HTML")

# =================================================================================
# 🪙 МОДУЛЬ ЭКОНОМИКИ И ТОРГОВЛИ (TRADING)
# =================================================================================
@dp.message(Command("rate", "курс"))
async def process_market_rate(message: Message):
    """Запрос текущего курса валюты."""
    trend_emoji = "📈" if len(Market.price_history) > 1 and Market.price >= Market.price_history[-2] else "📉"
    await message.answer(
        f"📊 <b>БИРЖА ALICOIN</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"Текущая цена: <b>{format_currency(Market.price)}</b> PTS\n"
        f"Тренд: {trend_emoji} <i>(обновляется каждые 25 сек.)</i>\n\n"
        f"Команды: <code>/buy</code>, <code>/sell</code>"
        f"{AD_TEXT}", parse_mode="HTML"
    )

@dp.message(Command("buy", "купить"))
async def process_buy_operation(message: Message, command: CommandObject):
    """Покупка AliCoin."""
    if not command.args:
        return await message.answer("🛒 <b>Укажите количество:</b> <code>/buy [число]</code> или <code>/buy все</code>")
    
    u = await ensure_user(message.from_user.id, message.from_user.username)
    
    if command.args.lower() in ["все", "all", "всё"]:
        amount_to_buy = u['points'] // Market.price
    else:
        try:
            amount_to_buy = int(command.args)
        except ValueError:
            return await message.answer("❌ Ошибка: Введите число.")
            
    if amount_to_buy <= 0:
        return await message.answer("❌ Сумма должна быть больше 0.")
        
    total_cost = amount_to_buy * Market.price
    if u['points'] < total_cost:
        return await message.answer(f"❌ Не хватает очков! Нужно: {format_currency(total_cost)}")
    
    await db.query(
        "UPDATE users SET points = points - ?, coins = coins + ? WHERE user_id = ?",
        (total_cost, amount_to_buy, u['user_id'])
    )
    await log_transaction(u['user_id'], "BUY", amount_to_buy)
    
    await message.answer(
        f"✅ <b>Успешная покупка!</b>\n"
        f"Получено: <b>{amount_to_buy}</b> ALI\n"
        f"Потрачено: <b>{format_currency(total_cost)}</b> PTS{AD_TEXT}",
        parse_mode="HTML"
    )

@dp.message(Command("sell", "продать"))
async def process_sell_operation(message: Message, command: CommandObject):
    """Продажа AliCoin."""
    if not command.args:
        return await message.answer("🛒 <b>Укажите количество:</b> <code>/sell [число]</code> или <code>/sell все</code>")
    
    u = await ensure_user(message.from_user.id, message.from_user.username)
    
    if command.args.lower() in ["все", "all", "всё"]:
        amount_to_sell = u['coins']
    else:
        try:
            amount_to_sell = int(command.args)
        except ValueError:
            return await message.answer("❌ Ошибка: Введите число.")

    if amount_to_sell <= 0 or u['coins'] < amount_to_sell:
        return await message.answer(f"❌ У вас нет столько монет (в наличии: {u['coins']}).")
    
    total_profit = amount_to_sell * Market.price
    await db.query(
        "UPDATE users SET coins = coins - ?, points = points + ? WHERE user_id = ?",
        (amount_to_sell, total_profit, u['user_id'])
    )
    await log_transaction(u['user_id'], "SELL", amount_to_sell)
    
    await message.answer(
        f"✅ <b>Успешная продажа!</b>\n"
        f"Продано: <b>{amount_to_sell}</b> ALI\n"
        f"Выручено: <b>{format_currency(total_profit)}</b> PTS{AD_TEXT}",
        parse_mode="HTML"
    )

@dp.message(Command("transfer", "передать"))
async def process_pts_transfer(message: Message, command: CommandObject):
    """Система перевода очков между игроками."""
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        return await message.answer("❌ Ответьте на сообщение игрока, которому хотите сделать перевод.")
    
    try:
        amount = int(command.args)
    except (ValueError, TypeError):
        return await message.answer("❌ Укажите сумму перевода.")
    
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть положительной.")
    
    sender = await ensure_user(message.from_user.id)
    if sender['points'] < amount:
        return await message.answer("❌ У вас недостаточно очков.")
    
    target_id = message.reply_to_message.from_user.id
    if target_id == message.from_user.id:
        return await message.answer("❌ Нельзя передавать очки самому себе.")
        
    # Выполнение транзакции
    await db.query("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, sender['user_id']))
    await db.query("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, target_id))
    
    receiver_name = message.reply_to_message.from_user.username or f"id{target_id}"
    await message.answer(
        f"💸 <b>Перевод выполнен!</b>\n"
        f"Отправлено: <b>{format_currency(amount)}</b> PTS\n"
        f"Получатель: @{receiver_name}{AD_TEXT}",
        parse_mode="HTML"
    )

# =================================================================================
# 🎲 ИГРОВОЙ МОДУЛЬ (CASINO & DUELS)
# =================================================================================
@dp.message(Command("casino", "казино"))
async def process_casino_bet(message: Message, command: CommandObject):
    """Классическое казино на базе рандома aiogram dice."""
    try:
        bet_value = int(command.args)
    except:
        return await message.answer("🎰 <b>Формат:</b> <code>/casino [ставка]</code>")
    
    u = await ensure_user(message.from_user.id)
    if bet_value > u['points'] or bet_value < 10:
        return await message.answer("❌ Ставка должна быть от 10 PTS и не превышать баланс.")
    
    # Списание ставки
    await db.query("UPDATE users SET points = points - ? WHERE user_id = ?", (bet_value, u['user_id']))
    
    # Анимация автомата
    dice_msg = await message.answer_dice(emoji="🎰")
    await asyncio.sleep(3.5)
    
    score = dice_msg.dice.value
    win_multiplier = 0
    
    # 64 - три семерки, 1, 22, 43 - комбинации из двух или трех символов
    if score == 64: win_multiplier = 10
    elif score in [1, 22, 43]: win_multiplier = 3
    elif score in [16, 32, 48]: win_multiplier = 1.5
    
    if win_multiplier > 0:
        payout = int(bet_value * win_multiplier)
        await db.query("UPDATE users SET points = points + ? WHERE user_id = ?", (payout, u['user_id']))
        await message.reply(f"🔥 <b>ВЫИГРЫШ! x{win_multiplier}</b>\nВы получили: <b>{format_currency(payout)}</b> PTS!")
    else:
        await message.reply(f"📉 <b>Проигрыш.</b>\nСтавка в {format_currency(bet_value)} PTS ушла в доход заведения.")

@dp.message(Command("duel", "дуэль"))
async def process_duel_invite(message: Message, command: CommandObject):
    """Инициализация дуэли между двумя игроками."""
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        return await message.answer("⚔️ Ответьте на сообщение игрока для вызова.")
    
    try:
        bet = int(command.args)
    except:
        return await message.answer("⚔️ <b>Использование:</b> <code>/duel [ставка]</code>")
    
    p1 = await ensure_user(message.from_user.id)
    p2 = await ensure_user(message.reply_to_message.from_user.id)
    
    if p1['points'] < bet or p2['points'] < bet:
        return await message.answer("❌ У кого-то из вас не хватает средств для боя.")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ ПРИНЯТЬ", callback_data=f"dl:ok:{bet}:{p1['user_id']}:{p2['user_id']}")
    kb.button(text="❌ ОТКАЗ", callback_data=f"dl:no:{p1['user_id']}:{p2['user_id']}")
    kb.button(text="🗑 ОТМЕНА", callback_data=f"dl:can:{p1['user_id']}")
    kb.adjust(2, 1)

    await message.answer(
        f"⚔️ <b>ДУЭЛЬ В ЧАЙХАНЕ!</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"👤 <b>Вызывающий:</b> {p1['custom_name'] or p1['username']}\n"
        f"👤 <b>Защитник:</b> {p2['custom_name'] or p2['username']}\n"
        f"💰 <b>Ставка:</b> {format_currency(bet)} PTS\n\n"
        f"<i>Примите вызов, нажав на кнопку ниже!</i>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("dl:"))
async def process_duel_callbacks(call: CallbackQuery):
    """Обработка всех игровых действий в дуэли."""
    parts = call.data.split(":")
    cmd = parts[1]
    
    if cmd == "can":
        if call.from_user.id == int(parts[2]):
            await call.message.edit_text("🗑 Вызов удален инициатором.")
        else:
            await call.answer("Только автор может отменить дуэль!", show_alert=True)
        return

    if cmd == "no":
        if call.from_user.id == int(parts[3]):
            await call.message.edit_text("🚫 Оппонент отказался от поединка.")
        else:
            await call.answer("Это не вам решать!", show_alert=True)
        return
        
    if cmd == "ok":
        stake = int(parts[2])
        id1, id2 = int(parts[3]), int(parts[4])

        if call.from_user.id != id2:
            return await call.answer("Вас не вызывали на этот бой!", show_alert=True)
        
        # Финальная проверка баланса перед боем
        u1 = await ensure_user(id1)
        u2 = await ensure_user(id2)

        if u1['points'] < stake or u2['points'] < stake:
            return await call.message.edit_text("❌ Ошибка: Недостаточно средств для поединка.")

        await call.message.delete()
        announcement = await call.message.answer("🎲 <b>Бросаем кости судьбы...</b>", parse_mode="HTML")
        
        d1 = await call.message.answer_dice()
        d2 = await call.message.answer_dice()
        await asyncio.sleep(4)
        
        res1, res2 = d1.dice.value, d2.dice.value
        
        if res1 == res2:
            await announcement.edit_text(f"🤝 <b>НИЧЬЯ!</b> Оба выкинули {res1}. Очки сохранены.")
        else:
            winner_id = id1 if res1 > res2 else id2
            loser_id = id2 if res1 > res2 else id1
            
            await db.query("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, winner_id))
            await db.query("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, loser_id))
            
            winner_data = u1 if res1 > res2 else u2
            win_name = winner_data['custom_name'] or winner_data['username']
            
            await announcement.edit_text(
                f"⚔️ <b>Битва окончена!</b>\n"
                f"Победитель: <b>{win_name}</b>\n"
                f"Выигрыш: <b>{format_currency(stake)}</b> PTS{AD_TEXT}", 
                parse_mode="HTML"
            )

# =================================================================================
# 🐾 МОДУЛЬ ПИТОМЦЕВ (PETS SYSTEM)
# =================================================================================
@dp.message(Command("monkey", "pig", "бибизян", "свин"))
async def process_pets_menu(message: Message):
    """Единая точка входа для управления питомцами."""
    p_code = "mon" if "monkey" in message.text or "бибизян" in message.text else "pig"
    await show_pet_ui(message, p_code)

async def show_pet_ui(message: Message, p_code: str):
    """Отрисовка интерфейса питомца."""
    u = await ensure_user(message.from_user.id)
    is_mon = (p_code == "mon")
    
    lvl = u['monkey_lvl'] if is_mon else u['pig_lvl']
    name = u['monkey_name'] if is_mon else u['pig_name']
    
    # Ценовая политика улучшений
    base_cost = 8000 if is_mon else 4000
    next_lvl_cost = base_cost + (lvl * 2000)
    limit = 20
    
    kb = InlineKeyboardBuilder()
    if lvl < limit:
        kb.button(text=f"⬆️ Апнуть ({format_currency(next_lvl_cost)})", callback_data=f"pt:up:{p_code}")
    kb.button(text="🚜 Сбор ресурсов", callback_data=f"pt:farm:{p_code}")
    kb.button(text="✏️ Переименовать", callback_data=f"pt:name:{p_code}")
    kb.adjust(1)
    
    job = "Добыча AliCoin" if is_mon else "Сбор очков (PTS)"
    
    await message.answer(
        f"🐾 <b>{name}</b> ({lvl}/{limit} lvl)\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🔧 Специализация: <b>{job}</b>\n"
        f"💰 Цена апа: {format_currency(next_lvl_cost)} PTS\n\n"
        f"<i>Используйте кнопки управления ниже!</i>{AD_TEXT}",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("pt:"))
async def process_pet_callbacks(call: CallbackQuery):
    """Логика кнопок питомца."""
    _, action, p_code = call.data.split(":")
    u = await ensure_user(call.from_user.id)
    is_mon = (p_code == "mon")
    
    lvl_key = "monkey_lvl" if is_mon else "pig_lvl"
    current_lvl = u[lvl_key]

    if action == "name":
        cmd_hint = "/name_monkey" if is_mon else "/name_pig"
        return await call.answer(f"Используйте команду {cmd_hint} [новое имя]", show_alert=True)

    if action == "up":
        if current_lvl >= 20: return await call.answer("Максимальный уровень!", show_alert=True)
        
        base_cost = 8000 if is_mon else 4000
        cost = base_cost + (current_lvl * 2000)
        
        if u['points'] < cost:
            return await call.answer("❌ Недостаточно PTS для прокачки!", show_alert=True)
            
        await db.query(f"UPDATE users SET points = points - ?, {lvl_key} = {lvl_key} + 1 WHERE user_id = ?", (cost, u['user_id']))
        await call.answer("🚀 Уровень повышен!", show_alert=True)
        await call.message.delete()
        await show_pet_ui(call.message, p_code)

    if action == "farm":
        if current_lvl == 0: return await call.answer("Питомец еще ничего не умеет! Апните его.", show_alert=True)
        
        cd_key = "last_farm_monkey" if is_mon else "last_farm_pig"
        cd_time = 1500 
        now_ts = int(time.time())
        
        if now_ts - u[cd_key] < cd_time:
            wait = (cd_time - (now_ts - u[cd_key])) // 60
            return await call.answer(f"💤 Питомец устал. Ждите {wait} мин.", show_alert=True)
            
        if is_mon:
            gain = current_lvl * random.randint(4, 14)
            await db.query(f"UPDATE users SET coins = coins + ?, {cd_key} = ? WHERE user_id = ?", (gain, now_ts, u['user_id']))
            await call.answer(f"🐒 Добыто {gain} AliCoin!", show_alert=True)
        else:
            gain = current_lvl * random.randint(120, 250)
            await db.query(f"UPDATE users SET points = points + ?, {cd_key} = ? WHERE user_id = ?", (gain, now_ts, u['user_id']))
            await call.answer(f"🐷 Собрано {gain} PTS!", show_alert=True)

@dp.message(Command("name_monkey", "name_pig"))
async def process_pet_naming(message: Message, command: CommandObject):
    """Смена имен питомцев."""
    if not command.args: return await message.answer("❌ Введите имя питомца.")
    
    target_pet = "monkey_name" if "monkey" in message.text else "pig_name"
    new_alias = command.args[:20].strip()
    
    await db.query(f"UPDATE users SET {target_pet} = ? WHERE user_id = ?", (new_alias, message.from_user.id))
    await message.answer(f"✅ Питомец успешно переименован в <b>{new_alias}</b>!")

# =================================================================================
# 👮‍♂️ АДМИНИСТРАТИВНЫЙ МОДУЛЬ (SYSTEM ADMIN)
# =================================================================================
@dp.message(F.text.startswith("!рассылка"))
async def admin_broadcast_system(message: Message):
    """Глобальное оповещение всех пользователей (только для ADMIN_ID)."""
    if message.from_user.id != ADMIN_ID: return
    
    raw_text = message.text.replace("!рассылка", "").strip()
    if not raw_text: return
    
    target_list = await db.query("SELECT user_id FROM users", fetch="all")
    delivered, failed = 0, 0
    
    progress = await message.answer(f"⏳ Рассылка запущена ({len(target_list)} чел.)...")
    
    for row in target_list:
        try:
            await bot.send_message(row['user_id'], f"📢 <b>СООБЩЕНИЕ ОТ АДМИНА:</b>\n\n{raw_text}", parse_mode="HTML")
            delivered += 1
            await asyncio.sleep(0.05) # Защита сервера от спам-фильтров ТГ
        except Exception:
            failed += 1
            
    await progress.edit_text(f"🏁 <b>Рассылка завершена!</b>\n✅ Доставлено: {delivered}\n❌ Ошибок: {failed}")

@dp.message(Command("addpromo"))
async def admin_create_promo(message: Message, command: CommandObject):
    """Создание промокода с автоматическим сбросом истории активаций."""
    if message.from_user.id != ADMIN_ID: return
    
    try:
        data = command.args.split()
        p_code = data[0].upper()
        p_min, p_max = int(data[1]), int(data[2])
        
        await db.query(
            "INSERT OR REPLACE INTO promos (code, min_val, max_val) VALUES (?, ?, ?)",
            (p_code, p_min, p_max)
        )
        # Очистка истории для данного кода, чтобы все могли использовать его снова
        await db.query("DELETE FROM promo_history WHERE code = ?", (p_code,))
        
        await message.answer(f"✅ Промокод <code>{p_code}</code> ({p_min}-{p_max}) создан и доступен всем!")
    except:
        await message.answer("❌ Ошибка формата: <code>/addpromo [код] [мин] [макс]</code>")

@dp.message(Command("set"))
async def admin_modify_balance(message: Message, command: CommandObject):
    """Ручная установка баланса (Admin Only)."""
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, val = map(int, command.args.split())
        await db.query("UPDATE users SET points = ? WHERE user_id = ?", (val, uid))
        await message.answer(f"✅ Баланс игрока {uid} изменен на {val}.")
    except:
        await message.answer("❌ Формат: <code>/set [id] [очки]</code>")

@dp.message(Command("set_rate"))
async def admin_fix_rate(message: Message, command: CommandObject):
    """Заморозка курса валюты."""
    if message.from_user.id != ADMIN_ID: return
    try:
        Market.price = int(command.args)
        Market.manual_override = True
        await message.answer(f"✅ Курс зафиксирован: <b>{Market.price}</b>")
    except:
        pass

@dp.message(Command("reset_rate"))
async def admin_unfix_rate(message: Message):
    """Разморозка курса валюты."""
    if message.from_user.id != ADMIN_ID: return
    Market.manual_override = False
    await message.answer("✅ Рынок снова активен!")

@dp.message(Command("server_info"))
async def admin_server_status(message: Message):
    """Вывод системной информации о работе бота на сервере."""
    if message.from_user.id != ADMIN_ID: return
    
    users_total = await db.query("SELECT COUNT(*) as c FROM users", fetch="one")
    points_total = await db.query("SELECT SUM(points) as s FROM users", fetch="one")
    
    uptime_text = (
        "🖥 <b>SERVER STATUS INFO</b>\n"
        f"👥 Пользователей: {users_total['c']}\n"
        f"💰 Эмиссия PTS: {format_currency(points_total['s'] or 0)}\n"
        f"📊 Текущая цена ALI: {Market.price}\n"
        f"🛠 Режим рынка: {'Ручной' if Market.manual_override else 'Авто'}\n"
        f"📅 Время сервера: {datetime.datetime.now().strftime('%H:%M:%S')}"
    )
    await message.answer(uptime_text, parse_mode="HTML")

@dp.message(Command("promo", "промо"))
async def process_promo_activation(message: Message, command: CommandObject):
    """Механика активации промокода."""
    if not command.args: 
        return await message.answer("🎫 <b>Использование:</b> <code>/promo [код]</code>")
    
    code_input = command.args.strip().upper()
    promo_data = await db.query("SELECT * FROM promos WHERE code = ?", (code_input,), fetch="one")
    
    if not promo_data:
        return await message.answer("❌ Такого промокода не существует.")
        
    already_used = await db.query(
        "SELECT * FROM promo_history WHERE user_id = ? AND code = ?",
        (message.from_user.id, code_input), fetch="one"
    )
    
    if already_used:
        return await message.answer("❌ Вы уже активировали этот промокод!")
    
    reward = random.randint(promo_data['min_val'], promo_data['max_val'])
    
    await db.query(
        "INSERT INTO promo_history (user_id, code, activated_at) VALUES (?, ?, ?)",
        (message.from_user.id, code_input, datetime.datetime.now().isoformat())
    )
    await db.query("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, message.from_user.id))
    
    await message.answer(f"🎁 <b>Успех!</b>\nВам начислено: <b>{format_currency(reward)}</b> PTS!{AD_TEXT}", parse_mode="HTML")

# =================================================================================
# 🚀 ЗАПУСК ЯДРА СИСТЕМЫ (BOOTSTRAP)
# =================================================================================
async def main_engine():
    """Главная функция инициализации и запуска всех сервисов."""
    logger.info("Starting Chaihana Bot v3.0 core...")
    
    # 1. Инициализация Базы Данных
    await db.initialize_schema()
    
    # 2. Настройка команд меню Telegram
    await bot.set_my_commands([
        BotCommand(command="chaihana", description="Получить очки коллектива"),
        BotCommand(command="profile", description="Мои данные и баланс"),
        BotCommand(command="top", description="Топ 10 участников чата"),
        BotCommand(command="world", description="Топ 10 всего мира"),
        BotCommand(command="rate", description="Текущий курс AliCoin"),
        BotCommand(command="help", description="Список всех возможностей"),
    ])
    
    # 3. Запуск фонового сервиса рынка
    asyncio.create_task(Market.updater())
    
    # 4. Запуск Long Polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot engine is online and ready for processing.")
    
    try:
        await dp.start_polling(bot)
    except Exception as fatal:
        logger.critical(f"FATAL ERROR DURING RUNTIME: {fatal}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    # Установка корректного цикла событий для серверов
    try:
        asyncio.run(main_engine())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot engine stopped by administrator.")
