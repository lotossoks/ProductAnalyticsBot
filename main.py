import telebot
import json
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from typing import Dict, Any

# Инициализация бота
TOKEN = config.TOKEN
bot = telebot.TeleBot(TOKEN)

# Константы для callback_data
CALLBACK_MAIN_MENU = "menu"
CALLBACK_MATERIALS = "materials"
CALLBACK_TRAINING = "training"
CALLBACK_FEEDBACK = "feedback"
CALLBACK_ABOUT = "about"
CALLBACK_REFERRAL = "referral"

# Функции для работы с файлами
def load_data(filename: str, default: Dict = {}) -> Dict:
    """Загружает данные из JSON-файла"""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    return default

def save_data(filename: str, data: Dict) -> None:
    """Сохраняет данные в JSON-файл"""
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# Загрузка данных при старте
user_data = load_data("users.json")
app_data = load_data("data.json")
FEEDBACK_FILE = "feedback.txt"

# --- Генерация клавиатур ---
def create_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню"""
    markup = InlineKeyboardMarkup(row_width=1)
    buttons = [
        ("📚 Обучение", CALLBACK_TRAINING),
        ("📂 Материалы", CALLBACK_MATERIALS),
        ("📝 Обратная связь", CALLBACK_FEEDBACK),
        ("ℹ️ О создателях", CALLBACK_ABOUT),
        ("👥 Реферальная программа", CALLBACK_REFERRAL)
    ]
    markup.add(*[InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    return markup

def create_materials_menu(user_id: str) -> InlineKeyboardMarkup:
    """Создает меню доступных материалов"""
    user_level = user_data.get(user_id, {}).get('level', 1)
    markup = InlineKeyboardMarkup(row_width=1)
    
    for topic, details in app_data.get("Материалы", {}).items():
        if user_level >= details.get("Уровень", 1):
            markup.add(InlineKeyboardButton(topic[:20], callback_data=f"mat_{topic[:20]}"))
    
    markup.add(InlineKeyboardButton("« Назад", callback_data=CALLBACK_MAIN_MENU))
    return markup

def create_subtopics_menu(topic: str) -> InlineKeyboardMarkup:
    """Создает меню подтем для выбранного материала"""
    markup = InlineKeyboardMarkup(row_width=1)
    for subtopic in app_data["Материалы"].get(topic, {}):
        markup.add(InlineKeyboardButton(subtopic[:20], callback_data=f"sub_{topic[:15]}_{subtopic[:15]}"))
    markup.add(InlineKeyboardButton("« Назад", callback_data=CALLBACK_MATERIALS))
    return markup

# --- Обработчики команд ---
@bot.message_handler(commands=['start'])
def handle_start(message: telebot.types.Message) -> None:
    """Обработчик команды /start"""
    user_id = str(message.chat.id)
    args = message.text.split()
    referral = args[1] if len(args) > 1 else None

    # Регистрация нового пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            "level": 1,
            "invited": [],
            "completed_lessons": [],
            "referral_name": message.chat.username or f"User_{user_id}"
        }
        
        # Обработка реферала
        if referral:
            for uid, uinfo in user_data.items():
                if (uinfo.get('referral_name') == referral 
                        and uinfo['level'] < 3 
                        and user_id not in uinfo['invited']):
                    uinfo['level'] += 1
                    uinfo['invited'].append(user_id)
                    break
    
    save_data("users.json", user_data)
    
    # Приветственное сообщение
    with open("welcome.jpg", "rb") as photo:
        bot.send_photo(user_id, photo, caption="Добро пожаловать!")
    
    bot.send_message(user_id, "Выберите действие:", reply_markup=create_main_menu())

# --- Обработчик callback-запросов ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call: telebot.types.CallbackQuery) -> None:
    """Обработка всех callback-запросов"""
    user_id = str(call.message.chat.id)
    action = call.data.split('_')[0] if '_' in call.data else call.data

    try:
        handlers = {
            CALLBACK_MAIN_MENU: lambda: bot.edit_message_text(
                "Выберите действие:", 
                chat_id=user_id, 
                message_id=call.message.message_id, 
                reply_markup=create_main_menu()
            ),
            CALLBACK_MATERIALS: lambda: bot.edit_message_text(
                "Доступные материалы:", 
                chat_id=user_id, 
                message_id=call.message.message_id, 
                reply_markup=create_materials_menu(user_id)
            ),
            'mat': lambda: handle_material_selection(call),
            'sub': lambda: handle_subtopic_selection(call),
            CALLBACK_TRAINING: lambda: bot.send_message(
                user_id, 
                "Выберите урок:", 
                reply_markup=create_training_menu(user_id)
            ),
            'lesson': lambda: handle_lesson_selection(call),
            'answer': lambda: handle_quiz_answer(call),
            CALLBACK_FEEDBACK: lambda: request_feedback(call),
            CALLBACK_ABOUT: lambda: bot.send_message(
                user_id, 
                app_data.get("About", "Информация отсутствует")
            ),
            CALLBACK_REFERRAL: lambda: send_referral_link(user_id)
        }
        
        handler = handlers.get(action)
        if handler:
            handler()
        else:
            bot.answer_callback_query(call.id, "Неизвестная команда")

    except Exception as e:
        bot.send_message(user_id, "Произошла ошибка. Попробуйте снова.")
        bot.answer_callback_query(call.id)
        print(f"Ошибка: {e}")

# --- Вспомогательные функции ---
def create_training_menu(user_id: str) -> InlineKeyboardMarkup:
    """Создает меню обучения с учетом уровня пользователя"""
    user_level = user_data.get(user_id, {}).get('level', 1)
    markup = InlineKeyboardMarkup(row_width=1)
    
    for lesson, details in app_data.get("Обучение", {}).items():
        if user_level >= details.get("Уровень", 1):
            status = "✅" if lesson in user_data[user_id].get("completed_lessons", []) else "❌"
            markup.add(InlineKeyboardButton(f"{status} {lesson}", callback_data=f"lesson_{lesson}"))
    
    markup.add(InlineKeyboardButton("« Назад", callback_data=CALLBACK_MAIN_MENU))
    return markup

def send_referral_link(user_id: str) -> None:
    """Отправляет реферальную ссылку пользователя"""
    link = f"https://t.me/product_analitics312_bot?start={user_data[user_id]['referral_name']}"
    bot.send_message(user_id, f"Ваша реферальная ссылка: {link}")

def handle_material_selection(call: telebot.types.CallbackQuery) -> None:
    """Обработка выбора материала"""
    topic = call.data.split('_', 1)[1]
    real_topic = next((t for t in app_data["Материалы"] if t.startswith(topic)), topic)
    bot.edit_message_text(
        f"Выберите подтему в: {real_topic}", 
        chat_id=call.message.chat.id, 
        message_id=call.message.message_id, 
        reply_markup=create_subtopics_menu(real_topic)
    )

def handle_subtopic_selection(call: telebot.types.CallbackQuery) -> None:
    """Обработка выбора подтемы"""
    parts = call.data.split('_', 2)
    topic_part = parts[1]
    subtopic_part = parts[2]
    
    # Поиск полного названия темы и подтемы
    real_topic = next((t for t in app_data["Материалы"] if t.startswith(topic_part)), topic_part)
    real_subtopic = next(
        (s for s in app_data["Материалы"][real_topic] if s.startswith(subtopic_part)),
        subtopic_part
    )
    
    if real_subtopic in app_data["Материалы"][real_topic]:
        content = app_data["Материалы"][real_topic][real_subtopic]
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("« Назад", callback_data=f"mat_{real_topic[:20]}")
        )
        bot.send_message(call.message.chat.id, content, reply_markup=markup)

def handle_lesson_selection(call: telebot.types.CallbackQuery) -> None:
    """Обработка выбора урока"""
    lesson = call.data.split('_', 1)[1]
    lesson_data = app_data["Обучение"].get(lesson)
    
    if lesson_data:
        markup = InlineKeyboardMarkup(row_width=1)
        for answer in lesson_data.get("Ответы", []):
            markup.add(InlineKeyboardButton(answer, callback_data=f"answer_{lesson}_{answer}"))
        bot.send_message(call.message.chat.id, lesson_data["Текст"], reply_markup=markup)

def handle_quiz_answer(call: telebot.types.CallbackQuery) -> None:
    """Проверка ответа на урок"""
    _, lesson, answer = call.data.split('_', 2)
    correct_answer = app_data["Обучение"][lesson]["Правильный ответ"]
    user_id = str(call.message.chat.id)
    
    if answer == correct_answer:
        if lesson not in user_data[user_id]["completed_lessons"]:
            user_data[user_id]["completed_lessons"].append(lesson)
            save_data("users.json", user_data)
        bot.send_message(user_id, "✅ Правильно!", reply_markup=create_retry_menu())
    else:
        bot.send_message(user_id, "❌ Неправильно. Попробуйте еще раз.", reply_markup=create_retry_menu())

def create_retry_menu() -> InlineKeyboardMarkup:
    """Клавиатура после ответа на урок"""
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("Повторить", callback_data=CALLBACK_TRAINING),
        InlineKeyboardButton("« Меню", callback_data=CALLBACK_MAIN_MENU)
    )

def request_feedback(call: telebot.types.CallbackQuery) -> None:
    """Запрашивает отзыв у пользователя"""
    bot.send_message(call.message.chat.id, "Отправьте отзыв:")
    bot.register_next_step_handler(call.message, process_feedback)

def process_feedback(message: telebot.types.Message) -> None:
    """Сохраняет отзыв и отправляет подтверждение"""
    user_id = str(message.chat.id)
    user_link = f"@{message.chat.username}" if message.chat.username else f"tg://user?id={user_id}"
    
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as file:
        file.write(f"{user_link}: {message.text}\n")
    
    bot.send_message(
        user_id, 
        "Спасибо за ваш отзыв!", 
        reply_markup=create_feedback_thank_you_menu()
    )

def create_feedback_thank_you_menu() -> InlineKeyboardMarkup:
    """Клавиатура после отправки отзыва"""
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("Отправить еще один отзыв", callback_data=CALLBACK_FEEDBACK),
        InlineKeyboardButton("« Назад в меню", callback_data=CALLBACK_MAIN_MENU)
    )

# --- Основной цикл ---
if __name__ == "__main__":
    bot.polling(none_stop=True)