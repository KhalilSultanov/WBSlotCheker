import logging
import asyncio
import time
import traceback

from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import TELEGRAM_BOT_TOKEN
from utils import get_acceptance_coefficients

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("bot_errors.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Максимальная длина сообщения в Telegram (безопасный лимит)
MAX_MESSAGE_LENGTH = 4000

# Список коэффициентов для выбора
COEFFICIENTS = list(range(0, 21))  # От 0 до 20 включительно

# Разрешённые ID пользователей
ALLOWED_USERS = [
    1391599879,
    466813055,
    1856114011,
    5495630544,
    893576709,
]  # Добавьте сюда разрешённые ID пользователей

# Список складов с информацией
WAREHOUSES = [
    {
        "ID": 2737, "name": "Санкт-Петербург (Уткина Заводь)",
        "address": "Всеволожский р-н, г.п. Свердловское, дер. Новосаратовка, участок № 1 (промзона Уткина Заводь, комплекс МЛП, корпус 4, парадная 4)",
        "workTime": "24/7", "acceptsQR": True},
    {"ID": 117986, "name": "📦 Казань",
     "address": "Республика Татарстан, Зеленодольск, промышленный парк Зеленодольск, 20", "workTime": "24/7",
     "acceptsQR": False},
    {"ID": 208277, "name": "📦 Невинномысск", "address": "ул. Тимирязева 16", "workTime": "24/7", "acceptsQR": True},
    {"ID": 507, "name": "📦 Коледино", "address": "дер. Коледино, ул. Троицкая, 20", "workTime": "24/7",
     "acceptsQR": True},
    {"ID": 1733, "name": "📦 Екатеринбург - Испытателей 14г", "address": "ул. Испытателей, 14Г", "workTime": "24/7",
     "acceptsQR": True},
    {"ID": 686, "name": "📦 Новосибирск", "address": "ул. Петухова, 71", "workTime": "24/7", "acceptsQR": False
     },
    {"ID": 206348, "name": "📦 Тула", "address": "Тульская область, муниципальное образование Алексин, 1",
     "workTime": "24/7", "acceptsQR": True}
]

# Словарь для хранения данных пользователей
user_data = {}


class AuthorizationMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get('event_from_user')
        if user is None:
            # Если пользователь не определен, можно либо заблокировать, либо разрешить
            return await handler(event, data)

        user_id = user.id

        if user_id not in ALLOWED_USERS:
            if event.message:
                await event.message.answer("🚫 У вас нет доступа к этому боту.")
            elif event.callback_query:
                await event.callback_query.answer("🚫 У вас нет доступа к этому боту.", show_alert=True)
            return  # Останавливаем дальнейшую обработку

        return await handler(event, data)


# Регистрируем middleware авторизации
dp.update.middleware.register(AuthorizationMiddleware())


# Стартовая команда для запроса складов
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    user_data[chat_id] = {
        'selected_warehouses': [],
        'selected_coefficients': {},
        'known_coeffs': {},
        'last_message_id': None,
        'last_keyboard': None,
        'current_warehouse_index': 0,
        'setup_complete': False  # Инициализируем флаг настройки
    }

    # Отправляем сообщение с инлайн-кнопками для выбора складов
    await send_warehouse_selection(chat_id, message)

    # Добавляем кнопку подтверждения
    confirm_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Подтвердить выбор складов")]],
        resize_keyboard=True
    )
    await message.answer("📋 Нажмите кнопку, чтобы подтвердить выбор складов:", reply_markup=confirm_keyboard)


# Функция для отправки инлайн-кнопок для выбора складов
async def send_warehouse_selection(chat_id: int, message: types.Message):
    keyboard_builder = InlineKeyboardBuilder()

    for warehouse in WAREHOUSES:
        action_text = "❌ Удалить" if warehouse['ID'] in user_data[chat_id]['selected_warehouses'] else "✅ Добавить"
        keyboard_builder.button(
            text=f"{action_text} {warehouse['name']}",
            callback_data=f"toggle_warehouse_{warehouse['ID']}"
        )

    # Организуем кнопки в столбик
    keyboard_builder.adjust(1)

    inline_keyboard = keyboard_builder.as_markup()

    if user_data[chat_id]['last_message_id'] is None:
        sent_message = await message.answer("🛒 Выберите склады для отслеживания:", reply_markup=inline_keyboard)
        user_data[chat_id]['last_message_id'] = sent_message.message_id
        user_data[chat_id]['last_keyboard'] = inline_keyboard
    else:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=user_data[chat_id]['last_message_id'],
                reply_markup=inline_keyboard
            )
            user_data[chat_id]['last_keyboard'] = inline_keyboard
        except Exception as e:
            logging.error(f"Ошибка при обновлении инлайн-кнопок: {e}")


