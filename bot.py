import asyncio
import logging
import random
import time
import math
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage

# ⚙️ КОНФИГУРАЦИЯ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
TOKEN = "8542233717:AAEfuFgvdkHLRDMshwzWq885r2dECOiYW0s"  # Убедитесь, что токен верный
ADMIN_ID = 5394084759
CHANNEL_TAG = "@chaihanabotprom"
DB_NAME = "chaihana_v2.db"

# Текстовые константы
AD_TEXT = f"\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n📢 <b>Инфо и промокоды доза пиписьки:</b> {CHANNEL_TAG}"

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Глобальные переменные экономики
CRYPTO_PRICE = 100
LAST_CRYPTO_UPDATE = 0

# 🛠 МЕНЕДЖЕР БАЗЫ ДАННЫХ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
class Database:
    def __init__(self, db_path):
        self.db_path = db_path

    async def execute(self, sql, params=(), fetch=None):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            data = None
            if fetch == "one":
                data = await cursor.fetchone()
            elif fetch == "all":
                data = await cursor.fetchall()
            await db.commit()
            return data

    async def init_tables(self):
        await self.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            custom_name TEXT,
            points INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            monkey_lvl INTEGER DEFAULT 0,
            pig_lvl INTEGER DEFAULT 0,
            last_chaihana INTEGER DEFAULT 0,
            last_farm_monkey INTEGER DEFAULT 0,
            last_farm_pig INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0,
            last_work INTEGER DEFAULT 0
        )""")
        await self.execute("""CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            min_val INTEGER,
            max_val INTEGER,
            activations INTEGER DEFAULT 0
        )""")
        await self.execute("""CREATE TABLE IF NOT EXISTS used_promos (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )""")

db = Database(DB_NAME)

# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def get_user(user_id, username=None):
    user = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch="one")
    if not user:
        await db.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        return await get_user(user_id, username)
    
    # Обновляем юзернейм если изменился
    if username and user['username'] != username:
         await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    return user

async def get_rank(user_id):
    res = await db.execute("SELECT COUNT(*) as cnt FROM users WHERE points > (SELECT points FROM users WHERE user_id = ?)", (user_id,), fetch="one")
    return res['cnt'] + 1

async def crypto_updater():
    """Фоновая задача для обновления курса с реалистичной волатильностью"""
    global CRYPTO_PRICE
    while True:
        # Генерируем случайное число для определения события на рынке
        event = random.random()
        
        if event < 0.10:  # 10% шанс на КРАХ (Дамп)
            change_percent = random.uniform(-0.40, -0.15) # Падение от 15% до 40%
        elif event < 0.45:  # 35% шанс на обычное падение
            change_percent = random.uniform(-0.07, -0.01) # Падение от 1% до 7%
        elif event < 0.85:  # 40% шанс на умеренный рост
            change_percent = random.uniform(0.01, 0.08)  # Рост от 1% до 8%
        else:  # 15% шанс на ТУЗЕМУН (Памп)
            change_percent = random.uniform(0.20, 0.60)  # Взлет от 20% до 60%

        # Вычисляем новую цену
        new_price = int(CRYPTO_PRICE * (1 + change_percent))
        
        # Устанавливаем границы, чтобы цена не ушла в ноль и не стала бесконечной
        if new_price < 10: 
            CRYPTO_PRICE = 10
        elif new_price > 25000:
            CRYPTO_PRICE = 20000
        else:
            CRYPTO_PRICE = new_price

        # Логируем изменение в консоль (для админа)
        logging.info(f"Обновление курса: {CRYPTO_PRICE} очков (изменение: {change_percent:.2%})")
        
        await asyncio.sleep(60)  # Обновляем раз в 5 минут (чтобы успевали торговать)

# 🎮 ОСНОВНЫЕ КОМАНДЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬

@dp.message(Command("start", "help", "помощь"))
async def cmd_start(message: types.Message):
    await get_user(message.from_user.id, message.from_user.username)
    text = (
        "🤖 <b>Чайхана Бот v3.0 (Fixed & Upgraded)</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "☕ <code>/chaihana</code> — Пить чай (репутация)\n"
        "💼 <code>/work</code> — Работать (монеты)\n"
        "🎁 <code>/bonus</code> — Ежедневный бонус\n"
        "👤 <code>/profile</code> — Твой профиль\n"
        "✏️ <code>/name [имя]</code> — Сменить ник\n"
        "🏆 <code>/top</code> — Топ игроков\n"
        "🎰 <code>/casino [сумма]</code> — Казино\n"
        "⚔️ <code>/duel [сумма]</code> — Дуэль с игроком\n"
        "💸 <code>/transfer [сумма]</code> — Перевод (ответом)\n"
        "📈 <code>/rate</code> — Курс Чайханокойна\n"
        "💰 <code>/buy [кол-во]</code> — Купить коины\n"
        "📉 <code>/sell [кол-во]</code> — Продать коины\n"
        "🐒 <code>/monkey</code> | 🐷 <code>/pig</code> — Питомцы\n"
        "🎫 <code>/promo [код]</code> — Ввести промокод"
        f"{AD_TEXT}"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("chaihana", "чайхана"))
@dp.message(F.text.lower() == "чайхана")
async def cmd_chaihana(message: types.Message):
    user = await get_user(message.from_user.id, message.from_user.username)
    now = int(time.time())
    cooldown = 3600  # 1 час

    if now - user['last_chaihana'] < cooldown:
        wait_time = int(cooldown - (now - user['last_chaihana']))
        m, s = divmod(wait_time, 60)
        await message.answer(f"⏳ <b>Чай еще горячий!</b>\nПриходи через: {m} мин. {s} сек." + AD_TEXT, parse_mode="HTML")
        return

    points = random.randint(-20, 40)
    await db.execute("UPDATE users SET points = points + ?, last_chaihana = ? WHERE user_id = ?", (points, now, message.from_user.id))
    
    emoji = "🟢" if points > 0 else "🔴"
    action = "кайфанул" if points > 0 else "обжегся"
    await message.answer(f"{emoji} <b>Чайхана:</b> Ты {action} и получил <b>{points}</b> очков репутации!" + AD_TEXT, parse_mode="HTML")

@dp.message(Command("work", "работа"))
async def cmd_work(message: types.Message):
    user = await get_user(message.from_user.id)
    now = int(time.time())
    cooldown = 1800 # 30 минут

    if now - user['last_work'] < cooldown:
        wait = int(cooldown - (now - user['last_work']))
        m, s = divmod(wait, 60)
        await message.answer(f"🛠 <b>Перекур!</b> Работать можно через: {m} мин.", parse_mode="HTML")
        return

    earnings = random.randint(5, 50)
    await db.execute("UPDATE users SET coins = coins + ?, last_work = ? WHERE user_id = ?", (earnings, now, message.from_user.id))
    await message.answer(f"🔨 Ты поработал на стройке чайханы и заработал <b>{earnings}</b> 🪙 чайханокойнов!{AD_TEXT}", parse_mode="HTML")

@dp.message(Command("bonus", "бонус"))
async def cmd_bonus(message: types.Message):
    user = await get_user(message.from_user.id)
    now = int(time.time())
    cooldown = 86400 # 24 часа

    if now - user['last_bonus'] < cooldown:
        h = int((cooldown - (now - user['last_bonus'])) / 3600)
        await message.answer(f"🎁 Бонус уже получен. Жди {h} ч.", parse_mode="HTML")
        return

    bonus_points = random.randint(100, 500)
    bonus_coins = random.randint(10, 50)
    
    await db.execute("UPDATE users SET points = points + ?, coins = coins + ?, last_bonus = ? WHERE user_id = ?", 
                     (bonus_points, bonus_coins, now, message.from_user.id))
    
    await message.answer(f"📅 <b>Ежедневный бонус:</b>\n+{bonus_points} очков\n+{bonus_coins} 🪙 коинов{AD_TEXT}", parse_mode="HTML")

@dp.message(Command("profile", "профиль"))
async def cmd_profile(message: types.Message):
    user = await get_user(message.from_user.id, message.from_user.username)
    rank = await get_rank(message.from_user.id)
    name = user['custom_name'] if user['custom_name'] else (user['username'] or "Гость")
    
    # Расчет состояния
    total_net_worth = user['points'] + (user['coins'] * CRYPTO_PRICE)

    text = (
        f"👤 <b>Профиль Чайханщика:</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🏷 <b>Имя:</b> {name}\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"🏆 <b>Репутация:</b> {format_number(user['points'])}\n"
        f"🪙 <b>Коины:</b> {format_number(user['coins'])}\n"
        f"💰 <b>Состояние:</b> ≈ {format_number(total_net_worth)} очков\n"
        f"🌍 <b>Ранг:</b> #{rank}\n\n"
        f"🐒 <b>Бибизян:</b> {user['monkey_lvl']} ур.\n"
        f"🐷 <b>Свин:</b> {user['pig_lvl']} ур."
        f"{AD_TEXT}"
    )
    
    photos = await message.from_user.get_profile_photos(limit=1)
    if photos.total_count > 0:
        await message.answer_photo(photos.photos[0][-1].file_id, caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

@dp.message(Command("name", "ник"))
async def cmd_name(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer(f"❌ <b>Пример:</b> /name [Новое имя]", parse_mode="HTML")
        return
    
    new_name = command.args[:25].replace("<", "").replace(">", "") # Защита от HTML тегов
    await db.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (new_name, message.from_user.id))
    await message.answer(f"✅ Теперь тебя зовут: <b>{new_name}</b>{AD_TEXT}", parse_mode="HTML")

# 💸 ЭКОНОМИКА
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("rate", "курс"))
async def cmd_rate(message: types.Message):
    await message.answer(f"📈 <b>Биржа Чайханы:</b>\n\n💰 1 🪙 = <b>{CRYPTO_PRICE}</b> очков репутации.\n<i>Курс плавающий!</i>{AD_TEXT}", parse_mode="HTML")

@dp.message(Command("buy", "купить"))
async def cmd_buy(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer(f"❌ Используй: <code>/buy [сумма]</code> или <code>/buy все</code>", parse_mode="HTML")
        return
    
    user = await get_user(message.from_user.id)
    arg = command.args.lower()
    
    can_buy_max = user['points'] // CRYPTO_PRICE
    
    if arg in ["все", "all", "всё"]:
        count = can_buy_max
    else:
        try:
            count = int(arg)
        except ValueError:
            await message.answer("❌ Введи число.")
            return

    if count <= 0:
        await message.answer("❌ Нельзя купить 0 или меньше.")
        return

    cost = count * CRYPTO_PRICE
    if user['points'] < cost:
        await message.answer(f"❌ Не хватает очков. Твой баланс: {user['points']}. Нужно: {cost}")
        return

    await db.execute("UPDATE users SET points = points - ?, coins = coins + ? WHERE user_id = ?", (cost, count, message.from_user.id))
    await message.answer(f"✅ Куплено <b>{count}</b> 🪙 за <b>{cost}</b> очков.{AD_TEXT}", parse_mode="HTML")

@dp.message(Command("sell", "продать"))
async def cmd_sell(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer(f"❌ Используй: <code>/sell [сумма]</code> или <code>/sell все</code>", parse_mode="HTML")
        return
    
    user = await get_user(message.from_user.id)
    arg = command.args.lower()
    
    if arg in ["все", "all", "всё"]:
        count = user['coins']
    else:
        try:
            count = int(arg)
        except ValueError: return

    if count <= 0 or user['coins'] < count:
        await message.answer(f"❌ У тебя нет столько монет.")
        return

    profit = count * CRYPTO_PRICE
    await db.execute("UPDATE users SET coins = coins - ?, points = points + ? WHERE user_id = ?", (count, profit, message.from_user.id))
    await message.answer(f"✅ Продано <b>{count}</b> 🪙 за <b>{profit}</b> очков.{AD_TEXT}", parse_mode="HTML")

@dp.message(Command("transfer", "передать"))
async def cmd_transfer(message: types.Message, command: CommandObject):
    if not message.reply_to_message:
        await message.answer("❌ Эту команду нужно писать в ответ на сообщение получателя.")
        return
    
    if message.reply_to_message.from_user.is_bot or message.reply_to_message.from_user.id == message.from_user.id:
        await message.answer("❌ Нельзя переводить ботам или самому себе.")
        return

    try:
        amount = int(command.args)
    except (ValueError, TypeError):
        await message.answer("❌ Укажи сумму: <code>/transfer 100</code>", parse_mode="HTML")
        return

    if amount <= 0: return

    sender = await get_user(message.from_user.id)
    if sender['points'] < amount:
        await message.answer("❌ Недостаточно средств.")
        return

    receiver_id = message.reply_to_message.from_user.id
    # Создаем получателя если его нет
    await get_user(receiver_id, message.reply_to_message.from_user.username)

    await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, message.from_user.id))
    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, receiver_id))

    await message.answer(f"💸 <b>Перевод успешен!</b>\nОтправлено {amount} очков игроку {message.reply_to_message.from_user.first_name}.{AD_TEXT}", parse_mode="HTML")

# 🎰 ИГРЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("casino", "казино"))
async def cmd_casino(message: types.Message, command: CommandObject):
    try:
        bet = int(command.args)
    except (ValueError, TypeError):
        await message.answer("🎰 Ставка: <code>/casino [сумма]</code>", parse_mode="HTML")
        return

    if bet < 10:
        await message.answer("❌ Минимальная ставка 10 очков.")
        return

    user = await get_user(message.from_user.id)
    if user['points'] < bet:
        await message.answer("❌ Не хватает очков.")
        return

    await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (bet, message.from_user.id))
    
    msg = await message.answer_dice(emoji="🎰")
    await asyncio.sleep(2.5) # Ждем анимацию
    val = msg.dice.value

    # Коэффициенты: 64 (три семерки) = x10, 1,22,43 (фрукты в ряд) = x3
    win_coeff = 0
    if val == 64: win_coeff = 10
    elif val in [1, 22, 43]: win_coeff = 3
    elif val in [16, 32, 48]: win_coeff = 1.5 # Две похожие

    if win_coeff > 0:
        win_amount = int(bet * win_coeff)
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win_amount, message.from_user.id))
        await message.answer(f"🎉 <b>ПОБЕДА!</b> Коэффициент x{win_coeff}!\nВыигрыш: {win_amount} очков!{AD_TEXT}", parse_mode="HTML")
    else:
        await message.answer(f"📉 Не повезло. Ты потерял {bet} очков.{AD_TEXT}", parse_mode="HTML")

@dp.message(Command("duel", "дуэль"))
async def cmd_duel(message: types.Message, command: CommandObject):
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot or message.reply_to_message.from_user.id == message.from_user.id:
        await message.answer("⚔️ Команду нужно писать в ответ реальному игроку.")
        return
    
    try:
        amount = int(command.args)
    except (ValueError, TypeError):
        await message.answer("⚔️ Укажи ставку: <code>/duel 100</code>", parse_mode="HTML")
        return

    if amount < 1: return

    user = await get_user(message.from_user.id)
    target = await get_user(message.reply_to_message.from_user.id)

    if user['points'] < amount:
        await message.answer("❌ У тебя не хватает очков.")
        return
    if target['points'] < amount:
        await message.answer("❌ У соперника не хватает очков.")
        return

    # Callback data structure: duel:action:amount:challenger_id
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"duel:acc:{amount}:{message.from_user.id}")
    kb.button(text="❌ Отказаться", callback_data=f"duel:dec:{amount}:{message.from_user.id}")
    
    await message.answer(
        f"⚔️ <b>ВЫЗОВ НА ДУЭЛЬ!</b>\n{message.from_user.first_name} вызывает {message.reply_to_message.from_user.first_name}!\n💰 Ставка: <b>{amount}</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("duel:"))
async def duel_callback(callback: CallbackQuery):
    _, action, s_amount, challenger_id_str = callback.data.split(":")
    amount = int(s_amount)
    challenger_id = int(challenger_id_str)
    
    # Тот, кого вызывали (должен быть получателем сообщения с кнопками, но в чате любой может нажать, поэтому проверяем)
    # В данном упрощенном варианте мы проверяем, не нажимает ли сам вызывающий
    if callback.from_user.id == challenger_id:
        if action == "dec": # Вызывающий может отменить
             await callback.message.edit_text(f"🚫 Дуэль отменена.{AD_TEXT}", parse_mode="HTML")
             return
        await callback.answer("Жди ответа соперника!", show_alert=True)
        return

    if action == "dec":
        await callback.message.edit_text(f"❌ Дуэль отклонена.{AD_TEXT}", parse_mode="HTML")
        return

    if action == "acc":
        # Повторная проверка баланса
        challenger = await get_user(challenger_id)
        acceptor = await get_user(callback.from_user.id)
        
        if challenger['points'] < amount or acceptor['points'] < amount:
            await callback.message.edit_text("❌ У кого-то закончились деньги во время раздумий.")
            return

        await callback.message.edit_text(f"🎲 <b>Бросаем кубики...</b>\nИгроки: {challenger['custom_name'] or 'Игрок 1'} vs {acceptor['custom_name'] or 'Игрок 2'}", parse_mode="HTML")
        
        d1 = await callback.message.answer_dice(emoji="🎲")
        d2 = await callback.message.answer_dice(emoji="🎲")
        await asyncio.sleep(4)
        
        v1 = d1.dice.value # Вызывающий
        v2 = d2.dice.value # Принявший

        winner_id = None
        loser_id = None
        res_text = ""

        if v1 > v2:
            winner_id, loser_id = challenger_id, callback.from_user.id
            res_text = f"🏆 Победил вызывавший!"
        elif v2 > v1:
            winner_id, loser_id = callback.from_user.id, challenger_id
            res_text = f"🏆 Победил принявший!"
        else:
            await callback.message.answer(f"🤝 <b>Ничья!</b> Ставки возвращены.{AD_TEXT}", parse_mode="HTML")
            return

        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, winner_id))
        await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, loser_id))
        
        await callback.message.answer(f"⚔️ Результат:\n{v1} : {v2}\n\n{res_text}\n💰 Выигрыш: {amount} очков.{AD_TEXT}", parse_mode="HTML")

# 🐾 ПИТОМЦЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("monkey", "бибизян"))
async def cmd_monkey(message: types.Message):
    await pet_menu(message, "mon")

@dp.message(Command("pig", "свин"))
async def cmd_pig(message: types.Message):
    await pet_menu(message, "pig")

async def pet_menu(message, p_type):
    user = await get_user(message.from_user.id)
    is_mon = p_type == "mon"
    lvl = user['monkey_lvl'] if is_mon else user['pig_lvl']
    name = "🐒 Бибизян" if is_mon else "🐷 Свин"
    
    # Экономика питомцев
    base_income = 15 if is_mon else 150
    income = lvl * base_income
    currency = "🪙" if is_mon else "очков"
    
    base_cost = 5000 if is_mon else 3500
    upg_cost = base_cost * (lvl + 1)
    
    kb = InlineKeyboardBuilder()
    if lvl < 20: 
        kb.button(text=f"⬆️ Улучшить ({upg_cost} pts)", callback_data=f"pet:upg:{p_type}")
    
    kb.button(text="🚜 Фармить", callback_data=f"pet:farm:{p_type}")
    
    text = (f"<b>{name}</b> (Уровень {lvl})\n"
            f"💰 Доход: {income} {currency} / час\n"
            f"⚡️ Цена улучшения: {upg_cost} очков\n\n"
            f"<i>Для фарма нажми кнопку ниже.</i>")
    
    if lvl == 0: text += "\n\n⚠️ <b>У тебя нет питомца!</b> Улучши уровень, чтобы купить."
    
    await message.answer(text + AD_TEXT, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("pet:"))
async def pet_callback(callback: CallbackQuery):
    _, action, ptype = callback.data.split(":")
    user_id = callback.from_user.id
    user = await get_user(user_id)
    is_mon = ptype == "mon"
    
    lvl_col = "monkey_lvl" if is_mon else "pig_lvl"
    lvl = user[lvl_col]

    if action == "upg":
        base_cost = 5000 if is_mon else 3500
        cost = base_cost * (lvl + 1)
        
        if user['points'] < cost:
            await callback.answer("❌ Не хватает очков!", show_alert=True)
            return
        
        await db.execute(f"UPDATE users SET points = points - ?, {lvl_col} = {lvl_col} + 1 WHERE user_id = ?", (cost, user_id))
        await callback.answer(f"Уровень повышен до {lvl+1}!", show_alert=True)
        await callback.message.delete() # Удаляем старое меню чтобы не путать

    elif action == "farm":
        if lvl == 0:
            await callback.answer("Сначала купи питомца (кнопка Улучшить)", show_alert=True)
            return
            
        last_col = "last_farm_monkey" if is_mon else "last_farm_pig"
        last_time = user[last_col]
        now = int(time.time())
        
        if now - last_time < 3600:
            rem = 3600 - (now - last_time)
            m = rem // 60
            await callback.answer(f"⏳ Питомец устал. Жди {m} мин.", show_alert=True)
            return
            
        income = lvl * (15 if is_mon else 150)
        curr_col = "coins" if is_mon else "points"
        
        await db.execute(f"UPDATE users SET {curr_col} = {curr_col} + ?, {last_col} = ? WHERE user_id = ?", (income, now, user_id))
        currency = "коинов" if is_mon else "очков"
        await callback.answer(f"✅ Собрано {income} {currency}!", show_alert=True)

# 📊 РАЗНОЕ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("top", "top"))
async def cmd_top(message: types.Message):
    # Топ 10 по очкам
    users = await db.execute("SELECT * FROM users ORDER BY points DESC LIMIT 10", fetch="all")
    text = "🏆 <b>Топ 10 Олигархов:</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
    for i, u in enumerate(users, 1):
        n = u['custom_name'] or u['username'] or "Аноним"
        text += f"{i}. <b>{n}</b> — {format_number(u['points'])}\n"
    
    await message.answer(text + AD_TEXT, parse_mode="HTML")

@dp.message(Command("promo", "промо"))
async def cmd_promo(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("🎫 Введи код: <code>/promo [код]</code>", parse_mode="HTML")
        return
    
    code = command.args.strip()
    promo = await db.execute("SELECT * FROM promos WHERE code = ?", (code,), fetch="one")
    
    if not promo:
        await message.answer("❌ Такого промокода нет.")
        return
        
    used = await db.execute("SELECT * FROM used_promos WHERE user_id = ? AND code = ?", (message.from_user.id, code), fetch="one")
    if used:
        await message.answer("❌ Ты уже активировал этот код.")
        return

    reward = random.randint(promo['min_val'], promo['max_val'])
    
    await db.execute("INSERT INTO used_promos VALUES (?, ?)", (message.from_user.id, code))
    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, message.from_user.id))
    await db.execute("UPDATE promos SET activations = activations + 1 WHERE code = ?", (code,))
    
    await message.answer(f"✅ <b>Промокод активирован!</b>\nНачислено: +{reward} очков.{AD_TEXT}", parse_mode="HTML")

# 👑 АДМИНКА (Управление рынком и ресурсами)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬

@dp.message(Command("setrate"))
async def adm_set_rate(message: types.Message, command: CommandObject):
    """Принудительно установить курс: /setrate 500"""
    if message.from_user.id != ADMIN_ID: 
        return # Бот проигнорирует, если пишет не админ
    
    try:
        global CRYPTO_PRICE
        new_price = int(command.args)
        CRYPTO_PRICE = new_price
        await message.answer(f"🛠 <b>Рынок под контролем:</b>\nКурс принудительно установлен на <b>{CRYPTO_PRICE}</b>")
    except:
        await message.answer("❌ Пиши: <code>/setrate 150</code>")

@dp.message(Command("pump"))
async def adm_pump(message: types.Message, command: CommandObject):
    """Резкий рост или обвал: /pump 0.5 (рост 50%) или /pump -0.8 (обвал 80%)"""
    if message.from_user.id != ADMIN_ID: 
        return
    
    try:
        global CRYPTO_PRICE
        multiplier = float(command.args)
        old_price = CRYPTO_PRICE
        CRYPTO_PRICE = int(CRYPTO_PRICE * (1 + multiplier))
        
        # Защита от отрицательного курса
        if CRYPTO_PRICE < 10: CRYPTO_PRICE = 10
        
        status = "🚀 ПАМП" if multiplier > 0 else "📉 ДАМП"
        await message.answer(f"⚠️ <b>{status} УСТРОЕН!</b>\nСтарая цена: {old_price}\nНовая цена: <b>{CRYPTO_PRICE}</b>")
    except:
        await message.answer("❌ Примеры:\n<code>/pump 0.5</code> (+50%)\n<code>/pump -0.5</code> (-50%)")

@dp.message(Command("admgive"))
async def adm_give(message: types.Message, command: CommandObject):
    """Выдать очки игроку: /admgive ID СУММА"""
    if message.from_user.id != ADMIN_ID: return
    try:
        args = command.args.split()
        uid = int(args[0])
        amt = int(args[1])
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amt, uid))
        await message.answer(f"💎 <b>Админ:</b> Вы выдали <b>{amt}</b> очков пользователю <code>{uid}</code>")
    except:
        await message.answer("❌ Ошибка. Используй: <code>/admgive ID СУММА</code>")
# 🚀 ЗАПУСК
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def main():
    await db.init_tables()
    
    # Запуск фоновых задач
    asyncio.create_task(crypto_updater())
    
    # Удаление вебхука и запуск пуллинга
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 BOT STARTED SUCCESSFULLY!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
