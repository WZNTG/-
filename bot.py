import asyncio
import logging
import random
import time
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage

# ⚙️ КОНФИГУРАЦИЯ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
TOKEN = "8542233717:AAEfuFgvdkHLRDMshwzWq885r2dECOiYW0s"
ADMIN_ID = 5394084759
CHANNEL_TAG = "@chaihanabotprom"
DB_NAME = "chaihana_v4.db"

# Текст рекламы/подписи
AD_TEXT = f"\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n📢 <b>Инфо:</b> {CHANNEL_TAG}"

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# 🌍 ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
CRYPTO_PRICE = 100          # Текущий курс
NEXT_FORCED_PRICE = None    # Для скрытого управления ("заказ" цены)
LAST_CRYPTO_UPDATE = 0      # (Оставлено для совместимости)
casino_cooldowns = {}       # Словарь для задержки казино {user_id: time}

# 🛠 РАБОТА С БАЗОЙ ДАННЫХ
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
        # Таблица пользователей
        await self.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            custom_name TEXT,
            points INTEGER DEFAULT 1000,
            coins INTEGER DEFAULT 0,
            monkey_lvl INTEGER DEFAULT 0,
            pig_lvl INTEGER DEFAULT 0,
            last_chaihana INTEGER DEFAULT 0,
            last_farm_monkey INTEGER DEFAULT 0,
            last_farm_pig INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0,
            last_work INTEGER DEFAULT 0
        )""")
        # Таблица промокодов
        await self.execute("""CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            min_val INTEGER,
            max_val INTEGER,
            activations INTEGER DEFAULT 0
        )""")
        # Таблица использованных промокодов
        await self.execute("""CREATE TABLE IF NOT EXISTS used_promos (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )""")

db = Database(DB_NAME)

# 🔄 ФОНОВЫЕ ЗАДАЧИ (КРИПТА)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def crypto_updater():
    """Обновляет курс каждые 1.5 минуты с возможностью скрытого управления"""
    global CRYPTO_PRICE, NEXT_FORCED_PRICE
    
    while True:
        # Ждем 90 секунд (1.5 минуты)
        await asyncio.sleep(90)
        
        # 1. Проверяем, есть ли "заказ" от админа
        if NEXT_FORCED_PRICE is not None:
            CRYPTO_PRICE = NEXT_FORCED_PRICE
            NEXT_FORCED_PRICE = None # Сбрасываем заказ
            logging.info(f"🎭 Скрытая манипуляция: Курс установлен на {CRYPTO_PRICE}")
        
        # 2. Если заказа нет — работает рынок (Рандом)
        else:
            event = random.random()
            
            if event < 0.10:   # 10% шанс КРАХ (-15%...-40%)
                change = random.uniform(-0.40, -0.15)
            elif event < 0.45: # 35% шанс ПАДЕНИЕ (-1%...-7%)
                change = random.uniform(-0.07, -0.01)
            elif event < 0.85: # 40% шанс РОСТ (+1%...+8%)
                change = random.uniform(0.01, 0.08)
            else:              # 15% шанс ПАМП (+20%...+60%)
                change = random.uniform(0.20, 0.60)

            # Рассчитываем новую цену
            new_price = int(CRYPTO_PRICE * (1 + change))
            
            # Ограничители (чтобы не ушло в минус или космос)
            if new_price < 10: CRYPTO_PRICE = 10
            elif new_price > 50000: CRYPTO_PRICE = 50000
            else: CRYPTO_PRICE = new_price
            
            logging.info(f"📈 Рынок обновлен: {CRYPTO_PRICE}")

async def get_user(user_id, username=None):
    """Получает пользователя или создает нового"""
    user = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch="one")
    if not user:
        await db.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        return await get_user(user_id, username)
    # Обновляем юзернейм если сменился
    if username and user['username'] != username:
         await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    return user

# 🎮 ОСНОВНЫЕ КОМАНДЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬

@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    await get_user(message.from_user.id, message.from_user.username)
    text = (
        "🤖 <b>Чайхана Бот v4.0</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "📈 <b>Крипта:</b> Обновляется каждые 1.5 мин!\n"
        "☕ <code>/chaihana</code> — Репутация (раз в час)\n"
        "💼 <code>/work</code> — Работать (монеты)\n"
        "🎰 <code>/casino [ставка]</code> — Поднять бабла\n"
        "💰 <code>/rate</code> — Текущий курс\n"
        "💵 <code>/buy [число]</code> — Купить коины\n"
        "📉 <code>/sell [число]</code> — Продать коины\n"
        "⚔️ <code>/duel [ставка]</code> — Битва с другом\n"
        "👤 <code>/profile</code> — Статистика\n"
        "🎫 <code>/promo [код]</code> — Промокод"
        f"{AD_TEXT}"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("rate"))
async def cmd_rate(message: types.Message):
    await message.answer(
        f"📊 <b>Биржа Чайханы:</b>\n\n"
        f"💰 1 Коин = <b>{CRYPTO_PRICE}</b> очков.\n"
        f"⏳ Курс меняется каждые 90 секунд.\n"
        f"<i>Следи за рынком, возможен крах!</i>"
        f"{AD_TEXT}", parse_mode="HTML"
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = await get_user(message.from_user.id, message.from_user.username)
    # Считаем общее состояние (очки + коины в очках)
    total_wealth = user['points'] + (user['coins'] * CRYPTO_PRICE)
    
    text = (
        f"👤 <b>Профиль:</b> {user['custom_name'] or user['username']}\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🏆 На руках: <b>{user['points']}</b> очков\n"
        f"🪙 Крипта: <b>{user['coins']}</b> монет\n"
        f"💎 Капитал: ≈ <b>{total_wealth}</b> очков"
        f"{AD_TEXT}"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("work"))
async def cmd_work(message: types.Message):
    user = await get_user(message.from_user.id)
    now = int(time.time())
    
    if now - user['last_work'] < 1800: # 30 минут
        rem = 1800 - (now - user['last_work'])
        mins = rem // 60
        await message.answer(f"⏳ Отдохни! Работать можно через {mins} мин.")
        return
    
    earn = random.randint(5, 50)
    await db.execute("UPDATE users SET coins = coins + ?, last_work = ? WHERE user_id = ?", (earn, now, message.from_user.id))
    await message.answer(f"🔨 Ты поработал и получил <b>{earn}</b> коинов!", parse_mode="HTML")

@dp.message(Command("chaihana"))
async def cmd_chaihana(message: types.Message):
    user = await get_user(message.from_user.id)
    now = int(time.time())
    
    if now - user['last_chaihana'] < 3600: # 1 час
        rem = 3600 - (now - user['last_chaihana'])
        mins = rem // 60
        await message.answer(f"⏳ Чай еще горячий! Жди {mins} мин.")
        return
    
    pts = random.randint(10, 150)
    await db.execute("UPDATE users SET points = points + ?, last_chaihana = ? WHERE user_id = ?", (pts, now, message.from_user.id))
    await message.answer(f"☕ Кайфанул в чайхане: <b>+{pts}</b> очков.", parse_mode="HTML")

# 🎰 КАЗИНО (С ЗАДЕРЖКОЙ)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("casino"))
async def cmd_casino(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    now = time.time()
    
    # 1. Проверка кулдауна (3 секунды)
    if user_id in casino_cooldowns:
        last_time = casino_cooldowns[user_id]
        if now - last_time < 3:
            wait = round(3 - (now - last_time), 1)
            await message.answer(f"⏳ Не части! Подожди {wait} сек.")
            return

    # 2. Парсинг ставки
    try:
        bet = int(command.args)
    except:
        await message.answer("🎰 Используй: <code>/casino 100</code>", parse_mode="HTML")
        return

    if bet < 10:
        await message.answer("❌ Минимальная ставка 10.")
        return

    user = await get_user(user_id)
    if user['points'] < bet:
        await message.answer("❌ Не хватает очков.")
        return

    # 3. Записываем время использования и списываем ставку
    casino_cooldowns[user_id] = now
    await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (bet, user_id))
    
    # 4. Игра
    msg = await message.answer_dice(emoji="🎰")
    await asyncio.sleep(2.5)
    val = msg.dice.value

    coeff = 0
    if val == 64: coeff = 10      # Три семерки
    elif val in [1, 22, 43]: coeff = 3 # Фрукты
    elif val in [16, 32, 48]: coeff = 1.5 # Бары

    if coeff > 0:
        win = int(bet * coeff)
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user_id))
        await message.answer(f"🎉 <b>ПОБЕДА x{coeff}!</b>\nТы выиграл {win} очков!", parse_mode="HTML")
    else:
        await message.answer(f"📉 Ты проиграл {bet} очков.", parse_mode="HTML")

# 💸 ТОРГОВЛЯ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message, command: CommandObject):
    if not command.args: 
        await message.answer("🛒 Пример: <code>/buy 10</code>", parse_mode="HTML")
        return
    
    user = await get_user(message.from_user.id)
    
    try:
        if command.args.lower() in ["все", "all", "всё"]:
            count = user['points'] // CRYPTO_PRICE
        else:
            count = int(command.args)
    except: return

    if count <= 0: return
    cost = count * CRYPTO_PRICE
    
    if user['points'] < cost:
        await message.answer(f"❌ Не хватает очков. Нужно: {cost}")
        return

    await db.execute("UPDATE users SET points = points - ?, coins = coins + ? WHERE user_id = ?", (cost, count, message.from_user.id))
    await message.answer(f"✅ Куплено <b>{count}</b> коинов за {cost} очков.", parse_mode="HTML")

@dp.message(Command("sell"))
async def cmd_sell(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("🛒 Пример: <code>/sell 10</code>", parse_mode="HTML")
        return
        
    user = await get_user(message.from_user.id)
    
    try:
        if command.args.lower() in ["все", "all", "всё"]:
            count = user['coins']
        else:
            count = int(command.args)
    except: return

    if count <= 0 or user['coins'] < count:
        await message.answer("❌ У тебя нет столько монет.")
        return

    profit = count * CRYPTO_PRICE
    await db.execute("UPDATE users SET coins = coins - ?, points = points + ? WHERE user_id = ?", (count, profit, message.from_user.id))
    await message.answer(f"✅ Продано <b>{count}</b> коинов за {profit} очков.", parse_mode="HTML")

# ⚔️ ДУЭЛИ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("duel"))
async def cmd_duel(message: types.Message, command: CommandObject):
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        await message.answer("⚔️ Ответь командой на сообщение другого игрока.")
        return
    
    try:
        bet = int(command.args)
    except:
        await message.answer("⚔️ Укажи ставку: <code>/duel 100</code>", parse_mode="HTML")
        return

    if bet < 1: return

    user = await get_user(message.from_user.id)
    target_id = message.reply_to_message.from_user.id
    target = await get_user(target_id) # Создаем если нет

    if user['points'] < bet:
        await message.answer("❌ У тебя нет денег.")
        return
    if target['points'] < bet:
        await message.answer("❌ У соперника нет денег.")
        return

    # Клавиатура
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"duel:yes:{bet}:{message.from_user.id}")
    kb.button(text="❌ Отмена", callback_data=f"duel:no:{bet}:{message.from_user.id}")

    await message.answer(
        f"⚔️ <b>ВЫЗОВ!</b>\n{message.from_user.first_name} против {message.reply_to_message.from_user.first_name}\n💰 Ставка: {bet}",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("duel:"))
async def duel_cb(callback: CallbackQuery):
    action, bet, challenger_id = callback.data.split(":")[1:]
    bet = int(bet)
    challenger_id = int(challenger_id)
    
    # Отменить может только вызывающий
    if action == "no":
        if callback.from_user.id == challenger_id:
            await callback.message.edit_text("🚫 Дуэль отменена.")
        else:
            await callback.answer("Это может сделать только тот, кто вызывал!", show_alert=True)
        return

    # Принять может кто угодно (для простоты) или нужно проверять reply (сложнее)
    # Здесь упростим: тот кто нажал Принять - становится соперником
    if action == "yes":
        if callback.from_user.id == challenger_id:
            await callback.answer("Сам с собой нельзя!", show_alert=True)
            return
            
        p1 = await get_user(challenger_id)
        p2 = await get_user(callback.from_user.id)
        
        if p1['points'] < bet or p2['points'] < bet:
            await callback.message.edit_text("❌ У кого-то кончились деньги.")
            return

        await callback.message.edit_text(f"🎲 <b>БИТВА НАЧАЛАСЬ!</b>\nСтавка: {bet}")
        
        d1 = await callback.message.answer_dice("🎲")
        d2 = await callback.message.answer_dice("🎲")
        await asyncio.sleep(4)
        
        v1 = d1.dice.value
        v2 = d2.dice.value
        
        if v1 > v2:
            winner, loser = challenger_id, callback.from_user.id
            res = "🏆 Победил вызывавший!"
        elif v2 > v1:
            winner, loser = callback.from_user.id, challenger_id
            res = "🏆 Победил принявший!"
        else:
            await callback.message.answer("🤝 Ничья! Расходимся.")
            return
            
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (bet, winner))
        await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (bet, loser))
        await callback.message.answer(f"{res}\n💰 Выигрыш: {bet} очков.")

# 🎫 ПРОМОКОДЫ
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
@dp.message(Command("promo"))
async def cmd_promo(message: types.Message, command: CommandObject):
    if not command.args: return
    code = command.args.strip().upper()
    
    # Ищем код
    promo = await db.execute("SELECT * FROM promos WHERE code = ?", (code,), fetch="one")
    if not promo:
        await message.answer("❌ Код не найден.")
        return
    
    # Проверяем, юзал ли
    used = await db.execute("SELECT * FROM used_promos WHERE user_id = ? AND code = ?", (message.from_user.id, code), fetch="one")
    if used:
        await message.answer("❌ Ты уже вводил этот код.")
        return

    # Награда
    rew = random.randint(promo['min_val'], promo['max_val'])
    
    await db.execute("INSERT INTO used_promos VALUES (?, ?)", (message.from_user.id, code))
    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (rew, message.from_user.id))
    await db.execute("UPDATE promos SET activations = activations + 1 WHERE code = ?", (code,))
    
    await message.answer(f"✅ <b>Успех!</b>\nПолучено: {rew} очков.{AD_TEXT}", parse_mode="HTML")

# 👑 АДМИНКА (СКРЫТОЕ УПРАВЛЕНИЕ)
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬

@dp.message(Command("nextrate"))
async def adm_nextrate(message: types.Message, command: CommandObject):
    """Скрыто установить цену на следующее обновление"""
    if message.from_user.id != ADMIN_ID: return
    try:
        global NEXT_FORCED_PRICE
        NEXT_FORCED_PRICE = int(command.args)
        
        # Удаляем следы
        msg = await message.answer("🤫") # Просто мигаем
        await asyncio.sleep(1)
        await message.delete() # Удаляем команду админа
        await msg.delete()     # Удаляем ответ бота
    except: pass

@dp.message(Command("setrate"))
async def adm_setrate(message: types.Message, command: CommandObject):
    """Явно установить цену сейчас"""
    if message.from_user.id != ADMIN_ID: return
    try:
        global CRYPTO_PRICE
        CRYPTO_PRICE = int(command.args)
        await message.answer(f"🛠 Админ установил курс: {CRYPTO_PRICE}")
    except: pass

@dp.message(Command("pump"))
async def adm_pump(message: types.Message, command: CommandObject):
    """Памп/Дамп: /pump 0.5 или /pump -0.5"""
    if message.from_user.id != ADMIN_ID: return
    try:
        global CRYPTO_PRICE
        mult = float(command.args)
        CRYPTO_PRICE = int(CRYPTO_PRICE * (1 + mult))
        if CRYPTO_PRICE < 10: CRYPTO_PRICE = 10
        await message.answer(f"⚠️ РЫНОК ШТОРМИТ! Цена: {CRYPTO_PRICE}")
    except: pass

@dp.message(Command("addpromo"))
async def adm_addpromo(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    try:
        # /addpromo CODE MIN MAX
        args = command.args.split()
        code, min_v, max_v = args[0].upper(), int(args[1]), int(args[2])
        await db.execute("INSERT OR REPLACE INTO promos (code, min_val, max_val) VALUES (?, ?, ?)", (code, min_v, max_v))
        await message.answer(f"✅ Промокод {code} создан ({min_v}-{max_v}).")
    except:
        await message.answer("❌ Ошибка. Формат: /addpromo CODE MIN MAX")

# 🚀 ЗАПУСК
# ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
async def main():
    await db.init_tables()
    
    # Запуск фоновой задачи обновления крипты
    asyncio.create_task(crypto_updater())
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 БОТ ЗАПУЩЕН! (v4.0 Full)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