# Обработка выбора склада через инлайн-кнопки
@dp.callback_query(lambda call: call.data.startswith("toggle_warehouse_"))
async def process_inline_warehouse_selection(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    warehouse_id = int(callback_query.data.split("_")[2])

    # Добавляем или удаляем склад из выбранных
    if warehouse_id not in user_data[chat_id]['selected_warehouses']:
        user_data[chat_id]['selected_warehouses'].append(warehouse_id)
        await callback_query.answer(f"📦 Склад добавлен в отслеживаемые.")
    else:
        user_data[chat_id]['selected_warehouses'].remove(warehouse_id)
        # Удаляем выбранные коэффициенты для этого склада
        user_data[chat_id]['selected_coefficients'].pop(warehouse_id, None)
        await callback_query.answer(f"📦 Склад удален из отслеживаемых.")

    # Обновляем инлайн-кнопки с актуальным состоянием
    await send_warehouse_selection(chat_id, callback_query.message)


# Подтверждение выбора складов
@dp.message(lambda message: message.text == "✅ Подтвердить выбор складов")
async def confirm_warehouse_selection(message: types.Message):
    chat_id = message.chat.id
    selected_warehouses_ids = user_data[chat_id]['selected_warehouses']

    if selected_warehouses_ids:
        # Переходим к выбору коэффициентов для каждого склада
        user_data[chat_id]['current_warehouse_index'] = 0  # Сбрасываем индекс склада
        await send_coefficient_selection(chat_id, message)
    else:
        await message.answer("Вы не выбрали ни одного склада.")


# Функция для отправки инлайн-кнопок для выбора коэффициентов
async def send_coefficient_selection(chat_id: int, message: types.Message):
    try:
        warehouse_index = user_data[chat_id]['current_warehouse_index']
        selected_warehouses = user_data[chat_id]['selected_warehouses']

        warehouse_id = selected_warehouses[warehouse_index]
        warehouse = next((w for w in WAREHOUSES if w['ID'] == warehouse_id), {})
        warehouse_name = warehouse.get('name', 'Неизвестный склад')

        keyboard_builder = InlineKeyboardBuilder()

        for coeff in COEFFICIENTS:
            action_text = "❌" if coeff in user_data[chat_id].get('selected_coefficients', {}).get(warehouse_id,
                                                                                                  []) else "✅"
            keyboard_builder.button(
                text=f"{action_text} {coeff}",
                callback_data=f"toggle_coefficient_{warehouse_id}_{coeff}"
            )

        # Организуем кнопки в два столбца
        keyboard_builder.adjust(2)

        # Навигационные кнопки
        navigation_buttons = []

        if warehouse_index > 0:
            back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_warehouse")
            navigation_buttons.append(back_button)

        if warehouse_index < len(selected_warehouses) - 1:
            next_button = InlineKeyboardButton(text="➡️ Далее", callback_data="next_warehouse")
            navigation_buttons.append(next_button)
        else:
            confirm_button = InlineKeyboardButton(
                text="✅ Подтвердить выбор коэффициентов",
                callback_data="confirm_coefficients"
            )
            navigation_buttons.append(confirm_button)

        # Добавляем дополнительные кнопки "Главное Меню"
        main_menu_button = InlineKeyboardButton(text="🏠 Главное Меню", callback_data="main_menu")
        navigation_buttons.append(main_menu_button)

        # Добавляем навигационные кнопки в клавиатуру
        keyboard_builder.row(*navigation_buttons)

        inline_keyboard = keyboard_builder.as_markup()

        # Отправляем или обновляем сообщение
        if user_data[chat_id]['last_message_id'] is None:
            sent_message = await message.answer(
                f"🔢 Выберите коэффициенты для склада <b>{warehouse_name}</b>:",
                reply_markup=inline_keyboard
            )
            user_data[chat_id]['last_message_id'] = sent_message.message_id
            user_data[chat_id]['last_keyboard'] = inline_keyboard
        else:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=user_data[chat_id]['last_message_id'],
                    text=f"🔢 Выберите коэффициенты для склада <b>{warehouse_name}</b>:",
                    reply_markup=inline_keyboard
                )
                user_data[chat_id]['last_keyboard'] = inline_keyboard
            except Exception as e:
                logging.error(f"Ошибка при обновлении инлайн-кнопок коэффициентов: {e}")
    except Exception as e:
        logging.error(f"Ошибка в функции send_coefficient_selection: {e}")
        await bot.send_message(chat_id, "Произошла ошибка при отображении коэффициентов. Пожалуйста, попробуйте снова.")


