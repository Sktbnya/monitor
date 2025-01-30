import tkinter as tk
from tkinter import messagebox
from pynput import mouse
import pytesseract
from PIL import Image
import requests
import threading
import time
from mss import mss

# Укажите путь к Tesseract OCR (обязательно!)
pytesseract.pytesseract.tesseract_cmd = r'./tesseract/tesseract.exe'

class ScreenMonitorApp:
    def init(self):
        self.window = tk.Tk()
        self.window.title("SOC L1 Monitor")

        self.setup_ui()
        self.monitoring = False
        self.thread = None
        self.coords_24h = None
        self.coords_1h = None

    def setup_ui(self):
        # Поля для API и Chat ID
        tk.Label(self.window, text="Telegram Bot Token:").grid(row=0, column=0)
        self.token_entry = tk.Entry(self.window, width=40)
        self.token_entry.grid(row=0, column=1)

        tk.Label(self.window, text="Chat ID:").grid(row=1, column=0)
        self.chat_id_entry = tk.Entry(self.window, width=40)
        self.chat_id_entry.grid(row=1, column=1)

        # Кнопки выбора областей
        self.btn_24h = tk.Button(self.window, text="Выбрать область 24ч", command=lambda: self.select_area("24h"))
        self.btn_24h.grid(row=2, column=0)
        self.label_24h = tk.Label(self.window, text="Не выбрано")
        self.label_24h.grid(row=2, column=1)

        self.btn_1h = tk.Button(self.window, text="Выбрать область 1ч", command=lambda: self.select_area("1h"))
        self.btn_1h.grid(row=3, column=0)
        self.label_1h = tk.Label(self.window, text="Не выбрано")
        self.label_1h.grid(row=3, column=1)

        # Кнопка управления мониторингом
        self.monitor_btn = tk.Button(self.window, text="Старт", command=self.toggle_monitoring)
        self.monitor_btn.grid(row=4, columnspan=2)

    def select_area(self, area_type):
        self.window.iconify()
        messagebox.showinfo("Инструкция", "Зажмите ЛКМ и выделите область. Отпустите ЛКМ для завершения.")

        start_x, start_y = None, None
        end_x, end_y = None, None

        def on_click(x, y, button, pressed):
            nonlocal start_x, start_y, end_x, end_y
            if button == mouse.Button.left:
                if pressed:
                    start_x, start_y = x, y
                else:
                    end_x, end_y = x, y
                    return False

        with mouse.Listener(on_click=on_click) as listener:
            listener.join()

        if None not in [start_x, start_y, end_x, end_y]:
            coords = {
                'left': min(start_x, end_x),
                'top': min(start_y, end_y),
                'width': abs(start_x - end_x),
                'height': abs(start_y - end_y)
            }
            if area_type == "24h":
                self.coords_24h = coords
                self.label_24h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")
            else:
                self.coords_1h = coords
                self.label_1h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")

        self.window.deiconify()

    def toggle_monitoring(self):
        if not self.monitoring:
            if not all([self.token_entry.get(), self.chat_id_entry.get(), self.coords_24h, self.coords_1h]):
                messagebox.showerror("Ошибка", "Заполните все поля и выберите области")
                return
            self.monitoring = True
            self.monitor_btn.config(text="Стоп")
            self.thread = threading.Thread(target=self.monitor_loop)
            self.thread.start()
        else:
            self.monitoring = False
            self.monitor_btn.config(text="Старт")

    def monitor_loop(self):
        prev_24h = None
        prev_1h = None
        with mss() as sct:
            while self.monitoring:
                # Проверка области 24ч
                if self.coords_24h:
                    img24 = sct.grab(self.coords_24h)
                    text24 = pytesseract.image_to_string(Image.frombytes("RGB", img24.size, img24.rgb)).strip()
                    if text24.isdigit() and text24 != prev_24h:
                        if prev_24h is not None:
                            self.send_alert(f"24h incidents changed: {prev_24h} → {text24}")
                        prev_24h = text24

                # Проверка области 1ч
                if self.coords_1h:
                    img1h = sct.grab(self.coords_1h)
                    text1h = pytesseract.image_to_string(Image.frombytes("RGB", img1h.size, img1h.rgb)).strip()
                    if text1h.isdigit() and text1h != prev_1h:
                        if prev_1h is not None:
                            self.send_alert(f"1h incidents changed: {prev_1h} → {text1h}")
                        prev_1h = text1h

                time.sleep(10)

    def send_alert(self, message):
        url = f"https://api.telegram.org/bot{self.token_entry.get()}/sendMessage"
        params = {
            "chat_id": self.chat_id_entry.get(),
            "text": message
        }
        try:
            requests.post(url, params=params)
        except Exception as e:
            print(f"Ошибка отправки: {e}")

if __name__ == "main":
    app = ScreenMonitorApp()
    app.window.mainloop()