import asyncio
import logging
import random
import time
import aiosqlite
import json
from typing import Callable, Dict, Any, Awaitable, List, Optional, Union

# Импортируем необходимые компоненты aiogram
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    BotCommand, 
    Message,
    BufferedInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ⚙️ ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ СИСТЕМЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
TOKEN = "8542233717:AAEfuFgvdkHLRDMshwzWq885r2dECOiYW0s" 
ADMIN_ID = 5394084759
CHANNEL_TAG = "@chaihanabotprom"
DB_NAME = "chaihana_v3.db"

# Рекламный текст для подписей (согласно ТЗ)
AD_TEXT = f"\n\n📢 Промокоды, информация и какой-то Даниил Родионов: {CHANNEL_TAG}"

# Настройка детализированного логирования для мониторинга в VS Code
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_debug.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ChaihanaBot")

# Инициализация ключевых объектов бота
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# 📉 СИСТЕМА ГЛОБАЛЬНОЙ ЭКОНОМИКИ (ALICOIN)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
class Market:
    """Класс управления рыночными котировками AliCoin."""
    price = 100
    manual_override = False # Флаг ручного управления курсом
    history: List[int] = [100] # История последних изменений для графиков (в будущем)

    @classmethod
    async def updater(cls):
        """Асинхронный цикл обновления курса каждые 25 секунд."""
        while True:
            try:
                if not cls.manual_override:
                    # Генерация случайного рыночного события
                    event = random.randint(1, 100)
                    
                    if event <= 5: 
                        # Резкий обвал курса (Дамп)
                        cls.price = random.randint(1, 40)
                        logger.warning(f"MARKET CRASH! New price: {cls.price}")
                    elif event >= 96: 
                        # Резкий взлет (Тузэмун)
                        cls.price = random.randint(3500, 5000)
                        logger.warning(f"MARKET PUMP! New price: {cls.price}")
                    else:
                        # Стандартная волатильность
                        change = random.randint(-80, 110)
                        cls.price += change
                    
                    # Жесткие границы курса (от 1 до 5000 очков за монету)
                    cls.price = max(1, min(5000, cls.price))
                    cls.history.append(cls.price)
                    if len(cls.history) > 50: cls.history.pop(0)
                
                await asyncio.sleep(25)
            except Exception as e:
                logger.error(f"Error in Market Updater: {e}")
                await asyncio.sleep(5)