# Обработка выбора коэффициентов через инлайн-кнопки
@dp.callback_query(lambda call: call.data.startswith("toggle_coefficient_"))
async def process_inline_coefficient_selection(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    data_parts = callback_query.data.split("_")
    warehouse_id = int(data_parts[2])
    coefficient = int(data_parts[3])

    # Добавляем или удаляем коэффициент из выбранных для данного склада
    selected_coeffs = user_data[chat_id].setdefault('selected_coefficients', {}).setdefault(warehouse_id, [])
    if coefficient not in selected_coeffs:
        selected_coeffs.append(coefficient)
        await callback_query.answer(f"➕ Коэффициент {coefficient} добавлен.")
    else:
        selected_coeffs.remove(coefficient)
        await callback_query.answer(f"➖ Коэффициент {coefficient} удален.")

    # Обновляем инлайн-кнопки с актуальным состоянием
    await send_coefficient_selection(chat_id, callback_query.message)


# Обработка навигационных кнопок
@dp.callback_query(lambda call: call.data in ["next_warehouse", "prev_warehouse", "main_menu"])
async def process_navigation(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    action = callback_query.data

    if action == "next_warehouse":
        warehouse_index = user_data[chat_id]['current_warehouse_index']
        selected_warehouses = user_data[chat_id]['selected_warehouses']
        warehouse_id = selected_warehouses[warehouse_index]

        # Проверяем, выбраны ли коэффициенты для текущего склада
        selected_coeffs = user_data[chat_id]['selected_coefficients'].get(warehouse_id, [])
        if not selected_coeffs:
            await callback_query.answer("❗️ Пожалуйста, выберите хотя бы один коэффициент.", show_alert=True)
            return

        # Увеличиваем индекс только если не на последнем складе
        if warehouse_index < len(selected_warehouses) - 1:
            user_data[chat_id]['current_warehouse_index'] += 1  # Переходим к следующему складу
            await send_coefficient_selection(chat_id, callback_query.message)
        else:
            await callback_query.answer("Вы на последнем складе.", show_alert=True)

    elif action == "prev_warehouse":
        if user_data[chat_id]['current_warehouse_index'] > 0:
            user_data[chat_id]['current_warehouse_index'] -= 1  # Переходим к предыдущему складу
            await send_coefficient_selection(chat_id, callback_query.message)
        else:
            await callback_query.answer("Вы на первом складе.", show_alert=True)

    elif action == "main_menu":
        await send_main_menu(chat_id, callback_query.message)
        await callback_query.answer("Перешли в Главное Меню.")


# Обработка нажатия кнопки "✅ Подтвердить выбор коэффициентов"
@dp.callback_query(lambda call: call.data == "confirm_coefficients")
async def process_confirm_coefficients(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    warehouse_index = user_data[chat_id]['current_warehouse_index']
    selected_warehouses = user_data[chat_id]['selected_warehouses']
    warehouse_id = selected_warehouses[warehouse_index]

    # Проверяем, выбраны ли коэффициенты для текущего склада
    selected_coeffs = user_data[chat_id]['selected_coefficients'].get(warehouse_id, [])
    if not selected_coeffs:
        await callback_query.answer("❗️ Пожалуйста, выберите хотя бы один коэффициент.", show_alert=True)
        return

    # Проверяем, обработаны ли все склады
    if warehouse_index == len(selected_warehouses) - 1:
        await finalize_selection(chat_id, callback_query.message)
    else:
        # Перейти к следующему складу, если он не последний
        user_data[chat_id]['current_warehouse_index'] += 1
        await send_coefficient_selection(chat_id, callback_query.message)


# Финализация выбора и запуск отслеживания
async def finalize_selection(chat_id: int, message: types.Message):
    selected_warehouses_ids = user_data[chat_id]['selected_warehouses']
    selected_coefficients = user_data[chat_id]['selected_coefficients']

    # Формируем сообщение с итоговым выбором
    response_message = "✅ <b>Ваш выбор:</b>\n"
    for warehouse_id in selected_warehouses_ids:
        warehouse = next((w for w in WAREHOUSES if w['ID'] == warehouse_id), {})
        warehouse_name = warehouse.get('name', 'Неизвестный склад')
        coeffs = selected_coefficients.get(warehouse_id, [])
        coeffs_text = ", ".join(map(str, coeffs)) if coeffs else "Нет выбранных коэффициентов"
        response_message += f"\n🏢 <b>{warehouse_name}</b>\n🔢 <b>Коэффициенты:</b> {coeffs_text}\n"

    await message.answer(response_message, parse_mode=ParseMode.HTML)

    # Устанавливаем флаг, что настройка завершена
    user_data[chat_id]['setup_complete'] = True

    # Удаляем сообщение с инлайн-кнопками
    if user_data[chat_id]['last_message_id']:
        try:
            await bot.delete_message(chat_id, user_data[chat_id]['last_message_id'])
            user_data[chat_id]['last_message_id'] = None
            user_data[chat_id]['last_keyboard'] = None
            user_data[chat_id]['current_warehouse_index'] = 0
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения: {e}")

    # Предлагаем изменить выбор складов
    change_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔄 Изменить отслеживаемые склады")]],
        resize_keyboard=True
    )
    await message.answer("📝 Вы можете изменить список отслеживаемых складов и коэффициентов.",
                         reply_markup=change_keyboard)


# Изменение списка складов
@dp.message(lambda message: message.text == "🔄 Изменить отслеживаемые склады")
async def change_warehouse_selection(message: types.Message):
    chat_id = message.chat.id

    # Сбрасываем выбор коэффициентов и флаг завершения настройки
    user_data[chat_id]['selected_coefficients'] = {}
    user_data[chat_id]['current_warehouse_index'] = 0
    user_data[chat_id]['setup_complete'] = False  # Сбрасываем флаг настройки

    # Отправляем инлайн-кнопки для редактирования выбранных складов
    await send_warehouse_selection(chat_id, message)

    # Добавляем кнопку подтверждения
    confirm_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Подтвердить выбор складов")]],
        resize_keyboard=True
    )
    await message.answer("📋 Нажмите кнопку, чтобы подтвердить выбор складов.", reply_markup=confirm_keyboard)


# Функция для отправки Главного Меню
async def send_main_menu(chat_id: int, message: types.Message):
    main_menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Изменить отслеживаемые склады")],
            [KeyboardButton(text="📜 История коэффициентов")],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )
    await bot.send_message(chat_id, "🏠 Главное Меню:", reply_markup=main_menu_keyboard)


