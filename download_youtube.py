print("Loading...")
# download_youtube.py
import os
import sys
import time
from yt_dlp import YoutubeDL
import shutil

BAR_LEN = 40
last_print = 0

def human_size(bytes_n):
    if bytes_n is None:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_n < 1024.0:
            return f"{bytes_n:3.1f} {unit}"
        bytes_n /= 1024.0
    return f"{bytes_n:.1f} PB"

def print_progress(status):
    global last_print
    now = time.time()
    if now - last_print < 0.2 and status.get('status') != 'finished':
        return
    last_print = now

    st = status.get('status')
    if st == 'downloading':
        downloaded = status.get('downloaded_bytes') or 0
        total = status.get('total_bytes') or status.get('total_bytes_estimate') or None
        speed = status.get('speed') or 0
        percent = (downloaded / total * 100) if total else 0
        filled = int(BAR_LEN * percent / 100) if total else int(BAR_LEN * (downloaded % 1))
        bar = "█" * filled + "-" * (BAR_LEN - filled)
        speed_h = human_size(speed) + "/s"
        eta = "-"
        if speed and total:
            rem = total - downloaded
            eta_sec = rem / speed
            m, s = divmod(int(eta_sec), 60)
            h, m = divmod(m, 60)
            eta = f"{h:02d}:{m:02d}:{s:02d}"
        total_h = human_size(total) if total else "?"
        print(f"\r[{bar}] {percent:6.2f}% | {human_size(downloaded)}/{total_h} | {speed_h} | ETA: {eta}", end="", flush=True)
    elif st == 'finished':
        print("\rСкачивание завершено. Обработка файла...                     ")

def locate_ffmpeg():
    """
    Возвращает путь к ffmpeg (директории или исполняемому), используемый yt-dlp через опцию ffmpeg_location.
    Логика:
      - если запущено запакованное PyInstaller-приложение, смотрим в sys._MEIPASS
      - иначе пробуем:
          1) путь рядом с скриптом (./ffmpeg.exe, ./ffprobe.exe)
          2) путь указан в переменной окружения FFMPEG_PATH
          3) shutil.which('ffmpeg')
          4) жестко заданный путь (если хочешь, можно изменить)
    """
    # 1) _MEIPASS (PyInstaller --onefile распаковывает там)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base = sys._MEIPASS
        ff = os.path.join(base, 'ffmpeg.exe')
        if os.path.exists(ff):
            return base  # возвращаем директорию, yt-dlp принимает директорию или путь к ffmpeg.exe

    # 2) рядом с исполняемым/скриптом
    base_candidates = [
        os.path.dirname(os.path.abspath(sys.argv[0])),
        os.path.dirname(os.path.abspath(__file__)),
    ]
    for base in base_candidates:
        ff = os.path.join(base, 'ffmpeg.exe')
        if os.path.exists(ff):
            return base

    # 3) из переменной окружения
    env = os.getenv('FFMPEG_PATH')
    if env:
        # если указан путь к директории или к ffmpeg.exe - вернём директорию
        if os.path.isdir(env):
            return env
        if os.path.isfile(env) and os.path.basename(env).lower().startswith('ffmpeg'):
            return os.path.dirname(env)

    # 4) в PATH
    which = shutil.which('ffmpeg')
    if which:
        return os.path.dirname(which)

    # 5) fallback — возможно пользователь ранее использовал этот путь; можно изменить при необходимости
    # Сюда можно вписать твой локальный путь по умолчанию, например:
    default = r"C:\Code\Paths\ffmpeg\bin"
    if os.path.exists(default):
        return default

    # Если не найдено — вернуть None (yt-dlp выдаст понятную ошибку)
    return None

def try_get_info(url, ffmpeg_loc=None):
    ydl_opts = {'quiet': True, 'skip_download': True}
    if ffmpeg_loc:
        ydl_opts['ffmpeg_location'] = ffmpeg_loc
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info
    except Exception:
        return None

