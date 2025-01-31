import sys
import os
import platform
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import pytesseract
from PIL import Image, ImageEnhance
import requests
import threading
import time
from mss import mss
import re
import configparser
import pyautogui

# Настройки для MPSIEM
MPSIEM_FONT_SETTINGS = {
    'contrast_factor': 2.5,       # Увеличение контраста для цифр
    'sharpness_factor': 2.0,      # Увеличение резкости
    'threshold': 200,             # Порог бинаризации
    'digit_whitelist': '0123456789',
    'resize_factor': 2            # Увеличение размера изображения для лучшего распознавания
}

def prevent_sleep():
    """Усиленные движения мыши для предотвращения сна системы"""
    while True:
        try:
            x, y = pyautogui.position()
            # Увеличенная амплитуда движения
            pyautogui.moveTo(x + 50, y + 50, duration=0.3)
            pyautogui.moveTo(x - 50, y - 50, duration=0.3)
            pyautogui.moveTo(x, y, duration=0.3)
            time.sleep(30)  # Уменьшенный интервал
        except Exception as e:
            print(f"Ошибка в prevent_sleep: {str(e)}")
            time.sleep(60)

def start_sleep_prevention():
    sleep_thread = threading.Thread(target=prevent_sleep, daemon=True)
    sleep_thread.start()

def get_tesseract_path():
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent
    
    tess_dir = base_dir / 'tesseract'
    
    if platform.system() == "Windows":
        exe_path = tess_dir / 'tesseract.exe'
    elif platform.system() == "Linux":
        exe_path = tess_dir / 'tesseract'
    elif platform.system() == "Darwin":
        exe_path = tess_dir / 'bin' / 'tesseract'
    
    if not exe_path.exists():
        raise FileNotFoundError(f"Tesseract not found at {exe_path}")
    
    os.environ['TESSDATA_PREFIX'] = str(tess_dir / 'tessdata')
    return str(exe_path)

pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()

class AreaSelector:
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        
        self.canvas = tk.Canvas(self.root, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.start_x = self.start_y = None
        self.rect = None
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='red', width=2
        )
        
    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)
        
    def on_release(self, event):
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        self.root.destroy()
        self.callback({'left': x1, 'top': y1, 'width': x2-x1, 'height': y2-y1})

class ScreenMonitorApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("SOC L1 Monitor v2.0")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.config = configparser.ConfigParser()
        self.config_file = 'config.ini'
        self.load_config()
        
        self.setup_ui()
        self.monitoring = False
        self.thread = None
        self.coords_24h = self.coords_1h = None
        
        # Оптимизированный конфиг для MPSIEM
        self.tesseract_config = (
            '--psm 11 --oem 3 '
            '-c tessedit_char_whitelist=0123456789 '
            'load_system_dawg=0 load_freq_dawg=0 '
            'textord_min_linesize=2.5 textord_old_xheight=1'
        )

    def load_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)

    def save_config(self):
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)

    def setup_ui(self):
        ttk.Label(self.window, text="Telegram Bot Token:").grid(row=0, column=0, padx=5, pady=2)
        self.token_entry = ttk.Entry(self.window, width=40)
        self.token_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(self.window, text="Chat ID:").grid(row=1, column=0, padx=5, pady=2)
        self.chat_id_entry = ttk.Entry(self.window, width=40)
        self.chat_id_entry.grid(row=1, column=1, padx=5, pady=2)
        
        self.btn_24h = ttk.Button(self.window, text="Выбрать область 24ч", 
                                command=lambda: self.select_area("24h"))
        self.btn_24h.grid(row=2, column=0, padx=5, pady=2)
        self.label_24h = ttk.Label(self.window, text="Не выбрано")
        self.label_24h.grid(row=2, column=1, padx=5, pady=2)

        self.btn_1h = ttk.Button(self.window, text="Выбрать область 1ч", 
                               command=lambda: self.select_area("1h"))
        self.btn_1h.grid(row=3, column=0, padx=5, pady=2)
        self.label_1h = ttk.Label(self.window, text="Не выбрано")
        self.label_1h.grid(row=3, column=1, padx=5, pady=2)

        self.monitor_btn = ttk.Button(self.window, text="Старт", 
                                    command=self.toggle_monitoring, width=15)
        self.monitor_btn.grid(row=4, columnspan=2, pady=10)
        
        self.status_label = ttk.Label(self.window, text="Статус: Остановлен", foreground="gray")
        self.status_label.grid(row=5, columnspan=2)

    def select_area(self, area_type):
        def callback(coords):
            if coords['width'] < 10 or coords['height'] < 10:
                messagebox.showerror("Ошибка", "Минимальный размер области - 10x10 пикселей!")
                return
                
            if area_type == "24h":
                self.coords_24h = coords
                self.label_24h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")
            else:
                self.coords_1h = coords
                self.label_1h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")

        self.window.withdraw()
        messagebox.showinfo("Инструкция", "Выделите область удерживая ЛКМ")
        AreaSelector(callback)
        self.window.deiconify()

    def toggle_monitoring(self):
        if not self.monitoring:
            if not re.match(r"^\d+:[A-Za-z0-9_-]+$", self.token_entry.get()):
                messagebox.showerror("Ошибка", "Неверный формат токена Telegram!")
                return
                
            if not self.chat_id_entry.get().isdigit():
                messagebox.showerror("Ошибка", "Chat ID должен содержать только цифры!")
                return

            if not (self.coords_24h and self.coords_1h):
                messagebox.showerror("Ошибка", "Выберите обе области для мониторинга!")
                return

            self.config['Telegram'] = {
                'token': self.token_entry.get(),
                'chat_id': self.chat_id_entry.get()
            }
            self.save_config()

            self.monitoring = True
            self.monitor_btn.config(text="Стоп")
            self.status_label.config(text="Статус: Активен", foreground="green")
            start_sleep_prevention()
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()
        else:
            self.monitoring = False
            self.monitor_btn.config(text="Старт")
            self.status_label.config(text="Статус: Остановлен", foreground="gray")
            
    def preprocess_image(self, img):
        """Оптимизация изображения для MPSIEM"""
        img = Image.frombytes("RGB", img.size, img.rgb)
        
        # Увеличение размера
        img = img.resize((img.width * MPSIEM_FONT_SETTINGS['resize_factor'], 
                        img.height * MPSIEM_FONT_SETTINGS['resize_factor']))
        
        # Улучшение контраста и резкости
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(MPSIEM_FONT_SETTINGS['contrast_factor'])
        
        # Бинаризация
        img = img.point(lambda x: 0 if x < MPSIEM_FONT_SETTINGS['threshold'] else 255)
        return img

    def monitor_loop(self):
        prev_values = {'24h': None, '1h': None}
        
        with mss() as sct:
            while self.monitoring:
                try:
                    for area_type in ['24h', '1h']:
                        coords = getattr(self, f'coords_{area_type}')
                        if not coords: continue
                        
                        img = sct.grab(coords)
                        processed_img = self.preprocess_image(img)
                        
                        text = pytesseract.image_to_string(
                            processed_img,
                            config=self.tesseract_config
                        ).strip()
                        
                        # Фильтрация результатов
                        text = ''.join(filter(str.isdigit, text))
                        if text != prev_values[area_type]:
                            if prev_values[area_type] is not None:
                                self.send_alert(f"{area_type} incidents changed: {prev_values[area_type]} → {text}")
                            prev_values[area_type] = text

                    time.sleep(10)

                except Exception as e:
                    self.window.after(0, messagebox.showerror,
                                    "Ошибка мониторинга", str(e))
                    break

    def send_alert(self, message):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.config['Telegram']['token']}/sendMessage",
                params={'chat_id': self.config['Telegram']['chat_id'], 'text': message},
                timeout=15
            )
            response.raise_for_status()
        except Exception as e:
            self.window.after(0, messagebox.showerror,
                            "Ошибка отправки", str(e))

    def on_close(self):
        self.monitoring = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.window.destroy()

if __name__ == "__main__":
    try:
        app = ScreenMonitorApp()
        app.window.mainloop()
    except Exception as e:
        messagebox.showerror("Критическая ошибка", f"Ошибка запуска: {str(e)}")