# 🛠 МЕНЕДЖЕР БАЗЫ ДАННЫХ (AIOSQLITE)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
class Database:
    """Обертка над SQLite для асинхронной работы с данными."""
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def execute(self, sql: str, params: tuple = (), fetch: Optional[str] = None):
        """Универсальный метод выполнения SQL запросов."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                cursor = await db.execute(sql, params)
                data = None
                if fetch == "one":
                    data = await cursor.fetchone()
                elif fetch == "all":
                    data = await cursor.fetchall()
                await db.commit()
                return data
            except Exception as e:
                logger.error(f"Database Error: {e} | SQL: {sql}")
                return None

    async def init_tables(self):
        """Инициализация структуры таблиц при запуске."""
        # Основная таблица пользователей
        await self.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            custom_name TEXT,
            points INTEGER DEFAULT 100,
            coins INTEGER DEFAULT 0,
            monkey_lvl INTEGER DEFAULT 0,
            monkey_name TEXT DEFAULT 'Бибизян',
            pig_lvl INTEGER DEFAULT 0,
            pig_name TEXT DEFAULT 'Свин',
            last_chaihana INTEGER DEFAULT 0,
            last_farm_monkey INTEGER DEFAULT 0,
            last_farm_pig INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0
        )""")
        
        # Таблица управления промокодами
        await self.execute("""CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            min_val INTEGER,
            max_val INTEGER,
            activations INTEGER DEFAULT 0
        )""")
        
        # Реестр активаций для предотвращения повторного ввода
        await self.execute("""CREATE TABLE IF NOT EXISTS used_promos (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )""")
        
        # Привязка пользователей к группам для локальных топов
        await self.execute("""CREATE TABLE IF NOT EXISTS chat_members (
            chat_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )""")
        
        # Лог транзакций для безопасности
        await self.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            amount INTEGER,
            timestamp INTEGER
        )""")

# Создаем экземпляр БД
db = Database(DB_NAME)

# 🛠 СИСТЕМНЫЕ MIDDLEWARES
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
class ChatTrackerMiddleware(BaseMiddleware):
    """Отслеживает активность пользователей в группах для формирования топов чата."""
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Работаем только с текстовыми сообщениями в группах
        if isinstance(event, Message) and event.from_user:
            if event.chat.type in ["group", "supergroup"]:
                # Фоновая задача записи участника
                asyncio.create_task(db.execute(
                    "INSERT OR IGNORE INTO chat_members (chat_id, user_id) VALUES (?, ?)", 
                    (event.chat.id, event.from_user.id)
                ))
        return await handler(event, data)

# Регистрация Middleware в диспетчере (ВАЖНО: вне обработчиков!)
dp.message.middleware(ChatTrackerMiddleware())

# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (УТИЛИТЫ)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
def fmt(num: int) -> str:
    """Красивое форматирование чисел с разделением тысяч."""
    return f"{num:,}".replace(",", ".")

async def get_user(user_id: int, username: Optional[str] = None) -> aiosqlite.Row:
    """Получение или создание профиля пользователя."""
    user = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch="one")
    if not user:
        await db.execute(
            "INSERT INTO users (user_id, username) VALUES (?, ?)", 
            (user_id, username if username else f"id{user_id}")
        )
        return await get_user(user_id, username)
    
    # Обновление юзернейма, если он изменился в Telegram
    if username and user['username'] != username:
         await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    return user

async def get_global_rank(user_id: int) -> int:
    """Вычисление позиции пользователя в мировом рейтинге."""
    res = await db.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE points > (SELECT points FROM users WHERE user_id = ?)", 
        (user_id,), fetch="one"
    )
    return res['cnt'] + 1 if res else 1

async def add_log(user_id: int, action: str, amount: int):
    """Логирование важных действий пользователя."""
    await db.execute(
        "INSERT INTO logs (user_id, action, amount, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, action, amount, int(time.time()))
    )

# 🎮 ОБРАБОТЧИКИ ОСНОВНЫХ КОМАНД
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬

@dp.message(Command("start", "help", "помощь"))
async def cmd_start(message: Message, command: CommandObject):
    """Приветственное сообщение и вывод списка команд."""
    # Обработка входа в админ-панель
    if command.args == "admin" and message.from_user.id == ADMIN_ID:
        admin_panel = (
            "👮‍♂️ <b>Панель управления администратора:</b>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "▫️ <code>!рассылка [текст]</code> — Глобальное оповещение\n"
            "▫️ <code>/addpromo [код] [min] [max]</code> — Создать промокод\n"
            "▫️ <code>/set [id] [очки]</code> — Изменить баланс\n"
            "▫️ <code>/set_rate [цена]</code> — Фиксация курса AliCoin\n"
            "▫️ <code>/reset_rate</code> — Включить волатильность рынка\n"
            "▫️ <code>/stats</code> — Техническая статистика бота"
        )
        return await message.answer(admin_panel, parse_mode="HTML")

    await get_user(message.from_user.id, message.from_user.username)
    
    help_text = (
        "🤖 <b>Чайхана Бот v3.5 (Stable Release)</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "☕ <b>Основные активности:</b>\n"
        "▫️ <code>/chaihana</code> — Заварить чай (получить очки)\n"
        "▫️ <code>/profile</code> — Информация о твоем аккаунте\n"
        "▫️ <code>/name [имя]</code> — Установить личный никнейм\n\n"
        "🏆 <b>Соревнования и топы:</b>\n"
        "▫️ <code>/top</code> — Рейтинг активных участников чата\n"
        "▫️ <code>/world</code> — Список самых богатых в мире\n\n"
        "🎲 <b>Азартные игры:</b>\n"
        "▫️ <code>/casino [ставка]</code> — Испытать удачу в автоматах\n"
        "▫️ <code>/duel [ставка]</code> — Вызвать игрока на бой костей\n\n"
        "💰 <b>Финансовая система:</b>\n"
        "▫️ <code>/rate</code> — Актуальный курс AliCoin\n"
        "▫️ <code>/buy [кол-во]</code> — Купить крипту\n"
        "▫️ <code>/sell [кол-во]</code> — Продать крипту\n"
        "▫️ <code>/transfer [сумма]</code> — Перевод игроку\n\n"
        "🐾 <b>Личная ферма:</b>\n"
        "▫️ <code>/monkey</code> — Твой Бибизян (майнит монеты)\n"
        "▫️ <code>/pig</code> — Твой Свин (добывает очки)\n\n"
        "🎫 <b>Бонусы:</b>\n"
        "▫️ <code>/promo [код]</code> — Активировать секретный промо"
        f"{AD_TEXT}"
    )
    await message.answer(help_text, parse_mode="HTML")

@dp.message(Command("chaihana", "чайхана"))
@dp.message(F.text.lower() == "чайхана")
async def cmd_chaihana(message: Message):
    """Механика получения очков с КД."""
    user = await get_user(message.from_user.id, message.from_user.username)
    now = int(time.time())
    cooldown = 1500  # 25 минут

    if now - user['last_chaihana'] < cooldown:
        wait = int(cooldown - (now - user['last_chaihana']))
        m, s = divmod(wait, 60)
        return await message.answer(
            f"⏳ <b>Чай еще заваривается!</b>\n"
            f"Приходи через: <b>{m} мин. {s} сек.</b>"
            f"{AD_TEXT}", parse_mode="HTML"
        )

    # Генерация случайного количества очков (от -10 до 15)
    delta = random.randint(-10, 15)
    new_points = user['points'] + delta
    
    await db.execute(
        "UPDATE users SET points = ?, last_chaihana = ? WHERE user_id = ?", 
        (new_points, now, message.from_user.id)
    )
    
    emoji = "🍵" if delta > 0 else "💨"
    status = "очень вкусный!" if delta > 5 else "горький..." if delta < 0 else "обычный чай."
    
    await message.answer(
        f"{emoji} <b>Чайхана:</b>\n"
        f"Чай получился {status}\n"
        f"Твой результат: <b>{delta:+d}</b> очков преданности!{AD_TEXT}", 
        parse_mode="HTML"
    )

@dp.message(Command("profile", "профиль"))
async def cmd_profile(message: Message):
    """Детальный вывод данных профиля с поддержкой фото."""
    u = await get_user(message.from_user.id, message.from_user.username)
    g_rank = await get_global_rank(u['user_id'])
    
    # Сбор данных о ранге в конкретном чате
    c_rank_text = ""
    if message.chat.type in ["group", "supergroup"]:
        res = await db.execute("""
            SELECT COUNT(*) as cnt FROM users u
            JOIN chat_members cm ON u.user_id = cm.user_id
            WHERE cm.chat_id = ? AND u.points > ?
        """, (message.chat.id, u['points']), fetch="one")
        c_rank = res['cnt'] + 1 if res else 1
        c_rank_text = f"🏘 <b>Место в этом чате:</b> #{c_rank}\n"

    name = u['custom_name'] or u['username'] or "Неизвестный странник"
    
    profile_card = (
        f"👤 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🆔 <b>ID:</b> <code>{u['user_id']}</code>\n"
        f"🏷 <b>Имя:</b> {name}\n"
        f"🏆 <b>Очки (PTS):</b> {fmt(u['points'])}\n"
        f"🪙 <b>AliCoin:</b> {fmt(u['coins'])}\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🌍 <b>Глобальный ранг:</b> #{g_rank}\n"
        f"{c_rank_text}"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🐒 <b>{u['monkey_name']}:</b> {u['monkey_lvl']} LVL\n"
        f"🐷 <b>{u['pig_name']}:</b> {u['pig_lvl']} LVL"
        f"{AD_TEXT}"
    )
    
    try:
        # Пытаемся получить аватарку
        photos = await message.from_user.get_profile_photos(limit=1)
        if photos.total_count > 0:
            await message.answer_photo(
                photos.photos[0][-1].file_id, 
                caption=profile_card, 
                parse_mode="HTML"
            )
        else:
            await message.answer(profile_card, parse_mode="HTML")
    except Exception as e:
        logger.debug(f"Failed to send profile photo: {e}")
        await message.answer(profile_card, parse_mode="HTML")

@dp.message(Command("name", "ник"))
async def cmd_name(message: Message, command: CommandObject):
    """Смена отображаемого имени пользователя."""
    if not command.args:
        return await message.answer("✏️ <b>Использование:</b> <code>/name [ваше имя]</code>", parse_mode="HTML")
    
    # Очистка от HTML тегов и ограничение длины
    new_name = command.args[:25].replace("<","").replace(">","").strip()
    if len(new_name) < 2:
        return await message.answer("❌ Слишком короткое имя!")

    await db.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (new_name, message.from_user.id))
    await message.answer(f"✅ <b>Успешно!</b> Теперь тебя зовут: <b>{new_name}</b>{AD_TEXT}", parse_mode="HTML")

# 📊 СИСТЕМА РЕЙТИНГОВ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def render_top_list(title: str, users_data: list) -> str:
    """Генератор текста для списков лидеров."""
    header = f"🏆 <b>{title}</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
    if not users_data:
        return header + "<i>В этом списке пока нет участников...</i>"
    
    rows = []
    for i, user in enumerate(users_data, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        display_name = user['custom_name'] or user['username'] or "Аноним"
        rows.append(f"{medal} <b>{display_name}</b> — <code>{fmt(user['points'])}</code> pts")
    
    return header + "\n".join(rows) + AD_TEXT

@dp.message(Command("top", "топ"))
async def cmd_chat_top(message: Message):
    """Топ-10 участников текущей группы."""
    if message.chat.type == "private":
        return await message.answer("❌ Топ чата доступен только в групповых беседах. Используй <code>/world</code>.")
    
    top_users = await db.execute("""
        SELECT u.* FROM users u
        JOIN chat_members cm ON u.user_id = cm.user_id
        WHERE cm.chat_id = ?
        ORDER BY u.points DESC LIMIT 10
    """, (message.chat.id,), fetch="all")
    
    content = await render_top_list(f"ТОП-10 ЧАТА: {message.chat.title}", top_users)
    await message.answer(content, parse_mode="HTML")

@dp.message(Command("world", "мир"))
async def cmd_world_top(message: Message):
    """Топ-10 самых богатых пользователей по всему боту."""
    global_users = await db.execute("SELECT * FROM users ORDER BY points DESC LIMIT 10", fetch="all")
    content = await render_top_list("МИРОВОЙ РЕЙТИНГ БОГАТЕЕВ", global_users)
    await message.answer(content, parse_mode="HTML")

# 💸 МОДУЛЬ ЭКОНОМИКИ И ТОРГОВЛИ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("rate", "курс"))
async def cmd_rate(message: Message):
    """Вывод текущего курса AliCoin."""
    trend = "📈 Рост" if len(Market.history) > 1 and Market.price > Market.history[-2] else "📉 Падение"
    await message.answer(
        f"📊 <b>КУРС ALICOIN (ALI)</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"Текущая цена: <b>{fmt(Market.price)}</b> PTS\n"
        f"Тренд: <i>{trend}</i>\n\n"
        f"💡 Обновление происходит каждые 25 секунд. Используй <code>/buy</code> или <code>/sell</code> для сделок."
        f"{AD_TEXT}", parse_mode="HTML"
    )

@dp.message(Command("buy", "купить"))
async def cmd_buy(message: Message, command: CommandObject):
    """Покупка AliCoin за очки."""
    if not command.args:
        return await message.answer("🛒 <b>Использование:</b> <code>/buy [число]</code> или <code>/buy все</code>", parse_mode="HTML")
    
    u = await get_user(message.from_user.id)
    
    if command.args.lower() in ['все', 'all', 'всё']:
        amount = u['points'] // Market.price
    else:
        try:
            amount = int(command.args)
        except ValueError:
            return await message.answer("❌ Введи корректное число.")
    
    if amount <= 0: return await message.answer("❌ Сумма должна быть больше 0.")
    
    total_cost = amount * Market.price
    if u['points'] < total_cost:
        return await message.answer(f"❌ Недостаточно очков! Нужно: <b>{fmt(total_cost)}</b>, у тебя: <b>{fmt(u['points'])}</b>")
    
    await db.execute(
        "UPDATE users SET points = points - ?, coins = coins + ? WHERE user_id = ?", 
        (total_cost, amount, u['user_id'])
    )
    await add_log(u['user_id'], "buy_coin", amount)
    
    await message.answer(
        f"✅ <b>Сделка успешна!</b>\n"
        f"Вы купили: <b>{fmt(amount)}</b> ALI\n"
        f"Списано: <b>{fmt(total_cost)}</b> очков."
        f"{AD_TEXT}", parse_mode="HTML"
    )

@dp.message(Command("sell", "продать"))
async def cmd_sell(message: Message, command: CommandObject):
    """Продажа AliCoin за очки."""
    if not command.args:
        return await message.answer("🛒 <b>Использование:</b> <code>/sell [число]</code> или <code>/sell все</code>", parse_mode="HTML")
    
    u = await get_user(message.from_user.id)
    
    if command.args.lower() in ['все', 'all', 'всё']:
        amount = u['coins']
    else:
        try:
            amount = int(command.args)
        except ValueError:
            return await message.answer("❌ Введи корректное число.")

    if amount <= 0 or u['coins'] < amount:
        return await message.answer(f"❌ У тебя нет такого количества монет (доступно: {u['coins']}).")
    
    total_income = amount * Market.price
    await db.execute(
        "UPDATE users SET coins = coins - ?, points = points + ? WHERE user_id = ?", 
        (amount, total_income, u['user_id'])
    )
    await add_log(u['user_id'], "sell_coin", amount)
    
    await message.answer(
        f"✅ <b>Монеты проданы!</b>\n"
        f"Вы продали: <b>{fmt(amount)}</b> ALI\n"
        f"Получено: <b>{fmt(total_income)}</b> очков."
        f"{AD_TEXT}", parse_mode="HTML"
    )

@dp.message(Command("transfer", "передать"))
async def cmd_transfer(message: Message, command: CommandObject):
    """Передача очков другому пользователю."""
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        return await message.answer("❌ Ответь на сообщение того, кому хочешь передать очки.")
    
    try:
        val = int(command.args)
    except (ValueError, TypeError):
        return await message.answer("❌ Укажи сумму: <code>/transfer [сумма]</code>")
    
    if val <= 0: return await message.answer("❌ Сумма должна быть положительной.")
    
    sender = await get_user(message.from_user.id)
    if sender['points'] < val:
        return await message.answer("❌ У тебя нет столько очков.")
    
    target_id = message.reply_to_message.from_user.id
    if target_id == message.from_user.id:
        return await message.answer("❌ Нельзя передавать очки самому себе.")
        
    receiver = await get_user(target_id, message.reply_to_message.from_user.username)
    
    await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (val, sender['user_id']))
    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (val, target_id))
    
    await message.answer(
        f"💸 <b>Перевод выполнен!</b>\n"
        f"Отправлено: <b>{fmt(val)}</b> очков\n"
        f"Получатель: {receiver['custom_name'] or receiver['username']}"
        f"{AD_TEXT}", parse_mode="HTML"
    )

# 🎰 ИГРОВОЙ МОДУЛЬ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("casino", "казино"))
async def cmd_casino(message: Message, command: CommandObject):
    """Виртуальное казино на базе dice."""
    try:
        bet = int(command.args)
    except:
        return await message.answer("🎰 <b>Формат:</b> <code>/casino [ставка]</code>", parse_mode="HTML")
    
    u = await get_user(message.from_user.id)
    if bet > u['points'] or bet < 10:
        return await message.answer("❌ Минимальная ставка 10 очков и не больше вашего баланса.")
    
    # Резервируем ставку
    await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (bet, u['user_id']))
    
    # Эффект ожидания
    msg = await message.answer_dice(emoji="🎰")
    await asyncio.sleep(3.0)
    
    result_val = msg.dice.value
    # Логика выигрыша (64 - три семерки, 1/22/43 - другие комбинации)
    multiplier = 0
    if result_val == 64: multiplier = 10
    elif result_val in [1, 22, 43]: multiplier = 3
    elif result_val in [16, 32, 48]: multiplier = 1.5
    
    if multiplier > 0:
        win_sum = int(bet * multiplier)
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win_sum, u['user_id']))
        await message.reply(f"🎰 <b>ПОБЕДА!</b>\nКоэффициент: <b>x{multiplier}</b>\nВыигрыш: <b>{fmt(win_sum)}</b> PTS!")
    else:
        await message.reply(f"📉 <b>Проигрыш...</b>\nВы потеряли <b>{fmt(bet)}</b> очков. Повезет в следующий раз!")

@dp.message(Command("duel", "дуэль"))
async def cmd_duel(message: Message, command: CommandObject):
    """Вызов на дуэль другого игрока."""
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        return await message.answer("⚔️ <b>Дуэль:</b> Ответь на сообщение игрока, чтобы вызвать его.")
    
    try:
        bet = int(command.args)
    except:
        return await message.answer("⚔️ <b>Использование:</b> <code>/duel [ставка]</code>", parse_mode="HTML")
    
    p1_id = message.from_user.id
    p2_id = message.reply_to_message.from_user.id
    
    if p1_id == p2_id: return await message.answer("❌ Нельзя воевать с тенью (самим собой).")
    
    u1 = await get_user(p1_id)
    u2 = await get_user(p2_id)
    
    if u1['points'] < bet or u2['points'] < bet:
        return await message.answer("❌ У одного из участников недостаточно очков для такой ставки.")

    builder = InlineKeyboardBuilder()
    builder.button(text="🛡 ПРИНЯТЬ", callback_data=f"duel:accept:{bet}:{p1_id}:{p2_id}")
    builder.button(text="🏳️ ОТКАЗАТЬСЯ", callback_data=f"duel:decline:{p1_id}:{p2_id}")
    builder.button(text="❌ ОТМЕНА", callback_data=f"duel:cancel:{p1_id}")
    builder.adjust(2, 1)

    p1_name = u1['custom_name'] or u1['username']
    p2_name = u2['custom_name'] or u2['username']
    
    await message.answer(
        f"⚔️ <b>ВЫЗОВ НА ДУЭЛЬ!</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"👤 <b>Инициатор:</b> {p1_name}\n"
        f"👤 <b>Соперник:</b> {p2_name}\n"
        f"💰 <b>Ставка:</b> {fmt(bet)} очков\n\n"
        f"<i>Ждем решения оппонента...</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("duel:"))
async def duel_callback_handler(call: CallbackQuery):
    """Обработка кнопок дуэли."""
    parts = call.data.split(":")
    action = parts[1]
    
    # Логика отмены вызова
    if action == "cancel":
        if call.from_user.id == int(parts[2]):
            await call.message.edit_text("🗑 Вызов аннулирован автором.")
        else:
            await call.answer("Это не твой вызов!", show_alert=True)
        return

    # Логика отказа
    if action == "decline":
        p2_id = int(parts[3])
        if call.from_user.id == p2_id:
            await call.message.edit_text("🏳️ Оппонент струсил и отказался от боя.")
        else:
            await call.answer("Это должен решить тот, кого вызвали!", show_alert=True)
        return
        
    # Логика принятия боя
    if action == "accept":
        bet = int(parts[2])
        p1_id = int(parts[3])
        p2_id = int(parts[4])

        if call.from_user.id != p2_id:
            return await call.answer("Тебя не приглашали в этот бой!", show_alert=True)
        
        # Финальная проверка баланса
        u1 = await get_user(p1_id)
        u2 = await get_user(p2_id)

        if u1['points'] < bet or u2['points'] < bet:
            return await call.message.edit_text("❌ Бой отменен: недостаточно средств на балансе.")

        # Процесс битвы
        await call.message.edit_text("🎲 <b>БИТВА НАЧАЛАСЬ! Бросаем кости...</b>", parse_mode="HTML")
        
        # Анимация кубиков
        d1 = await call.message.answer_dice(emoji="🎲")
        d2 = await call.message.answer_dice(emoji="🎲")
        await asyncio.sleep(4.5)
        
        v1, v2 = d1.dice.value, d2.dice.value
        
        if v1 == v2:
            await call.message.answer(f"🤝 <b>НИЧЬЯ!</b> Выброшено по {v1}. Очки остаются при владельцах.")
        else:
            if v1 > v2:
                winner_id, loser_id = p1_id, p2_id
                win_name = u1['custom_name'] or u1['username']
            else:
                winner_id, loser_id = p2_id, p1_id
                win_name = u2['custom_name'] or u2['username']
            
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (bet, winner_id))
            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (bet, loser_id))
            
            await call.message.answer(
                f"⚔️ <b>ИТОГИ ДУЭЛИ:</b>\n"
                f"Победитель: <b>{win_name}</b>\n"
                f"Приз: <b>{fmt(bet)}</b> очков!{AD_TEXT}", 
                parse_mode="HTML"
            )

# 🐾 МОДУЛЬ ФЕРМЫ (ПИТОМЦЫ)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("monkey", "pig", "бибизян", "свин"))
async def cmd_pets_main(message: Message):
    """Общий вход в систему питомцев."""
    p_type = "mon" if "monkey" in message.text or "бибиз" in message.text else "pig"
    await render_pet_interface(message, p_type)

async def render_pet_interface(message: Message, p_type: str):
    """Отрисовка меню питомца."""
    u = await get_user(message.from_user.id)
    is_mon = (p_type == "mon")
    
    lvl = u['monkey_lvl'] if is_mon else u['pig_lvl']
    name = u['monkey_name'] if is_mon else u['pig_name']
    
    # Математика улучшений
    price_base = 7500 if is_mon else 3500
    price = price_base + (lvl * 1750)
    max_lvl = 15
    
    builder = InlineKeyboardBuilder()
    if lvl < max_lvl:
        builder.button(text=f"⬆️ Улучшить ({fmt(price)})", callback_data=f"pet:up:{p_type}")
    
    builder.button(text="⛏ Сбор ресурсов", callback_data=f"pet:work:{p_type}")
    builder.button(text="✏️ Переименовать", callback_data=f"pet:rename:{p_type}")
    builder.adjust(1)
    
    spec = "Добывает AliCoin" if is_mon else "Генерирует PTS"
    
    await message.answer(
        f"🐾 <b>ВАШ ПИТОМЕЦ: {name}</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"📈 <b>Уровень:</b> {lvl} / {max_lvl}\n"
        f"🛠 <b>Специализация:</b> {spec}\n"
        f"💰 <b>След. уровень:</b> {fmt(price)} PTS\n\n"
        f"<i>Используйте кнопки для взаимодействия!</i>{AD_TEXT}",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("pet:"))
async def pet_action_handler(call: CallbackQuery):
    """Логика взаимодействия с питомцами через кнопки."""
    _, action, p_type = call.data.split(":")
    u = await get_user(call.from_user.id)
    is_mon = (p_type == "mon")
    
    lvl_field = "monkey_lvl" if is_mon else "pig_lvl"
    lvl = u[lvl_field]

    if action == "rename":
        cmd = "/name_monkey" if is_mon else "/name_pig"
        return await call.answer(f"Используй: {cmd} [имя]", show_alert=True)

    if action == "up":
        if lvl >= 15: return await call.answer("Достигнут лимит уровня!", show_alert=True)
        
        price_base = 7500 if is_mon else 3500
        price = price_base + (lvl * 1750)
        
        if u['points'] < price:
            return await call.answer("❌ Недостаточно очков!", show_alert=True)
        
        await db.execute(f"UPDATE users SET points = points - ?, {lvl_field} = {lvl_field} + 1 WHERE user_id = ?", (price, u['user_id']))
        await call.answer("🌟 Уровень повышен!", show_alert=True)
        await call.message.delete()
        await render_pet_interface(call.message, p_type)

    if action == "work":
        if lvl == 0: return await call.answer("Сначала улучшите питомца до 1 уровня!", show_alert=True)
        
        time_field = "last_farm_monkey" if is_mon else "last_farm_pig"
        cooldown = 1500 # 25 минут
        now = int(time.time())
        
        if now - u[time_field] < cooldown:
            rem = (cooldown - (now - u[time_field])) // 60
            return await call.answer(f"💤 Питомец отдыхает. Еще {rem} мин.", show_alert=True)
        
        # Расчет прибыли
        if is_mon:
            reward = lvl * random.randint(3, 12)
            await db.execute(f"UPDATE users SET coins = coins + ?, {time_field} = ? WHERE user_id = ?", (reward, now, u['user_id']))
            await call.answer(f"🐒 Добыто {reward} AliCoin!", show_alert=True)
        else:
            reward = lvl * random.randint(100, 300)
            await db.execute(f"UPDATE users SET points = points + ?, {time_field} = ? WHERE user_id = ?", (reward, now, u['user_id']))
            await call.answer(f"🐷 Нафармлено {reward} PTS!", show_alert=True)

@dp.message(Command("name_monkey", "name_pig"))
async def cmd_pet_rename(message: Message, command: CommandObject):
    """Смена имени питомца."""
    if not command.args: return await message.answer("❌ Укажите имя питомца.")
    
    is_mon = "monkey" in message.text
    column = "monkey_name" if is_mon else "pig_name"
    new_name = command.args[:15].strip()
    
    await db.execute(f"UPDATE users SET {column} = ? WHERE user_id = ?", (new_name, message.from_user.id))
    await message.answer(f"✅ Теперь вашего питомца зовут: <b>{new_name}</b>")

# 🎫 СИСТЕМА ПРОМОКОДОВ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("promo", "промо"))
async def cmd_promo(message: Message, command: CommandObject):
    """Активация бонусов по коду."""
    if not command.args:
        return await message.answer("🎫 <b>Использование:</b> <code>/promo [код]</code>", parse_mode="HTML")
    
    code = command.args.strip().upper()
    promo = await db.execute("SELECT * FROM promos WHERE code = ?", (code,), fetch="one")
    
    if not promo:
        return await message.answer("❌ Такого промокода не существует.")
    
    used = await db.execute("SELECT * FROM used_promos WHERE user_id = ? AND code = ?", (message.from_user.id, code), fetch="one")
    if used:
        return await message.answer("❌ Вы уже активировали этот бонус.")
    
    reward = random.randint(promo['min_val'], promo['max_val'])
    
    await db.execute("INSERT INTO used_promos VALUES (?, ?)", (message.from_user.id, code))
    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, message.from_user.id))
    
    await message.answer(
        f"🎫 <b>УСПЕХ!</b>\n"
        f"Начислено: <b>{fmt(reward)}</b> PTS\n"
        f"Код: <code>{code}</code>"
        f"{AD_TEXT}", parse_mode="HTML"
    )

# 👮‍♂️ АДМИНИСТРАТИВНЫЙ ФУНКЦИОНАЛ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(F.text.startswith("!рассылка"))
async def admin_broadcast(message: Message):
    """Массовая рассылка от имени бота."""
    if message.from_user.id != ADMIN_ID: return
    
    broadcast_msg = message.text.replace("!рассылка", "").strip()
    if not broadcast_msg: return
    
    all_users = await db.execute("SELECT user_id FROM users", fetch="all")
    success, fail = 0, 0
    
    status_msg = await message.answer(f"🚀 Начало рассылки на {len(all_users)} чел...")
    
    for u in all_users:
        try:
            await bot.send_message(u['user_id'], f"📢 <b>ВНИМАНИЕ:</b>\n\n{broadcast_msg}", parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.04) # Защита от Flood Limit
        except:
            fail += 1
            
    await status_msg.edit_text(f"🏁 <b>Рассылка завершена!</b>\n✅ Успешно: {success}\n❌ Ошибок: {fail}")

@dp.message(Command("addpromo"))
async def admin_add_promo(message: Message, command: CommandObject):
    """Создание/Обновление промокода с очисткой истории для реактивации."""
    if message.from_user.id != ADMIN_ID: return
    
    try:
        args = command.args.split()
        code = args[0].upper()
        v_min, v_max = int(args[1]), int(args[2])
        
        # Перезаписываем промокод и очищаем историю его активаций
        await db.execute("INSERT OR REPLACE INTO promos (code, min_val, max_val) VALUES (?, ?, ?)", (code, v_min, v_max))
        await db.execute("DELETE FROM used_promos WHERE code = ?", (code,))
        
        await message.answer(f"✅ Код <code>{code}</code> готов! Диапазон: {v_min}-{v_max}.\nВсе игроки могут ввести его снова.")
    except:
        await message.answer("❌ Ошибка. Формат: <code>/addpromo [код] [мин] [макс]</code>")

@dp.message(Command("set"))
async def admin_set_balance(message: Message, command: CommandObject):
    """Принудительная установка баланса пользователю."""
    if message.from_user.id != ADMIN_ID: return
    try:
        t_id, amount = map(int, command.args.split())
        await db.execute("UPDATE users SET points = ? WHERE user_id = ?", (amount, t_id))
        await message.answer(f"✅ Баланс игрока <code>{t_id}</code> изменен на {amount}.")
    except:
        await message.answer("❌ Формат: <code>/set [id] [очки]</code>")

@dp.message(Command("set_rate"))
async def admin_set_rate(message: Message, command: CommandObject):
    """Ручная фиксация курса AliCoin."""
    if message.from_user.id != ADMIN_ID: return
    try:
        Market.price = int(command.args)
        Market.manual_override = True
        await message.answer(f"🛑 <b>РЫНОК ЗАМОРОЖЕН!</b>\nНовый курс: {Market.price} PTS.")
    except:
        await message.answer("❌ Укажите число.")

@dp.message(Command("reset_rate"))
async def admin_reset_rate(message: Message):
    """Возврат рыночного регулирования курса."""
    if message.from_user.id != ADMIN_ID: return
    Market.manual_override = False
    await message.answer("🟢 <b>РЫНОК РАЗБЛОКИРОВАН.</b> Волатильность включена.")

@dp.message(Command("stats"))
async def admin_get_stats(message: Message):
    """Техническая статистика проекта."""
    if message.from_user.id != ADMIN_ID: return
    
    u_count = await db.execute("SELECT COUNT(*) as c FROM users", fetch="one")
    p_sum = await db.execute("SELECT SUM(points) as s FROM users", fetch="one")
    c_sum = await db.execute("SELECT SUM(coins) as s FROM users", fetch="one")
    
    stats_text = (
        "📊 <b>ТЕХНИЧЕСКАЯ СТАТИСТИКА</b>\n"
        f"👥 Всего игроков: {u_count['c']}\n"
        f"💰 Очков в обороте: {fmt(p_sum['s'] or 0)}\n"
        f"🪙 Монет в обороте: {fmt(c_sum['s'] or 0)}\n"
        f"📈 Курс ALI: {Market.price}\n"
        f"⚙️ Ручной режим: {'ВКЛ' if Market.manual_override else 'ВЫКЛ'}"
    )
    await message.answer(stats_text, parse_mode="HTML")

# 🚀 ЗАПУСК СИСТЕМЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def on_startup():
    """Действия при инициализации бота."""
    logger.info("Initializing database...")
    await db.init_tables()
    
    logger.info("Setting bot commands...")
    await bot.set_my_commands([
        BotCommand(command="chaihana", description="Получить очки"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="top", description="Топ чата"),
        BotCommand(command="world", description="Мировой рейтинг"),
        BotCommand(command="rate", description="Курс криптовалюты"),
        BotCommand(command="help", description="Помощь"),
    ])
    
    # Запуск фонового процесса обновления рынка
    asyncio.create_task(Market.updater())
    logger.info("Market updater started.")

async def main():
    """Основная точка входа."""
    await on_startup()
    
    # Очистка очереди обновлений и запуск Polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot is polling...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot turned off.")