def build_format_list(info):
    fmts = info.get('formats', []) or []
    seen = set()
    items = []
    def score(f):
        h = f.get('height') or 0
        abr = f.get('abr') or 0
        return (h, abr)
    fmts_sorted = sorted(fmts, key=score, reverse=True)
    for f in fmts_sorted:
        fid = f.get('format_id')
        if not fid or fid in seen:
            continue
        seen.add(fid)
        ext = f.get('ext') or ''
        height = f.get('height')
        abr = f.get('abr')
        if height:
            res = f"{height}p"
        elif abr:
            res = f"{int(abr)}kbps"
        else:
            res = f"{f.get('format_note') or ''}"
        note = []
        vcodec = f.get('vcodec') or ''
        acodec = f.get('acodec') or ''
        if vcodec and vcodec != 'none':
            note.append(f"v:{vcodec}")
        if acodec and acodec != 'none':
            note.append(f"a:{acodec}")
        items.append({'format_id': fid, 'ext': ext, 'res': res, 'note': ",".join(note)})
    return items

def show_format_options(info):
    title = info.get('title', 'unknown')
    print(f"\nНайдено видео: {title}")
    print("Доступные форматы:")
    items = build_format_list(info)
    print("  0) [best] Наилучший (bestvideo+bestaudio/best) — merged")
    print("  m) [mp3] Аудио MP3 128kbps (конвертация)")
    for i, it in enumerate(items, start=1):
        print(f" {i:2d}) format_id={it['format_id']:<8} ext={it['ext']:<4} {it['res']:<7} {it['note']}")
    print("\nВыберите номер формата, или введите format_id напрямую, или '0' для best, 'm' для mp3.")
    return items

def prepare_ydl_opts(selection, items, ffmpeg_loc):
    if selection == '0':
        return {'format': 'bestvideo+bestaudio/best'}
    if selection.lower() == 'm':
        return {
            'format': 'bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'outtmpl': '%(title)s.%(ext)s'
        }
    if selection.isdigit():
        idx = int(selection)
        if 1 <= idx <= len(items):
            fid = items[idx-1]['format_id']
            return {'format': fid}
    return {'format': selection}

def download_with_choice(url, ffmpeg_loc):
    ydl_opts_for_info = {'quiet': True, 'skip_download': True}
    if ffmpeg_loc:
        ydl_opts_for_info['ffmpeg_location'] = ffmpeg_loc
    with YoutubeDL(ydl_opts_for_info) as ydl:
        info = ydl.extract_info(url, download=False)

    items = show_format_options(info)
    while True:
        sel = input("Выбор (номер/format_id/0/m): ").strip()
        if not sel:
            print("Выбор не введён. Попробуйте снова.")
            continue
        opts = prepare_ydl_opts(sel, items, ffmpeg_loc)
        print(f"Вы выбрали: {sel}. Нажмите Enter для начала загрузки или 'c' чтобы отменить выбор.")
        c = input().strip().lower()
        if c == 'c':
            print("Выбор отменён. Повторите выбор формата.")
            continue

        ydl_opts = {
            'noplaylist': True,
            'progress_hooks': [print_progress],
            'outtmpl': opts.get('outtmpl', '%(title)s.%(ext)s')
        }
        if ffmpeg_loc:
            ydl_opts['ffmpeg_location'] = ffmpeg_loc
        if 'format' in opts:
            ydl_opts['format'] = opts['format']
        if 'postprocessors' in opts:
            ydl_opts['postprocessors'] = opts['postprocessors']

        try:
            with YoutubeDL(ydl_opts) as ydl:
                print("Загрузка...")
                ydl.download([url])
            print("\nЗагрузка успешно завершена!")
            return True
        except Exception as e:
            print(f"\nОшибка при скачивании: {e}")
            return False

def main():
    ffmpeg_loc = locate_ffmpeg()
    if ffmpeg_loc is None:
        print("WARNING: ffmpeg не найден. Если планируете конвертацию (mp3) или использование форматов требующих ffmpeg, установите ffmpeg и повторите.")
    while True:
        url = input("Введите ссылку на YouTube: ").strip()
        if not url:
            print("Ссылка не указана.")
            continue
        info = try_get_info(url, ffmpeg_loc)
        if info is None:
            print("Видео не найдено или ссылка недействительна. Попробуйте снова.")
            continue
        print(f"Найдено видео: {info.get('title', 'unknown')}")
        ans = input("Скачать это видео? (y/n): ").strip().lower()
        if ans == 'n':
            continue
        if ans != 'y':
            print("Неверный ввод. Попробуйте снова.")
            continue

        success = download_with_choice(url, ffmpeg_loc)
        if success:
            break
        else:
            print("Попробовать снова с той же или новой ссылкой.")
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
