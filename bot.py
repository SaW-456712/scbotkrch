import os
import tempfile
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import yt_dlp

# ==============================================================================
# БЛОК НАСТРОЕК И ТЕКСТОВ (Пункт 12, 17 ТЗ)
# ==============================================================================
FILE_SIGNATURE = "_tg@zombie_music_bot"  # Подпись к файлу (оставьте "", если не нужна)

TXT_START = "👋 Добро пожаловать!\n\n🎵 Отправьте ссылку SoundCloud или название трека.\n\nЯ найду музыку и отправлю её."
TXT_SEARCHING = "🔎 Ищу трек..."
TXT_PROCESSING = "⏳ Скачиваю и конвертирую трек, подождите..."
TXT_NOT_FOUND = "❌ Ничего не найдено."
TXT_ERROR = "❌ Произошла ошибка при обработке запроса."
TXT_CANCELLED = "❌ Поиск отменён."
TXT_TOO_LONG = "❌ Трек длиннее 30 минут. Скачивание отменено."
TXT_NO_MORE_RESULTS = "❌ Больше результатов не найдено."

BTN_RECORDS = "📊 Рекорды"
BTN_YES = "✅ Да"
BTN_NEXT = "➡️ Следующий"
BTN_CANCEL = "❌ Отмена"

STATS_FILE = "stats.json"
DOWNLOADS_DIR = "downloads"
MAX_DURATION = 1800  # 30 минут в секундах

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ И ЛОГИРОВАНИЕ (Пункт 16, 19 ТЗ)
# ==============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# ==============================================================================
# ФУНКЦИИ СТАТИСТИКИ (Пункт 14 ТЗ)
# ==============================================================================
def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": [], "downloads": 0}

def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=4)

def track_user(user_id):
    stats = load_stats()
    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_stats(stats)

def track_download():
    stats = load_stats()
    stats["downloads"] = stats.get("downloads", 0) + 1
    save_stats(stats)

# ==============================================================================
# СТАТУСЫ FSM (Пункт 20 ТЗ)
# ==============================================================================
class SearchStates(StatesGroup):
    choosing_result = State()

# ==============================================================================
# КЛАВИАТУРЫ
# ==============================================================================
def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_RECORDS)
    return builder.as_markup(resize_keyboard=True)

def get_search_buttons():
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_YES, callback_data="confirm")
    builder.button(text=BTN_NEXT, callback_data="next")
    builder.button(text=BTN_CANCEL, callback_data="cancel")
    builder.adjust(2, 1) # Первые две кнопки в ряд, отмена на новой строке
    return builder.as_markup()

# ==============================================================================
# СКАЧИВАНИЕ И ОБРАБОТКА (yt-dlp + ffmpeg)
# ==============================================================================
async def download_soundcloud_track(url: str, message: types.Message) -> str | None:
    logger.info("Downloading track")

    import shutil
    import os
    import shutil

    logger.info(f"PATH = {os.environ.get('PATH')}")
    logger.info(f"ffmpeg = {shutil.which('ffmpeg')}")
    logger.info(f"ffprobe = {shutil.which('ffprobe')}")
    temp_dir = tempfile.mkdtemp()

    outtmpl = os.path.join(
        temp_dir,
        "%(id)s.%(ext)s"
    )
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'noplaylist': True,
        'quiet': True,
    
        'ffmpeg_location': '/usr/bin',
    
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
    }

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Converting to MP3")
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'

    try:
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, _download)
        return file_path
    except Exception as e:
        logger.error(f"Ошибка при скачивании: {e}")
        return None

# ==============================================================================
# ОБРАБОТЧИКИ КОМАНД И КНОПОК
# ==============================================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    track_user(message.from_user.id)
    logger.info("Bot started")
    await message.answer(TXT_START, reply_markup=get_main_menu())

@dp.message(F.text == BTN_RECORDS)
async def show_records(message: types.Message):
    stats = load_stats()
    users_count = len(stats.get("users", []))
    downloads_count = stats.get("downloads", 0)
    
    # Пункт 13 ТЗ
    text = (
        f"📊 Статистика\n\n"
        f"👥 Пользователей: {users_count}\n\n"
        f"🎵 Скачано треков: {downloads_count}\n\n"
        f"📦 Всего скачиваний: {downloads_count}"
    )
    logger.info("Show statistics")
    await message.answer(text)

