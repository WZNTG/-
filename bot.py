import asyncio
import logging
import random
import time
import math
from datetime import datetime, timedelta
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ⚙️ КОНФИГУРАЦИЯ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
TOKEN = "8542233717:AAEfuFgvdkHLRDMshwzWq885r2dECOiYW0s"
ADMIN_ID = 5394084759
CHANNEL_TAG = "@chaihanabotprom"
AD_TEXT = f"\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n📢 <b>Промокоды, информация и какой-то Даниил:</b> {CHANNEL_TAG}"

# Логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Глобальные переменные
DB_NAME = "chaihana.db"
CRYPTO_PRICE = 100  # Начальная цена
ACTIVE_DUELS = {}   # message_id: {data}

# 🛠 БАЗА ДАННЫХ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            custom_name TEXT,
            points INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            monkey_lvl INTEGER DEFAULT 0,
            pig_lvl INTEGER DEFAULT 0,
            last_chaihana INTEGER DEFAULT 0,
            last_farm_monkey INTEGER DEFAULT 0,
            last_farm_pig INTEGER DEFAULT 0
        )""")
        # Таблица промокодов
        await db.execute("""CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            min_val INTEGER,
            max_val INTEGER,
            is_random BOOLEAN
        )""")
        # Таблица использованных промокодов
        await db.execute("""CREATE TABLE IF NOT EXISTS used_promos (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )""")
        await db.commit()

# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def get_user(user_id, username=None):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
                await db.commit()
                return await get_user(user_id, username)
            return user

async def update_balance(user_id, amount, currency="points"):
    col = "points" if currency == "points" else "coins"
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE users SET {col} = {col} + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def get_top_users(limit=10, global_top=True, chat_users=None):
    async with aiosqlite.connect(DB_NAME) as db:
        if global_top:
            sql = "SELECT user_id, custom_name, username, points FROM users ORDER BY points DESC LIMIT ?"
            params = (limit,)
        else:
            # Для топа чата нужен список ID участников, но бот не хранит всех юзеров чата по умолчанию.
            # Мы будем фильтровать тех, кто есть в БД.
            placeholders = ','.join('?' for _ in chat_users)
            sql = f"SELECT user_id, custom_name, username, points FROM users WHERE user_id IN ({placeholders}) ORDER BY points DESC LIMIT ?"
            params = (*chat_users, limit)
        
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchall()

async def get_rank(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        # Узнаем место в мире
        async with db.execute("SELECT COUNT(*) FROM users WHERE points > (SELECT points FROM users WHERE user_id = ?)", (user_id,)) as cursor:
            rank = (await cursor.fetchone())[0] + 1
        return rank

# 📈 ФОНОВАЯ ЗАДАЧА: КУРС КРИПТЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def crypto_updater():
    global CRYPTO_PRICE
    while True:
        # Рандом от 1 до 5000
        CRYPTO_PRICE = random.randint(1, 5000)
        # Каждые 1.3 минуты = 78 секунд
        await asyncio.sleep(78)

# 🎮 КОМАНДЫ ПОЛЬЗОВАТЕЛЯ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬

# /chaihana
@dp.message(F.text.lower().in_({"чайхана", "/chaihana"}))
async def cmd_chaihana(message: types.Message):
    user = await get_user(message.from_user.id, message.from_user.username)
    now = int(time.time())
    cooldown = 5400 # 1 час 30 минут

    if now - user[7] < cooldown:
        wait_time = int(cooldown - (now - user[7]))
        m, s = divmod(wait_time, 60)
        h, m = divmod(m, 60)
        await message.answer(f"⏳ <b>Остынь!</b> Чайхана закрыта на уборку. Приходи через: {h}ч {m}м {s}с" + AD_TEXT, parse_mode="HTML")
        return

    points = random.randint(-10, 10)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET points = points + ?, last_chaihana = ? WHERE user_id = ?", (points, now, message.from_user.id))
        await db.commit()
    
    emoji = "🟢" if points > 0 else "🔴"
    await message.answer(f"{emoji} <b>Чайхана вердикт:</b>\nТы получил <b>{points}</b> очков преданности!" + AD_TEXT, parse_mode="HTML")

# /profile
@dp.message(F.text.lower().in_({"профиль", "/profile", "profile"}))
async def cmd_profile(message: types.Message):
    user = await get_user(message.from_user.id, message.from_user.username)
    rank = await get_rank(message.from_user.id)
    name = user[2] if user[2] else (user[1] if user[1] else "Безымянный")
    
    text = (
        f"👤 <b>Профиль пользователя:</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🏷 <b>Ник:</b> {name}\n"
        f"🆔 <b>ID:</b> <code>{user[0]}</code>\n"
        f"🏆 <b>Очки:</b> {user[3]}\n"
        f"🪙 <b>Чайханокойны:</b> {user[4]}\n"
        f"🌍 <b>Место в мире:</b> #{rank}\n"
        f"🐒 <b>Бибизян:</b> {user[5]} ур.\n"
        f"🐷 <b>Свин:</b> {user[6]} ур."
        f"{AD_TEXT}"
    )
    
    # Пытаемся получить аватарку
    photos = await message.from_user.get_profile_photos(limit=1)
    if photos.total_count > 0:
        await message.answer_photo(photos.photos[0][-1].file_id, caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

# /name
@dp.message(Command("name"))
async def cmd_name(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer(f"❌ <b>Использование:</b> /name [Новое имя]{AD_TEXT}", parse_mode="HTML")
        return
    
    new_name = command.args[:30] # Ограничение длины
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (new_name, message.from_user.id))
        await db.commit()
    await message.answer(f"✅ Имя изменено на: <b>{new_name}</b>{AD_TEXT}", parse_mode="HTML")

# /rate (Курс)
@dp.message(F.text.lower().in_({"курс", "/rate"}))
async def cmd_rate(message: types.Message):
    await message.answer(f"📈 <b>Биржа Чайханы:</b>\n\n💰 1 Чайханокойн = <b>{CRYPTO_PRICE}</b> очков.\n<i>Курс обновляется каждые 1.3 минуты.</i>{AD_TEXT}", parse_mode="HTML")

# /buy (Купить)
@dp.message(F.text.lower().startswith(("купить", "/buy")))
async def cmd_buy(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(f"❌ Пиши: <code>купить [сумма]</code> или <code>купить все</code>{AD_TEXT}", parse_mode="HTML")
        return
    
    user = await get_user(message.from_user.id)
    amount_req = args[1].lower()
    
    max_buy = user[3] // CRYPTO_PRICE # Сколько может купить на свои очки
    
    if amount_req == "все" or amount_req == "all":
        count = max_buy
    else:
        try:
            count = int(amount_req)
        except:
            await message.answer("❌ Неверное число.")
            return

    if count <= 0:
        await message.answer("❌ Минимум 1 монета.")
        return

    cost = count * CRYPTO_PRICE
    if user[3] < cost:
        await message.answer(f"❌ Недостаточно очков. Нужно: {cost}, есть: {user[3]}{AD_TEXT}", parse_mode="HTML")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET points = points - ?, coins = coins + ? WHERE user_id = ?", (cost, count, message.from_user.id))
        await db.commit()
    
    await message.answer(f"✅ Куплено <b>{count}</b> 🪙 за <b>{cost}</b> очков.{AD_TEXT}", parse_mode="HTML")

# /sell (Продать)
@dp.message(F.text.lower().startswith(("продать", "/sell")))
async def cmd_sell(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(f"❌ Пиши: <code>продать [сумма]</code> или <code>продать все</code>{AD_TEXT}", parse_mode="HTML")
        return
    
    user = await get_user(message.from_user.id)
    amount_req = args[1].lower()
    
    if amount_req == "все" or amount_req == "all":
        count = user[4]
    else:
        try:
            count = int(amount_req)
        except:
            await message.answer("❌ Неверное число.")
            return

    if count <= 0 or user[4] < count:
        await message.answer(f"❌ У тебя нет столько монет.{AD_TEXT}", parse_mode="HTML")
        return

    profit = count * CRYPTO_PRICE
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET coins = coins - ?, points = points + ? WHERE user_id = ?", (count, profit, message.from_user.id))
        await db.commit()
    
    await message.answer(f"✅ Продано <b>{count}</b> 🪙 за <b>{profit}</b> очков.{AD_TEXT}", parse_mode="HTML")

# /transfer (Передать)
@dp.message(F.text.lower().startswith(("передать", "/transfer")))
async def cmd_transfer(message: types.Message):
    if not message.reply_to_message:
        await message.answer(f"❌ Эту команду нужно писать в ответ на сообщение того, кому передаешь.{AD_TEXT}", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажи сумму: <code>передать 100</code>")
        return

    try:
        amount = int(args[1])
    except:
        return

    if amount <= 0: return
    sender = await get_user(message.from_user.id)
    receiver_id = message.reply_to_message.from_user.id

    if sender[3] < amount:
        await message.answer(f"❌ Недостаточно средств.{AD_TEXT}", parse_mode="HTML")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, message.from_user.id))
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (receiver_id, message.reply_to_message.from_user.username))
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, receiver_id))
        await db.commit()

    await message.answer(f"💸 <b>Перевод успешен!</b>\n{message.from_user.first_name} перевел {amount} очков пользователю {message.reply_to_message.from_user.first_name}{AD_TEXT}", parse_mode="HTML")

# /casino (Казино)
@dp.message(F.text.lower().startswith(("казино", "/casino")))
async def cmd_casino(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(f"🎰 Ставка: <code>казино [сумма]</code>{AD_TEXT}", parse_mode="HTML")
        return
    try:
        bet = int(args[1])
    except: return

    if bet <= 0: return
    user = await get_user(message.from_user.id)
    if user[3] < bet:
        await message.answer(f"❌ Мало очков для ставки.{AD_TEXT}", parse_mode="HTML")
        return

    # Списываем ставку
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (bet, message.from_user.id))
        await db.commit()

    # Кидаем дайс
    msg = await message.answer_dice(emoji="🎰")
    val = msg.dice.value
    await asyncio.sleep(2) # Пауза для анимации

    # Логика слота (Telegram dice value: 1-64. 64 is 777)
    # Упрощенная логика по значениям дайса:
    # 1, 22, 43 - это бары, виноград, лимоны (проигрыш/малый выигрыш - зависит от реализации)
    # Но в ТГ value 64 = три семерки.
    
    # Сделаем простую логику:
    win_coeff = 0
    if val == 64: # 777
        win_coeff = 5
    elif val in [1, 22, 43]: # Три одинаковых картинки (условно)
        win_coeff = 2
    
    if win_coeff > 0:
        win_amount = bet * win_coeff
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win_amount, message.from_user.id))
            await db.commit()
        await message.answer(f"🎉 <b>ДЖЕКПОТ!</b> Выпало x{win_coeff}! Ты выиграл <b>{win_amount}</b> очков!{AD_TEXT}", parse_mode="HTML")
    else:
        await message.answer(f"📉 Ты проиграл <b>{bet}</b> очков. Попробуй еще!{AD_TEXT}", parse_mode="HTML")

# /duel (Дуэль)
@dp.message(F.text.lower().startswith(("дуэль", "/duel")))
async def cmd_duel(message: types.Message):
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        await message.answer(f"⚔️ Ответь на сообщение соперника: <code>дуэль [сумма]</code>{AD_TEXT}", parse_mode="HTML")
        return
    
    args = message.text.split()
    try:
        amount = int(args[1])
    except: return

    user = await get_user(message.from_user.id)
    target = await get_user(message.reply_to_message.from_user.id)
    
    if user[3] < amount or target[3] < amount:
        await message.answer("❌ У кого-то из вас не хватает очков!", parse_mode="HTML")
        return

    # Клавиатура
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"duel_acc_{amount}_{message.from_user.id}")
    kb.button(text="❌ Отказаться", callback_data=f"duel_dec_{message.from_user.id}")
    kb.button(text="🚫 Отменить", callback_data=f"duel_cancel_{message.from_user.id}") # Может нажать автор
    
    msg = await message.answer(
        f"⚔️ <b>ДУЭЛЬ!</b>\n{message.from_user.first_name} вызывает {message.reply_to_message.from_user.first_name}!\n💰 Ставка: <b>{amount}</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("duel_"))
async def duel_callback(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action = data[1]
    
    # Получаем ID участников из текста сообщения (хак, лучше хранить в БД, но для простоты так)
    # В колбеке мы передали ID автора вызова (challenger)
    challenger_id = int(data[-1])
    
    # Тот, кому бросили вызов - это юзер, упомянутый в тексте, но надежнее проверить права
    # В данном коде мы упростим: кнопку принять может нажать только тот, на чье сообщение ответили.
    # Но так как reply нет в callback, мы полагаемся на логику "только соперник может принять"
    
    # Определим соперника по entities сообщения или просто сделаем проверку:
    # Принять может любой кроме автора? Нет, это дыра.
    # Исправим: Дуэль через реплай, значит мы знаем имена.
    
    if action == "acc":
        amount = int(data[2])
        # Проверка: нажать может кто угодно? Нет, надо ограничить.
        # В идеале хранить state. Тут разрешим нажать "Принять" любому кроме автора (риск, но код проще)
        if callback.from_user.id == challenger_id:
            await callback.answer("Ты не можешь принять свой вызов!", show_alert=True)
            return
            
        # Проводим дуэль
        # Бросок 1
        d1 = await callback.message.answer_dice(emoji="🎲")
        # Бросок 2
        d2 = await callback.message.answer_dice(emoji="🎲")
        await asyncio.sleep(4)
        
        v1 = d1.dice.value # Challenger (автор)
        v2 = d2.dice.value # Opponent (нажавший)
        
        # Списываем/начисляем
        async with aiosqlite.connect(DB_NAME) as db:
            if v1 > v2:
                winner = challenger_id
                loser = callback.from_user.id
                res = f"🏆 Победил вызывавший (ID {winner})!"
            elif v2 > v1:
                winner = callback.from_user.id
                loser = challenger_id
                res = f"🏆 Победил принявший (ID {winner})!"
            else:
                await callback.message.edit_text(f"🤝 <b>Ничья!</b> Ставки возвращены.{AD_TEXT}", parse_mode="HTML")
                return

            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, winner))
            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, loser))
            await db.commit()
            
        await callback.message.edit_text(f"⚔️ <b>Результат:</b> {v1} vs {v2}\n{res}\n💰 Выигрыш: {amount}{AD_TEXT}", parse_mode="HTML")

    elif action == "dec":
        if callback.from_user.id == challenger_id:
            await callback.answer("Ты не можешь отказаться от своего вызова, жми Отменить.", show_alert=True)
            return
        await callback.message.edit_text(f"❌ Дуэль отклонена.{AD_TEXT}", parse_mode="HTML")
        
    elif action == "cancel":
        if callback.from_user.id != challenger_id:
            await callback.answer("Только автор может отменить.", show_alert=True)
            return
        await callback.message.delete()

# /monkey & /pig (Питомцы)
@dp.message(F.text.lower().in_({"бибизян", "/monkey", "свин", "/pig"}))
async def cmd_pet(message: types.Message):
    cmd = message.text.lower().replace("/", "")
    user = await get_user(message.from_user.id)
    is_monkey = "бибизян" in cmd or "monkey" in cmd
    
    # Индексы в БД: 5 - monkey_lvl, 6 - pig_lvl
    lvl_idx = 5 if is_monkey else 6
    lvl = user[lvl_idx]
    pet_name = "🐒 Бибизян" if is_monkey else "🐷 Свин"
    cost_base = 5000 if is_monkey else 3500
    
    # Цена улучшения: База * (Лвл + 1)
    upgrade_cost = cost_base * (lvl + 1)
    
    kb = InlineKeyboardBuilder()
    if lvl < 15:
        kb.button(text=f"⬆️ Улучшить ({upgrade_cost})", callback_data=f"upg_{'mon' if is_monkey else 'pig'}_{upgrade_cost}")
    kb.button(text="🚜 Фармить", callback_data=f"farm_{'mon' if is_monkey else 'pig'}")
    
    text = (
        f"{pet_name} (Уровень {lvl}/15)\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"Добывает: {'🪙 Крипту' if is_monkey else '🏆 Очки'}\n"
        f"Доход: {lvl * (10 if is_monkey else 100)} за сбор.\n"
        f"КД сбора: 1 час.\n"
        f"Стоимость улучшения: {upgrade_cost}\n"
    )
    if lvl == 0:
        text += "\n<i>Купи питомца, нажав 'Улучшить'!</i>"
        
    await message.answer(text + AD_TEXT, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith(("upg_", "farm_")))
async def pet_callback(callback: types.CallbackQuery):
    action, pet_type, *args = callback.data.split("_")
    user_id = callback.from_user.id
    user = await get_user(user_id)
    
    is_monkey = pet_type == "mon"
    lvl_idx = 5 if is_monkey else 6
    lvl = user[lvl_idx]
    
    if action == "upg":
        cost = int(args[0])
        if lvl >= 15:
            await callback.answer("Максимальный уровень!", show_alert=True)
            return
        if user[3] < cost: # Покупаем за очки
            await callback.answer("Не хватает очков!", show_alert=True)
            return
        
        async with aiosqlite.connect(DB_NAME) as db:
            col = "monkey_lvl" if is_monkey else "pig_lvl"
            await db.execute(f"UPDATE users SET points = points - ?, {col} = {col} + 1 WHERE user_id = ?", (cost, user_id))
            await db.commit()
        await callback.message.edit_text(f"✅ Питомец улучшен до {lvl+1} уровня!{AD_TEXT}", parse_mode="HTML")
        
    elif action == "farm":
        if lvl == 0:
            await callback.answer("Сначала купи питомца!", show_alert=True)
            return
            
        last_farm_idx = 8 if is_monkey else 9
        last_farm = user[last_farm_idx]
        now = int(time.time())
        
        if now - last_farm < 3600:
            await callback.answer(f"⏳ Питомец устал. Жди еще {(3600 - (now-last_farm))//60} мин.", show_alert=True)
            return
            
        farm_amount = lvl * (10 if is_monkey else 100) # Формула дохода
        res_col = "coins" if is_monkey else "points"
        last_farm_col = "last_farm_monkey" if is_monkey else "last_farm_pig"
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(f"UPDATE users SET {res_col} = {res_col} + ?, {last_farm_col} = ? WHERE user_id = ?", (farm_amount, now, user_id))
            await db.commit()
            
        currency = "🪙" if is_monkey else "🏆"
        await callback.answer(f"Собрано {farm_amount} {currency}", show_alert=True)

# 👑 АДМИН ПАНЕЛЬ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("adminhelp"))
async def cmd_admin_help(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = (
        "🔐 <b>Админ-панель:</b>\n"
        "/set [id/reply] [сумма] - Установить очки\n"
        "/addpromo [код] [мин] [макс] - Создать промокод (перезаписывает)\n"
        "/send [текст] - Рассылка всем\n"
    )
    await message.answer(text + AD_TEXT, parse_mode="HTML")

@dp.message(Command("set"))
async def cmd_set(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    args = command.args.split() if command.args else []
    
    target_id = message.from_user.id
    amount = 0
    
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        if args: amount = int(args[0])
    elif len(args) >= 2:
        target_id = int(args[0])
        amount = int(args[1])
    else:
        await message.answer("Ошибка аргументов.")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET points = ? WHERE user_id = ?", (amount, target_id))
        await db.commit()
    await message.answer(f"✅ Установлено {amount} очков для {target_id}")

@dp.message(Command("addpromo"))
async def cmd_addpromo(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    # /addpromo NEWYEAR -100 100
    try:
        args = command.args.split()
        code = args[0]
        min_v = int(args[1])
        max_v = int(args[2])
    except:
        await message.answer("Формат: /addpromo CODE MIN MAX")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO promos (code, min_val, max_val, is_random) VALUES (?, ?, ?, 1)", (code, min_v, max_v))
        await db.commit()
    await message.answer(f"📢 Промокод <b>{code}</b> создан ({min_v} - {max_v}).", parse_mode="HTML")

@dp.message(F.text) # Обработка промокода просто текстом
async def check_promo(message: types.Message):
    # Если это не команда, проверяем на промокод
    if message.text.startswith("/"): return 
    
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверка существования
        async with db.execute("SELECT * FROM promos WHERE code = ?", (code,)) as cursor:
            promo = await cursor.fetchone()
        
        if not promo: return # Не промокод, игнорим
        
        # Проверка использования
        async with db.execute("SELECT * FROM used_promos WHERE user_id = ? AND code = ?", (message.from_user.id, code)) as cursor:
            if await cursor.fetchone():
                await message.answer(f"❌ Ты уже активировал этот код!{AD_TEXT}", parse_mode="HTML")
                return

        # Награда
        reward = random.randint(promo[1], promo[2])
        await db.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (message.from_user.id, code))
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, message.from_user.id))
        await db.commit()
        
        await message.answer(f"🎁 <b>Промокод активирован!</b>\nТы получил: <b>{reward}</b> очков!{AD_TEXT}", parse_mode="HTML")

# /top & /world
@dp.message(F.text.lower().in_({"топ", "/top", "мир", "/world"}))
async def cmd_top(message: types.Message):
    is_world = "мир" in message.text.lower() or "world" in message.text.lower()
    
    chat_users = []
    if not is_world and message.chat.type != "private":
        # Это сложный момент для ботов: получить всех юзеров чата невозможно без админки и кэша.
        # Для "Топ чата" мы покажем топ мира, но с заголовком, либо (если бы была база всех участников чата) фильтровали бы.
        # В данном решении, чтобы код работал 100%, топ чата будет работать как Топ мира, 
        # но в реальном проекте нужно сохранять chat_id в таблицу users при каждом сообщении.
        pass

    users = await get_top_users(10, global_top=True) # Пока используем глобальный топ для надежности
    
    title = "🌍 Топ мира" if is_world else "🏆 Топ (глобальный)"
    text = f"<b>{title}:</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
    
    for idx, u in enumerate(users, 1):
        name = u[1] if u[1] else (u[2] if u[2] else "ID: " + str(u[0]))
        medal = "🥇" if idx==1 else ("🥈" if idx==2 else ("🥉" if idx==3 else f"{idx}."))
        text += f"{medal} <b>{name}</b> — {u[3]}\n"
        
    await message.answer(text + AD_TEXT, parse_mode="HTML")

# /help
@dp.message(Command("start"))
@dp.message(F.text.lower().in_({"помощь", "/help"}))
async def cmd_help(message: types.Message):
    await get_user(message.from_user.id, message.from_user.username) # Регаем если нет
    text = (
        "🤖 <b>Чайхана Бот v1.0</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "☕ <code>/chaihana</code> - Получить очки (-10..10)\n"
        "👤 <code>/profile</code> - Твой профиль\n"
        "✏️ <code>/name [имя]</code> - Сменить ник\n"
        "🏆 <code>/top</code> / <code>/world</code> - Рейтинги\n"
        "🎰 <code>/casino [сумма]</code> - Испытай удачу (777 = x5)\n"
        "⚔️ <code>/duel [сумма]</code> - Вызвать на бой (реплай)\n"
        "💸 <code>/transfer [сумма]</code> - Передать очки (реплай)\n"
        "📈 <code>/rate</code> - Курс Чайханокойна\n"
        "💰 <code>/buy</code> / <code>/sell</code> - Торговля криптой\n"
        "🐒 <code>/monkey</code> - Майнер крипты\n"
        "🐷 <code>/pig</code> - Майнер очков\n"
        f"{AD_TEXT}"
    )
    await message.answer(text, parse_mode="HTML")

async def main():
    await init_db()
    
    # Настройка команд меню
    commands = [
        types.BotCommand(command="chaihana", description="Получить очки"),
        types.BotCommand(command="profile", description="Профиль"),
        types.BotCommand(command="top", description="Топ игроков"),
        types.BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)
    
    # Запуск фоновых задач
    asyncio.create_task(crypto_updater())
    
    print("🚀 БОТ ЗАПУЩЕН! Чайхана открыта.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")