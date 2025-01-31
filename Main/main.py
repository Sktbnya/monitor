import tkinter as tk
from tkinter import messagebox
from pynput import mouse
import pytesseract
from PIL import Image
import requests
import threading
import time
from mss import mss
import re

# Укажите путь к Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Skotoboynya\Desktop\monitor\monitor\tesseract\tesseract.exe'

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
        self.listener = None
        self.tesseract_config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'

        # Проверка доступности Tesseract
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError:
            messagebox.showerror("Ошибка", "Tesseract не найден! Проверьте путь установки.")
            self.window.destroy()

    def setup_ui(self):
        # UI элементы
        tk.Label(self.window, text="Telegram Bot Token:").grid(row=0, column=0, padx=5, pady=2)
        self.token_entry = tk.Entry(self.window, width=40)
        self.token_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(self.window, text="Chat ID:").grid(row=1, column=0, padx=5, pady=2)
        self.chat_id_entry = tk.Entry(self.window, width=40)
        self.chat_id_entry.grid(row=1, column=1, padx=5, pady=2)

        # Кнопки выбора областей
        self.btn_24h = tk.Button(self.window, text="Выбрать область 24ч", 
                               command=lambda: self.select_area("24h"))
        self.btn_24h.grid(row=2, column=0, padx=5, pady=2)
        self.label_24h = tk.Label(self.window, text="Не выбрано")
        self.label_24h.grid(row=2, column=1, padx=5, pady=2)

        self.btn_1h = tk.Button(self.window, text="Выбрать область 1ч", 
                              command=lambda: self.select_area("1h"))
        self.btn_1h.grid(row=3, column=0, padx=5, pady=2)
        self.label_1h = tk.Label(self.window, text="Не выбрано")
        self.label_1h.grid(row=3, column=1, padx=5, pady=2)

        # Управление мониторингом
        self.monitor_btn = tk.Button(self.window, text="Старт", 
                                   command=self.toggle_monitoring, width=15)
        self.monitor_btn.grid(row=4, columnspan=2, pady=10)
        
        # Статус
        self.status_label = tk.Label(self.window, text="Статус: Остановлен", fg="gray")
        self.status_label.grid(row=5, columnspan=2)

    def select_area(self, area_type):
        self.window.iconify()
        messagebox.showinfo("Инструкция", "Зажмите ЛКМ и выделите область. Отпустите ЛКМ для завершения.")

        start_x, start_y = None, None
        end_x, end_y = None, None

        def on_click(x, y, button, pressed):
            nonlocal start_x, start_y, end_x, end_y
            if button == mouse.Button.left:
                if pressed:
                    start_x, start_y = int(x), int(y)
                else:
                    end_x, end_y = int(x), int(y)
                    return False

        try:
            with mouse.Listener(on_click=on_click) as listener:
                listener.join()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка выбора области: {str(e)}")
        finally:
            self.window.deiconify()

        if None not in [start_x, start_y, end_x, end_y]:
            coords = {
                'left': min(start_x, end_x),
                'top': min(start_y, end_y),
                'width': abs(start_x - end_x),
                'height': abs(start_y - end_y)
            }
            
            if coords['width'] < 10 or coords['height'] < 10:
                messagebox.showerror("Ошибка", "Минимальный размер области - 10x10 пикселей!")
                return

            if area_type == "24h":
                self.coords_24h = coords
                self.label_24h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")
            else:
                self.coords_1h = coords
                self.label_1h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")

    def toggle_monitoring(self):
        if not self.monitoring:
            # Валидация ввода
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
            self.status_label.config(text="Статус: Активен", fg="green")
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()
        else:
            self.monitoring = False
            self.monitor_btn.config(text="Старт")
            self.status_label.config(text="Статус: Остановлен", fg="gray")

    def monitor_loop(self):
        prev_24h = prev_1h = None
        
        with mss() as sct:
            while self.monitoring:
                try:
                    # Обработка 24ч
                    if self.coords_24h:
                        img = sct.grab(self.coords_24h)
                        text = pytesseract.image_to_string(
                            Image.frombytes("RGB", img.size, img.rgb),
                            config=self.tesseract_config
                        ).strip()
                        text = ''.join(filter(str.isdigit, text))
                        
                        if text and text != prev_24h:
                            if prev_24h is not None:
                                self.send_alert(f"24h incidents changed: {prev_24h} → {text}")
                            prev_24h = text

                    # Обработка 1ч
                    if self.coords_1h:
                        img = sct.grab(self.coords_1h)
                        text = pytesseract.image_to_string(
                            Image.frombytes("RGB", img.size, img.rgb),
                            config=self.tesseract_config
                        ).strip()
                        text = ''.join(filter(str.isdigit, text))
                        
                        if text and text != prev_1h:
                            if prev_1h is not None:
                                self.send_alert(f"1h incidents changed: {prev_1h} → {text}")
                            prev_1h = text

                    # Адаптивная задержка с проверкой состояния
                    for _ in range(20):
                        if not self.monitoring:
                            break
                        time.sleep(0.5)

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