# Функция для обработки коэффициентов для каждого пользователя
async def process_coefficients_for_user(chat_id: int, data: dict, coefficients: list):
    # Проверяем, завершил ли пользователь настройку
    if not data.get('setup_complete', False):
        return  # Если нет, не обрабатываем коэффициенты

    selected_warehouses = data.get('selected_warehouses', [])
    selected_coefficients = data.get('selected_coefficients', {})
    known_coeffs = data.setdefault('known_coeffs', {})

    new_or_changed_coeffs_found = False

    for coefficient in coefficients:
        warehouse_id = coefficient['warehouseID']
        date = coefficient['date'].split("T")[0]
        coeff_value = coefficient['coefficient']

        if warehouse_id in selected_warehouses:
            if coeff_value in selected_coefficients.get(warehouse_id, []):
                # Проверяем, что этот коэффициент новый или изменился для пользователя
                known_coeffs_warehouse = known_coeffs.setdefault(warehouse_id, {})
                previous_coeff_value = known_coeffs_warehouse.get(date)

                if previous_coeff_value is None:
                    # Новый коэффициент
                    warehouse = next((w for w in WAREHOUSES if w['ID'] == warehouse_id), {})
                    message_text = (
                        f"📢 <b>Новый коэффициент!</b>\n"
                        f"🏢 <b>Склад:</b> {warehouse.get('name', 'Неизвестный склад')}\n"
                        f"📅 <b>Дата:</b> {date}\n"
                        f"📊 <b>Коэффициент:</b> {coeff_value}\n"
                        f"📦 <b>Тип поставки:</b> {coefficient['boxTypeName']}\n\n"
                    )

                    # Отправляем сообщение о новом коэффициенте
                    await send_long_message(chat_id, message_text)

                    # Сохраняем коэффициент
                    known_coeffs_warehouse[date] = coeff_value
                    new_or_changed_coeffs_found = True

                elif previous_coeff_value != coeff_value:
                    # Коэффициент изменился
                    warehouse = next((w for w in WAREHOUSES if w['ID'] == warehouse_id), {})
                    message_text = (
                        f"🔄 <b>Изменение коэффициента!</b>\n"
                        f"🏢 <b>Склад:</b> {warehouse.get('name', 'Неизвестный склад')}\n"
                        f"📅 <b>Дата:</b> {date}\n"
                        f"📊 <b>Старый коэффициент:</b> {previous_coeff_value}\n"
                        f"📊 <b>Новый коэффициент:</b> {coeff_value}\n"
                        f"📦 <b>Тип поставки:</b> {coefficient['boxTypeName']}\n\n"
                    )

                    # Отправляем сообщение об изменении коэффициента
                    await send_long_message(chat_id, message_text)

                    # Обновляем коэффициент
                    known_coeffs_warehouse[date] = coeff_value
                    new_or_changed_coeffs_found = True

    if not new_or_changed_coeffs_found:
        logging.info(f"No new or changed coefficients for chat {chat_id}.")


