import tkinter as tk
from tkinter import ttk, messagebox
import pytesseract
from PIL import Image
import requests
import threading
import time
from mss import mss
import re

# Укажите путь к Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Skotoboynya\Desktop\monitor\monitor\tesseract\tesseract.exe'

class AreaSelector:
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        
        self.canvas = tk.Canvas(self.root, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, 
            self.start_x, self.start_y,
            outline='red', width=2
        )
        
    def on_drag(self, event):
        self.canvas.coords(
            self.rect,
            self.start_x, self.start_y,
            event.x, event.y
        )
        
    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        
        self.root.destroy()
        self.callback({
            'left': x1,
            'top': y1,
            'width': x2 - x1,
            'height': y2 - y1
        })

class ScreenMonitorApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("SOC L1 Monitor")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.setup_ui()
        self.monitoring = False
        self.thread = None
        self.coords_24h = None
        self.coords_1h = None
        self.tesseract_config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'

    def setup_ui(self):
        # UI элементы
        ttk.Label(self.window, text="Telegram Bot Token:").grid(row=0, column=0, padx=5, pady=2)
        self.token_entry = ttk.Entry(self.window, width=40)
        self.token_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(self.window, text="Chat ID:").grid(row=1, column=0, padx=5, pady=2)
        self.chat_id_entry = ttk.Entry(self.window, width=40)
        self.chat_id_entry.grid(row=1, column=1, padx=5, pady=2)

        # Кнопки выбора областей
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

        # Управление мониторингом
        self.monitor_btn = ttk.Button(self.window, text="Старт", 
                                    command=self.toggle_monitoring, width=15)
        self.monitor_btn.grid(row=4, columnspan=2, pady=10)
        
        # Статус
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

            self.monitoring = True
            self.monitor_btn.config(text="Стоп")
            self.status_label.config(text="Статус: Активен", foreground="green")
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()
        else:
            self.monitoring = False
            self.monitor_btn.config(text="Старт")
            self.status_label.config(text="Статус: Остановлен", foreground="gray")

    def monitor_loop(self):
        prev_values = {'24h': None, '1h': None}
        
        with mss() as sct:
            while self.monitoring:
                try:
                    for area_type in ['24h', '1h']:
                        coords = getattr(self, f'coords_{area_type}')
                        if not coords:
                            continue
                            
                        img = sct.grab(coords)
                        text = pytesseract.image_to_string(
                            Image.frombytes("RGB", img.size, img.rgb),
                            config=self.tesseract_config
                        ).strip()
                        text = ''.join(filter(str.isdigit, text))
                        
                        if text and text != prev_values[area_type]:
                            if prev_values[area_type] is not None:
                                self.send_alert(f"{area_type} incidents changed: {prev_values[area_type]} → {text}")
                            prev_values[area_type] = text

                    for _ in range(10):
                        if not self.monitoring:
                            break
                        time.sleep(1)

                except Exception as e:
                    self.window.after(0, messagebox.showerror,
                                    "Ошибка мониторинга", 
                                    f"{str(e)}\nПроверьте настройки областей!")
                    break

    def send_alert(self, message):
        url = f"https://api.telegram.org/bot{self.token_entry.get()}/sendMessage"
        params = {
            "chat_id": self.chat_id_entry.get(),
            "text": message
        }
        try:
            response = requests.post(url, params=params, timeout=10)
            response.raise_for_status()
        except Exception as e:
            self.window.after(0, messagebox.showerror,
                            "Ошибка отправки",
                            f"Не удалось отправить сообщение: {str(e)}")

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
        messagebox.showerror("Критическая ошибка", f"Программа завершена с ошибкой: {str(e)}")