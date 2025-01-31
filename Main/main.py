import tkinter as tk
from tkinter import messagebox
from pynput import mouse
import pytesseract
from PIL import Image
import requests
import threading
import time
from mss import mss

pytesseract.pytesseract.tesseract_cmd = r'.\tesseract\tesseract.exe'

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
        self.listener = None  # Добавлено для управления слушателем мыши

    def setup_ui(self):
        # ... (остальной код UI без изменений)

    def select_area(self, area_type):
        self.window.iconify()
        messagebox.showinfo("Инструкция", "Зажмите ЛКМ и выделите область. Отпустите ЛКМ для завершения.")

        start_x, start_y = None, None
        end_x, end_y = None, None

        def on_click(x, y, button, pressed):
            nonlocal start_x, start_y, end_x, end_y
            if button == mouse.Button.left:
                if pressed:
                    start_x, start_y = int(x), int(y)  # Преобразование в int
                else:
                    end_x, end_y = int(x), int(y)      # Преобразование в int
                    return False  # Остановить слушатель

        def on_move(x, y):
            # Игнорировать перемещение мыши
            pass

        try:
            # Явное создание и управление слушателем
            self.listener = mouse.Listener(on_click=on_click, on_move=on_move)
            self.listener.start()
            self.listener.join()  # Ожидание завершения выбора
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при выборе области: {str(e)}")
        finally:
            self.window.deiconify()
            if self.listener:
                self.listener.stop()

        if None not in [start_x, start_y, end_x, end_y]:
            # Корректный расчет координат с преобразованием в int
            coords = {
                'left': min(start_x, end_x),
                'top': min(start_y, end_y),
                'width': abs(start_x - end_x),
                'height': abs(start_y - end_y)
            }
            
            # Проверка минимального размера области
            if coords['width'] < 10 or coords['height'] < 10:
                messagebox.showerror("Ошибка", "Слишком маленькая область!")
                return

            if area_type == "24h":
                self.coords_24h = coords
                self.label_24h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")
            else:
                self.coords_1h = coords
                self.label_1h.config(text=f"X: {coords['left']} Y: {coords['top']} W: {coords['width']} H: {coords['height']}")

    # ... (остальные методы без изменений)

if __name__ == "__main__":
    app = ScreenMonitorApp()
    app.window.mainloop()