# Обработка прямой ссылки SoundCloud (Пункт 3 ТЗ)
@dp.message(F.text.contains("soundcloud.com"))
async def handle_soundcloud_link(message: types.Message):
    track_user(message.from_user.id)
    url = message.text.strip()
    
    status_msg = await message.answer(TXT_SEARCHING)
    
    ydl_opts = {'extract_flat': True, 'quiet': True}
    def _extract_info():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
            
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _extract_info)
    except Exception as e:
        logger.error(f"Ошибка проверки ссылки: {e}")
        await status_msg.edit_text(TXT_ERROR)
        return

    duration = info.get('duration', 0)
    if duration > MAX_DURATION: # Пункт 10 ТЗ
        await status_msg.edit_text(TXT_TOO_LONG)
        return

    await status_msg.edit_text(TXT_PROCESSING)
    
    file_path = await download_soundcloud_track(url, message)
    if not file_path or not os.path.exists(file_path):
        await status_msg.edit_text(TXT_ERROR)
        return

    # Отправка файла (Пункт 11, 12 ТЗ)
    try:
        caption = FILE_SIGNATURE if FILE_SIGNATURE else None
        audio_file = types.FSInputFile(file_path)
        await message.answer_audio(audio=audio_file, caption=caption)
        logger.info("File sent")
        track_download()
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        await status_msg.edit_text(TXT_ERROR)
    finally:
        # Автоматическое удаление (Пункт 15 ТЗ)
        if os.path.exists(file_path):
            os.remove(file_path)

# Обработка текстовых поисковых запросов (Пункт 4, 5 ТЗ)
@dp.message(F.text)
async def handle_search_query(message: types.Message, state: FSMContext):
    track_user(message.from_user.id)
    query = message.text.strip()
    
    logger.info(f"Searching: {query}")
    status_msg = await message.answer(TXT_SEARCHING)
    
    # Поиск до 15 результатов через scsearch
    ydl_opts = {
        'extract_flat': 'in_playlist', 
        'quiet': True,
        'playlist_items': '1-15'
    }
    
    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(f"scsearch15:{query}", download=False)

    try:
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(None, _search)
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        await status_msg.edit_text(TXT_ERROR)
        return

    entries = search_results.get('entries', [])
    if not entries:
        logger.info("Found 0 results")
        await status_msg.edit_text(TXT_NOT_FOUND)
        return

    logger.info(f"Found {len(entries)} results")
    
    # Сохраняем результаты в FSM контекст
    await state.update_data(results=entries, current_index=0)
    await state.set_state(SearchStates.choosing_result)
    
    await status_msg.delete()
    await send_search_result_message(message, entries[0], 0, len(entries))

async def send_search_result_message(message: types.Message, track_info, index, total, edit_message: types.Message = None):
    title = track_info.get('title', 'Unknown Track')
    text = f"🔎 Результат {index + 1}/{total}\n\n🎵 {title}\n\nПодходит этот трек?"
    
    if edit_message:
        await edit_message.edit_text(text, reply_markup=get_search_buttons())
    else:
        await message.answer(text, reply_markup=get_search_buttons())

# ==============================================================================
# ОБРАБОТКА CALLBACK КНОПОК ПОИСКА (FSM)
# ==============================================================================
@dp.callback_query(SearchStates.choosing_result, F.data == "confirm")
async def process_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    results = data.get("results", [])
    index = data.get("current_index", 0)
    
    if not results:
        await callback.answer(TXT_ERROR)
        return
        
    track = results[index]
    url = track.get("url") or track.get("webpage_url")
    duration = track.get("duration", 0)
    
    # Уведомляем пользователя через изменение текста
    await callback.message.edit_text(TXT_PROCESSING)
    await state.clear() # Сразу очищаем состояние
    
    if duration and duration > MAX_DURATION:
        await callback.message.edit_text(TXT_TOO_LONG)
        return

    file_path = await download_soundcloud_track(url, callback.message)
    if not file_path or not os.path.exists(file_path):
        await callback.message.edit_text(TXT_ERROR)
        return

    try:
        caption = FILE_SIGNATURE if FILE_SIGNATURE else None
        audio_file = types.FSInputFile(file_path)
        await callback.message.answer_audio(audio=audio_file, caption=caption)
        logger.info("File sent")
        track_download()
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        await callback.message.edit_text(TXT_ERROR)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
    
    await callback.answer()

@dp.callback_query(SearchStates.choosing_result, F.data == "next")
async def process_next(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    results = data.get("results", [])
    index = data.get("current_index", 0)
    
    next_index = index + 1
    if next_index >= len(results):
        logger.info("No more results")
        await callback.message.edit_text(TXT_NO_MORE_RESULTS)
        await state.clear()
    else:
        await state.update_data(current_index=next_index)
        await send_search_result_message(callback.message, results[next_index], next_index, len(results), edit_message=callback.message)
        
    await callback.answer()

@dp.callback_query(SearchStates.choosing_result, F.data == "cancel")
async def process_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    logger.info("Search cancelled")
    await callback.message.edit_text(TXT_CANCELLED)
    await callback.answer()

# ==============================================================================
# ЗАПУСК БОТА
# ==============================================================================
async def main():
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