# Периодическая проверка новых коэффициентов
async def periodic_check():
    while True:
        # Собираем все уникальные ID складов
        all_warehouse_ids = set()
        for data in user_data.values():
            all_warehouse_ids.update(data.get('selected_warehouses', []))

        if all_warehouse_ids:
            try:
                # Получаем коэффициенты из API для всех складов
                coefficients = get_acceptance_coefficients(list(all_warehouse_ids))
                if coefficients:
                    # Обрабатываем результаты для каждого пользователя
                    for chat_id, data in user_data.items():
                        await process_coefficients_for_user(chat_id, data, coefficients)
                else:
                    logging.error("Не удалось получить коэффициенты из API.")
            except Exception as e:
                logging.error(f"Ошибка при запросе к API: {e}")
        else:
            logging.info("Нет отслеживаемых складов.")

        await asyncio.sleep(10)  # Ждем 10 секунд перед следующим запросом


# Функция для отправки сообщений по частям, если длина превышает лимит
async def send_long_message(chat_id: int, text: str):
    if len(text) <= MAX_MESSAGE_LENGTH:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
    else:
        # Разбиваем сообщение на части
        for i in range(0, len(text), MAX_MESSAGE_LENGTH):
            await bot.send_message(chat_id, text[i:i + MAX_MESSAGE_LENGTH], parse_mode=ParseMode.HTML)


# Команда /history для отображения истории коэффициентов
@dp.message(Command("history"))
async def show_history(message: types.Message):
    chat_id = message.chat.id
    history = user_data.get(chat_id, {}).get('known_coeffs', {})

    if not history:
        await message.answer("🔍 История коэффициентов пуста.")
        return

    response_message = "📜 <b>История коэффициентов:</b>\n\n"
    for warehouse_id, dates in history.items():
        warehouse = next((w for w in WAREHOUSES if w['ID'] == warehouse_id), {})
        warehouse_name = warehouse.get('name', 'Неизвестный склад')

        response_message += f"🏢 <b>{warehouse_name}</b>\n"
        for date, coeff_value in dates.items():
            response_message += f"📅 <b>Дата:</b> {date} | 📊 <b>Коэффициент:</b> {coeff_value}\n"
        response_message += "\n"

    await send_long_message(chat_id, response_message)


# Команда /help для отображения списка команд
@dp.message(Command("help"))
async def show_help(message: types.Message):
    response_message = (
        "ℹ️ <b>Доступные команды:</b>\n\n"
        "🟢 /start - начать выбор складов для отслеживания.\n"
        "📜 /history - показать историю коэффициентов.\n"
        "❓ /help - показать информацию о командах.\n"
    )
    # Отправляем сообщение с командами без дополнительной клавиатуры
    await message.answer(response_message, parse_mode=ParseMode.HTML)


# Обработка кнопок Главного Меню
@dp.message(lambda message: message.text == "📜 История коэффициентов")
async def history_button(message: types.Message):
    await show_history(message)


@dp.message(lambda message: message.text == "❓ Помощь")
async def help_button(message: types.Message):
    await show_help(message)


# Обработка кнопки "Главное Меню" через Callback Query
@dp.callback_query(lambda call: call.data == "main_menu")
async def handle_main_menu(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    await send_main_menu(chat_id, callback_query.message)
    await callback_query.answer("Перешли в Главное Меню.")


async def main():
    logging.info("Запуск бота...")
    asyncio.create_task(periodic_check())
    try:
        await dp.start_polling(bot, skip_updates=False)
    except Exception as e:
        logging.error(f"Ошибка в процессе работы бота: {e}")
        logging.error("Traceback:\n%s", traceback.format_exc())  # Записываем стек вызовов в файл


if __name__ == '__main__':
    while True:
        try:
            asyncio.run(main())
        except Exception as main_e:
            logging.error(f"Критическая ошибка, бот упал: {main_e}")
            logging.error("Traceback:\n%s", traceback.format_exc())  # Записываем стек вызовов в файл
            # Ждём 5 секунд перед повторной попыткой перезапуска
            time.sleep(5)
            logging.info("Повторный запуск бота...")
            continue
        # Если main завершился без исключений, выходим из цикла
        break
