import sqlite3
from telebot import TeleBot, types
import csv
import os
from io import StringIO
from datetime import datetime, date
import threading
import time

# --- Настройки бота ---
API_TOKEN = '7827212867:AAFal1er6Z_voA_HgLA-pz1bM_yhl2jAGQI'
YOUR_ADMIN_ID = 1200223081  # Замените на ID администратора
bot = TeleBot(API_TOKEN)
print("START===")

# --- Подключение к базе данных ---
DB_FILE = 'referrals.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# --- Инициализация базы данных ---
def init_db():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0,
        hold_balance REAL DEFAULT 0,
        referrer_id INTEGER,
        referrals_count INTEGER DEFAULT 0
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        channel_id INTEGER PRIMARY KEY,
        channel_name TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stats (
        date TEXT PRIMARY KEY,
        new_users INTEGER DEFAULT 0,
        top_users TEXT
    )
    ''')
    conn.commit()

# Вызываем инициализацию при старте
init_db()

# --- Проверка подписки ---
def check_subscription(user_id):
    cursor.execute("SELECT channel_id, channel_name FROM channels")
    channels = cursor.fetchall()
    if not channels:
        return True
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton(text=f"Подписаться на @{channel[1]}", url=f"https://t.me/{channel[1]}") for channel in channels]
    buttons.append(types.InlineKeyboardButton(text="Проверить подписку", callback_data="check_subs"))
    markup.add(*buttons)
    
    for channel in channels:
        try:
            member = bot.get_chat_member(channel[0], user_id)
            if member.status not in ['member', 'creator', 'administrator']:
                bot.send_message(user_id, "⚠️ Для использования бота необходимо подписаться на наши каналы:", reply_markup=markup)
                return False
        except Exception as e:
            bot.send_message(user_id, f"⚠️ Произошла ошибка при проверке подписки: {e}")
            return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def check_subs_callback(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        bot.send_message(user_id, "✅ Вы успешно подписались на все каналы! Теперь вы можете использовать бота.")
        start_command(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Вы не подписаны на все каналы. Пожалуйста, проверьте подписку.", show_alert=True)

# --- Основные команды ---
@bot.message_handler(commands=['start'])
def start_command(message):
    if not check_subscription(message.from_user.id):
        return
    
    user_id = message.from_user.id
    referrer_id = None
    
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                bot.send_message(user_id, "❌ Вы не можете пригласить сами себя.")
                return
        except ValueError:
            pass
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()
        
        # Обновляем статистику новых пользователей
        today = date.today().isoformat()
        cursor.execute("INSERT OR IGNORE INTO stats (date, new_users) VALUES (?, 0)", (today,))
        cursor.execute("UPDATE stats SET new_users = new_users + 1 WHERE date = ?", (today,))
        conn.commit()
        
        if referrer_id:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (referrer_id,))
            referrer = cursor.fetchone()
            if referrer:
                cursor.execute(
                    "UPDATE users SET hold_balance = hold_balance + 0.5, referrals_count = referrals_count + 1 WHERE user_id = ?",
                    (referrer_id,)
                )
                conn.commit()
                bot.send_message(
                    referrer_id,
                    f"✨ У вас новый реферал! На ваш холд добавлено 0.5 звезды. Чтобы они были зачислены на основной баланс, ваш друг должен пригласить хотя бы одного друга."
                )
    
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("⭐ Заработать звезды", "💸 Вывод")
    markup.add("📊 Статистика", "🏆 Топ", "ℹ️ Помощь")
    
    bot.send_message(
        user_id, 
        f"""
👋 Добро пожаловать, {message.from_user.first_name}!
Приглашайте друзей и зарабатывайте звезды! ⭐
🔗 Ваша реферальная ссылка:
{referral_link}
💰 За каждого приглашенного вы получите 0.5 звезды (после выполнения условий).
        """,
        reply_markup=markup
    )
    
    if referrer_id:
        check_and_unlock(referrer_id)

def check_and_unlock(referrer_id):
    cursor.execute("SELECT user_id FROM users WHERE referrer_id = ?", (referrer_id,))
    referrals = cursor.fetchall()
    for referral in referrals:
        cursor.execute("SELECT referrals_count FROM users WHERE user_id = ?", (referral[0],))
        sub_referrals = cursor.fetchone()
        if sub_referrals and sub_referrals[0] > 0:
            cursor.execute("SELECT hold_balance FROM users WHERE user_id = ?", (referrer_id,))
            user = cursor.fetchone()
            if user and user[0] > 0:
                hold_balance = user[0]
                cursor.execute(
                    "UPDATE users SET balance = balance + ?, hold_balance = 0 WHERE user_id = ?",
                    (hold_balance, referrer_id),
                )
                conn.commit()
                bot.send_message(
                    referrer_id,
                    f"✅ {hold_balance:.1f} звезд были разблокированы и добавлены на ваш основной баланс!"
                )
                break
    cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (referrer_id,))
    grand_referrer = cursor.fetchone()
    if grand_referrer and grand_referrer[0]:
        check_and_unlock(grand_referrer[0])

@bot.message_handler(func=lambda message: message.text == "⭐ Заработать звезды")
def show_balance_with_referral(message):
    user_id = message.from_user.id
    cursor.execute("SELECT balance, hold_balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        bot.send_message(user_id, "Вы не зарегистрованы. Нажмите /start.")
        return
    
    balance, hold_balance = user
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    text = (
        "👤 Реферальная программа\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 Реф. ссылка: {referral_link}\n"
        "Приглашай по ней друзей и зарабатывай звезды!\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"Баланс:\nАктивный - {balance:.1f} звезд\nВ холде - {hold_balance:.1f} звезд\n"
        "➖➖➖➖➖➖➖➖➖➖"
    )
    
    try:
        with open('photo.jpg', 'rb') as photo_file:
            bot.send_photo(user_id, photo_file, caption=text)
    except FileNotFoundError:
        bot.send_message(user_id, "❌ Файл photo.jpg не найден. Пожалуйста, убедитесь, что файл существует.")
        bot.send_message(user_id, text)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Помощь")
def help_command(message):
    bot.send_message(
        message.from_user.id,
        """
📋 Справка:
- Приглашайте друзей с помощью вашей реферальной ссылки.
- Получайте 0.5 звезды за каждого приглашенного друга (после выполнения условий).
- Звезды из холда разблокируются автоматически, если приглашенный друг приглашает хотя бы одного друга.
Команды:
- "⭐ Заработать звезды" – Узнать ваш баланс и реферальную ссылку.
- "📊 Статистика" – Посмотреть свою статистику рефералов.
- "🏆 Топ" – Посмотреть топ рефереров.
- "💸 Вывод" – Отправить запрос на вывод средств (от 15 звезд после выполнения условий). \n
 Разработка команды @impaermax (Телеграм боты, GPT, внедрение ИИ)
        """
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def stats_command(message):
    user_id = message.from_user.id
    cursor.execute("""
        SELECT referrals_count, 
               (SELECT COUNT(*) FROM users WHERE referrer_id = ? AND referrals_count > 0) AS active_referrals
        FROM users WHERE user_id = ?
    """, (user_id, user_id))
    stats = cursor.fetchone()
    if stats:
        referrals_count, active_referrals = stats
        bot.send_message(user_id, f"📊 Ваша статистика:\n"
                                  f"👥 Приглашено друзей: {referrals_count}\n"
                                  f"✅ Из них активных: {active_referrals}")
    else:
        bot.send_message(user_id, "Вы не зарегистрованы. Нажмите /start.")

@bot.message_handler(func=lambda message: message.text == "🏆 Топ")
def leaderboard_command(message):
    cursor.execute("SELECT user_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT 10")
    leaders = cursor.fetchall()
    leaderboard_text = "🏆 Топ рефереров:\n"
    for idx, (user_id, count) in enumerate(leaders, 1):
        try:
            user_info = bot.get_chat(user_id)
            name = user_info.first_name or "Unknown"
        except:
            name = "Unknown"
        leaderboard_text += f"{idx}. {name} - {count} рефералов\n"
    bot.send_message(message.chat.id, leaderboard_text)

@bot.message_handler(func=lambda message: message.text == "💸 Вывод")
def withdraw_request(message):
    user_id = message.from_user.id
    cursor.execute("""
        SELECT balance, 
               (SELECT COUNT(*) FROM users WHERE referrer_id = ?) AS total_referrals,
               (SELECT COUNT(*) FROM users WHERE referrer_id = ? AND referrals_count > 0) AS active_referrals
        FROM users WHERE user_id = ?
    """, (user_id, user_id, user_id))
    data = cursor.fetchone()
    
    if not data or data[1] < 15 or data[2] < 15:
        bot.send_message(user_id, "❌ Для вывода необходимо пригласить минимум 15 активных друзей.")
        return
    
    balance = data[0]
    if balance < 15:
        bot.send_message(user_id, "❌ Минимальная сумма для вывода - 15 звезд.")
        return
    
    bot.send_message(user_id, "✏️ Введите ваш юзернейм для вывода звёзд:")
    bot.register_next_step_handler(message, process_withdraw_request)

def process_withdraw_request(message):
    username = message.text
    user_id = message.from_user.id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    
    bot.send_message(YOUR_ADMIN_ID, f"-New Withdraw Request-\n"
                                    f"User: @{username} ({user_id})\n"
                                    f"Balance: {balance:.1f} stars")
    bot.send_message(user_id, f"📝 Ваша заявка на вывод отправлена администраторам.\n"
                              f"Баланс: {balance:.1f} звезд\n"
                              f"Свяжитесь с администратором для подтверждения: @GromovALX")

# --- Админ-панель ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id != YOUR_ADMIN_ID:
        bot.send_message(user_id, "❌ У вас нет прав доступа к админ-панели.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👥 Статистика пользователей", "📝 Рассылка")
    markup.add("⚙️ Управление каналами")
    markup.add("📥 Выгрузить базу данных")
    markup.add("🏠 Главное меню")
    
    bot.send_message(user_id, "👨‍💻 Админ-панель:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "👥 Статистика пользователей" and message.from_user.id == YOUR_ADMIN_ID)
def users_stats(message):
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrals_count > 0")
    active_users = cursor.fetchone()[0]
    
    bot.send_message(
        message.chat.id,
        f"📊 Статистика пользователей:\n"
        f"👥 Всего зарегистрованных: {total_users}\n"
        f"✅ Активных (с рефералами): {active_users}"
    )

@bot.message_handler(func=lambda message: message.text == "📝 Рассылка" and message.from_user.id == YOUR_ADMIN_ID)
def start_mailing(message):
    bot.send_message(message.chat.id, "Отправьте сообщение для рассылки (текст + фото можно отправить как альбом):")
    bot.register_next_step_handler(message, process_mailing)

def process_mailing(message):
    if message.content_type == 'text':
        text = message.text
        photo_id = None
    elif message.content_type == 'photo':
        text = message.caption
        photo_id = message.photo[-1].file_id
    else:
        bot.send_message(message.chat.id, "❌ Неподдерживаемый тип контента.")
        return
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    success_count = 0
    for user in users:
        try:
            if photo_id:
                bot.send_photo(user[0], photo_id, caption=text)
            else:
                bot.send_message(user[0], text)
            success_count += 1
        except:
            pass
    
    bot.send_message(message.chat.id, f"✅ Рассылка завершена. Доставлено: {success_count} из {len(users)}")

@bot.message_handler(func=lambda message: message.text == "⚙️ Управление каналами" and message.from_user.id == YOUR_ADMIN_ID)
def manage_channels(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Добавить канал", "❌ Удалить канал")
    markup.add("📋 Список каналов", "🏠 Главное меню")
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "➕ Добавить канал" and message.from_user.id == YOUR_ADMIN_ID)
def add_channel(message):
    bot.send_message(message.chat.id, "Отправьте ссылку на канал в формате @channel_username или https://t.me/channel_username:")
    bot.register_next_step_handler(message, process_add_channel)

def process_add_channel(message):
    channel_link = message.text.strip()
    if not channel_link.startswith('@') and not channel_link.startswith('https://t.me/'):
        bot.send_message(message.chat.id, "❌ Некорректный формат ссылки. Используйте @channel_username или https://t.me/channel_username.")
        return
    
    channel_name = channel_link.replace('https://t.me/', '').replace('@', '').strip()
    try:
        chat = bot.get_chat(f"@{channel_name}")
        member = bot.get_chat_member(chat.id, bot.get_me().id)
        if member.status != 'administrator':
            bot.send_message(message.chat.id, f"❌ Бот не является администратором канала {chat.title}.")
            return
        
        cursor.execute("INSERT OR IGNORE INTO channels (channel_id, channel_name) VALUES (?, ?)", (chat.id, chat.username))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Канал {chat.title} успешно добавлен.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Не удалось добавить канал. Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "❌ Удалить канал" and message.from_user.id == YOUR_ADMIN_ID)
def remove_channel(message):
    cursor.execute("SELECT channel_id, channel_name FROM channels")
    channels = cursor.fetchall()
    if not channels:
        bot.send_message(message.chat.id, "❌ Список каналов пуст.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for channel_id, channel_name in channels:
        markup.add(types.InlineKeyboardButton(f"@{channel_name}", callback_data=f"remove_channel_{channel_id}"))
    
    bot.send_message(message.chat.id, "Выберите канал для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_channel_"))
def process_remove_channel(call):
    channel_id = int(call.data.split("_")[2])
    try:
        cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        conn.commit()
        bot.answer_callback_query(call.id, f"Канал удален.")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(call.message.chat.id, f"✅ Канал успешно удален.")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка при удалении канала: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "📋 Список каналов" and message.from_user.id == YOUR_ADMIN_ID)
def list_channels(message):
    cursor.execute("SELECT channel_name FROM channels")
    channels = cursor.fetchall()
    if not channels:
        bot.send_message(message.chat.id, "❌ Список каналов пуст.")
        return
    
    channels_text = "Список каналов:\n" + "\n".join([f"- @{channel[0]}" for channel in channels])
    bot.send_message(message.chat.id, channels_text)

@bot.message_handler(func=lambda message: message.text == "🏠 Главное меню" and message.from_user.id == YOUR_ADMIN_ID)
def back_to_main_menu(message):
    admin_panel(message)

@bot.message_handler(func=lambda message: message.text == "📥 Выгрузить базу данных" and message.from_user.id == YOUR_ADMIN_ID)
def export_database(message):
    export_users_db(message.chat.id)

# --- Ежедневная выгрузка и статистика ---
def export_users_db(chat_id):
    try:
        cursor.execute("""
            SELECT user_id, balance, hold_balance, referrer_id, referrals_count,
                   (SELECT COUNT(*) FROM users u2 WHERE u2.referrer_id = users.user_id AND u2.referrals_count > 0) AS active_referrals
            FROM users
        """)
        users_data = cursor.fetchall()
        if not users_data:
            bot.send_message(chat_id, "❌ База данных пользователей пуста.")
            return

        csv_buffer = StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerow(["User ID", "Balance", "Hold Balance", "Referrer ID", "Referrals Count", "Active Referrals"])
        
        for user in users_data:
            user_id, balance, hold_balance, referrer_id, referrals_count, active_referrals = user
            csv_writer.writerow([
                user_id, f"{balance:.1f}", f"{hold_balance:.1f}", 
                referrer_id if referrer_id else "None", referrals_count, active_referrals
            ])
        
        csv_buffer.seek(0)
        file_name = f"users_db_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        bot.send_document(
            chat_id, 
            document=csv_buffer.getvalue().encode('utf-8'), 
            visible_file_name=file_name,
            caption="📊 Ежедневная выгрузка базы данных пользователей"
        )
        csv_buffer.close()
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка при выгрузке базы данных: {str(e)}")

def send_daily_stats():
    while True:
        now = datetime.now()
        # Отправка в 00:00 каждый день
        if now.hour == 0 and now.minute == 0:
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE referrals_count > 0")
            active_users = cursor.fetchone()[0]
            today = date.today().isoformat()
            cursor.execute("SELECT new_users FROM stats WHERE date = ?", (today,))
            new_users = cursor.fetchone()
            new_users_count = new_users[0] if new_users else 0
            
            bot.send_message(
                YOUR_ADMIN_ID,
                f"📊 Ежедневная статистика ({today}):\n"
                f"👥 Всего пользователей: {total_users}\n"
                f"✅ Активных: {active_users}\n"
                f"🆕 Новых за день: {new_users_count}"
            )
            export_users_db(YOUR_ADMIN_ID)
        time.sleep(60)  # Проверка каждую минуту

# Запуск ежедневной статистики в отдельном потоке
threading.Thread(target=send_daily_stats, daemon=True).start()

# --- Основной цикл с уведомлением при падении ---
if __name__ == '__main__':
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        bot.send_message(YOUR_ADMIN_ID, f"⚠️ Бот упал: {str(e)}")
        raise  # Повторно вызываем исключение, чтобы увидеть его в консоли
