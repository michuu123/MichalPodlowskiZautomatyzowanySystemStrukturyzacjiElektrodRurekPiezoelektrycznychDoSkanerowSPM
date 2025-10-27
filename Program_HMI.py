import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import time
import json
import os

# Ustawienia GRBL
GRBL_BAUD_RATE = 115200

# Parametry cyklu grawerowania
CYLINDER_Y_START = -280 # Początkowa pozycja Y do sondowania
CYLINDER_X_START = -310 # Początkowa pozycja X do sondowania
CYLINDER_Z_START = -90 # Początkowa pozycja Z do sondowania
LENGTH_A = 10 # Długość A elektrody
LENGTH_B = 10 # Długość B elektrody
GROVE_MARIGIN = 0.5 # Długość C elektrody
Z_CLEARANCE = 30 # Bezpieczna odległość do podniesienia Z
Z_CLEARANCE_ABSOLUTE=-65 # Bezpieczna odległość do podniesienia Z w kordynatach bezwzględnych
Y_ENGRAVE_LENGTH = 20 # Długość rowka do wygrawerowania (mm)
ENGRAVE_DEPTH = 0.3 # Głębokość grawerowania (mm)
ENGRAVE_FEEDRATE = 200 # Prędkość posuwu podczas grawerowania (mm/min)
PROBE_FEEDRATE = 100 # Prędkość sondowania (mm/min)

class GRBLControllerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GRBL CNC Controller")
        self.geometry("500x550")
        
        self.serial_port = None
        
        # Zmienne do przechowywania współrzędnych z sondy
        self.x_left = 0.0
        self.x_right = 0.0
        self.x_center = 0.0
        self.z_top = 0.0
        self.y = 0.0
        
        self.create_widgets()

    def load_params_from_file(self, filename="params.json"): # Wczytywanie danych z pliku JSON
        if os.path.exists(filename):
            try:
                with open(filename, "r") as f:
                    data = json.load(f)
                for var_name, value in data.items():
                    if var_name in globals():
                        globals()[var_name] = value
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się wczytać parametrów: {e}")

    def save_params_to_file(self, filename="params.json"): # Zapisywanie do pliku JSON
        try:
            data = {var_name: globals()[var_name] for var_name in self.param_entries.keys()}
            with open(filename, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się zapisać parametrów: {e}")

    def create_widgets(self): #tworzenie interfejsu graficznego
        # Sekcja połączenia
        connection_frame = ttk.LabelFrame(self, text="Połączenie")
        connection_frame.pack(padx=10, pady=5, fill="x")
        ttk.Label(connection_frame, text="Port COM:").pack(side="left", padx=5)
        self.port_list = ttk.Combobox(connection_frame, state="readonly")
        self.port_list.pack(side="left", padx=5, expand=True, fill="x")
        self.update_port_list()
        self.connect_btn = ttk.Button(connection_frame, text="Połącz", command=self.connect)
        self.connect_btn.pack(side="left", padx=5)
        
        # Sekcja sterowania ręcznego
        manual_frame = ttk.LabelFrame(self, text="Sterowanie ręczne")
        manual_frame.pack(padx=10, pady=5, fill="x")
        ttk.Label(manual_frame, text="Wartość ruchu (mm):").pack(pady=5)
        self.move_value = ttk.Entry(manual_frame)
        self.move_value.insert(0, "10")
        self.move_value.pack(pady=5)
        move_buttons_frame = ttk.Frame(manual_frame)
        move_buttons_frame.pack()
        buttons = [
            ("-X", lambda: self.send_gcode_move("X", "-")),
            ("+X", lambda: self.send_gcode_move("X", "+")),
            ("-Y", lambda: self.send_gcode_move("Y", "-")),
            ("+Y", lambda: self.send_gcode_move("Y", "+")),
            ("-Z", lambda: self.send_gcode_move("Z", "-")),
            ("+Z", lambda: self.send_gcode_move("Z", "+"))
        ]
        for i, (text, command) in enumerate(buttons):
            btn = ttk.Button(move_buttons_frame, text=text, command=command)
            btn.grid(row=i//2, column=i%2, padx=5, pady=5)
            
        # Sekcja dodatkowych funkcji
        extra_functions_frame = ttk.LabelFrame(self, text="Dodatkowe funkcje")
        extra_functions_frame.pack(padx=10, pady=5, fill="x")
        self.home_btn = ttk.Button(extra_functions_frame, text="Homing ($H)", command=self.home_machine)
        self.home_btn.pack(side="left", padx=5, expand=True, fill="x")
        self.unlock_btn = ttk.Button(extra_functions_frame, text="Kasuj błąd ($X)", command=self.clear_error)
        self.unlock_btn.pack(side="left", padx=5, expand=True, fill="x")

        # Sekcja programu automatycznego
        auto_program_frame = ttk.LabelFrame(self, text="Program automatyczny")
        auto_program_frame.pack(padx=10, pady=5, fill="x")
        
        self.auto_start_btn = ttk.Button(auto_program_frame, text="Uruchom program automatyczny", command=self.auto_program)
        self.auto_start_btn.pack(pady=10)

        # panel parametrów
        params_frame = ttk.LabelFrame(self, text="Parametry programu")
        params_frame.pack(padx=10, pady=5, fill="x")

        self.param_entries = {}
        params = [
            ("Głębokość grawerowania", "ENGRAVE_DEPTH"),
            ("Prędkość grawerowania", "ENGRAVE_FEEDRATE"),
            ("A", "LENGTH_A"),
            ("B", "LENGTH_B"),
            ("C", "GROVE_MARIGIN"),
            ("Pozycja X", "CYLINDER_X_START"),
            ("Pozycja Y", "CYLINDER_Y_START"),
            ("Pozycja Z", "CYLINDER_Z_START"),
            
        ]

        for i, (label, var_name) in enumerate(params):
            ttk.Label(params_frame, text=label + ":", width=30, anchor="w").grid(row=i, column=0, padx=5, pady=2, sticky="w")
            entry = ttk.Entry(params_frame)
            entry.insert(0, str(globals()[var_name]))
            entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
            self.param_entries[var_name] = entry

                # Wczytaj parametry z pliku (jeśli istnieją) i uzupełnij pola
        self.load_params_from_file()
        for var_name, entry in self.param_entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(globals()[var_name]))

        params_frame.columnconfigure(1, weight=1)

        def save_params(): #zapisz parametry do pliku
            for var_name, entry in self.param_entries.items():
                try:
                    globals()[var_name] = float(entry.get())
                except ValueError:
                    messagebox.showerror("Błąd", f"Niepoprawna wartość dla {var_name}")
            self.save_params_to_file()
            messagebox.showinfo("Zapisano", "Parametry zostały zaktualizowane.")


        save_btn = ttk.Button(params_frame, text="Zapisz parametry", command=save_params)
        save_btn.grid(row=len(params), column=0, columnspan=2, pady=5)

        try:
            from PIL import Image, ImageTk
            img = Image.open("drawing.png")
            img = img.resize((200, 200))
            self.preview_img = ImageTk.PhotoImage(img)
            ttk.Label(params_frame, image=self.preview_img).grid(row=len(params)+1, column=0, columnspan=2, pady=5)
        except Exception:
            ttk.Label(params_frame, text="Nie udało się załadować placeholder.png").grid(row=len(params)+1, column=0, columnspan=2, pady=5)
        
        # Pole do wyświetlania statusu
        self.status_label = ttk.Label(self, text="Status: Rozłączony")
        self.status_label.pack(pady=10)

    def update_port_list(self): # Odświeżamy listę dostępnych portów
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_list['values'] = ports
        if ports:
            self.port_list.current(0)
    
    def connect(self): #Łączenie z danym portem
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.status_label.config(text="Status: Rozłączono")
            self.connect_btn.config(text="Połącz")
        else:
            try:
                port = self.port_list.get()
                self.serial_port = serial.Serial(port, GRBL_BAUD_RATE, timeout=10)
                self.status_label.config(text="Status: Połączono")
                self.connect_btn.config(text="Rozłącz")
                messagebox.showinfo("Połączono", f"Pomyślnie połączono z portem {port}")
            except serial.SerialException as e:
                messagebox.showerror("Błąd połączenia", f"Nie można połączyć z portem: {e}")

    

    def send_gcode(self, gcode_command, wait_for_idle=False): # Funkcha odpowiadająca za wysyłanie gcode, z możliwością czekania na stan idle maszyny

        if not self.serial_port or not self.serial_port.is_open:
            messagebox.showerror("Błąd", "Nie połączono z GRBL.")
            return False
        
        self.serial_port.flushInput()
        self.serial_port.write((gcode_command + '\n').encode())
        time.sleep(0.1)  
        if wait_for_idle:
            self.wait_for_idle()
        
        return True
    
    def send_gcode_move(self, axis, direction):
        try:
            value = float(self.move_value.get())
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawną wartość liczbową.")
            return

        if direction == "-":
            value = -value

        gcode = f"G91 G0 {axis}{value}"
        self.send_gcode(gcode)

    

    def wait_for_idle(self, timeout=1000): # Funkcja do oczekiwania na stan "Idle"
        start_time = time.time()
        
        # Pętla trwa, dopóki nie upłynie czas lub maszyna osiągnie stan "idle"
        while time.time() - start_time < timeout:
            self.serial_port.flushInput()
            self.serial_port.write(b'?\n')
            response = self.serial_port.readline().decode().strip()
            self.status_label.config(text=f"Status GRBL: {response}")

            # Sprawdzenie, czy status zawiera "Idle"
            if "Idle" in response:
                return True
            
            # Krótkie opóźnienie, aby uniknąć przeciążenia portu szeregowego
            self.update_idletasks()
            time.sleep(0.1)

        # Jeśli czas upłynął, a maszyna nie przeszła w stan "Idle"
        messagebox.showerror("Błąd", "Przekroczono czas oczekiwania na stan 'Idle'.")
        self.clear_error()
        return False

    def wait_for_probe_response(self, timeout=30): # Funkcja czekania na odpowiedź z sondy
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.serial_port.in_waiting > 0:
                line = self.serial_port.readline().decode().strip()
                if line.startswith("[PRB:"):
                    self.status_label.config(text=f"Odebrano dane sondy: {line}")
                    return line
            self.update_idletasks()
        return None
    

    def home_machine(self): # Funkcja przeprowadzająca "homing"
        if messagebox.askyesno("Homing", "Czy na pewno chcesz wykonać homing? Upewnij się, że krańcówki są sprawne."):
            self.send_gcode("$H")

    def clear_error(self): # Czyszczenie błędu
        self.send_gcode("$X")
    
    def auto_program(self): # Program automatyczny

        # 1. Weryfikacja, podłączenia urządzenia
        if not self.serial_port or not self.serial_port.is_open:
            messagebox.showerror("Błąd", "Nie połączono z GRBL.")
            return

        self.status_label.config(text="Status: Uruchamiam program automatyczny...")
        time.sleep(1)

        # 2. Homing i ruch do pozycji startowej
        self.send_gcode("$H", True)
        self.send_gcode(f"G90 G0 X{CYLINDER_X_START}", True)
        self.send_gcode(f"G90 G1 Y{CYLINDER_Y_START} F1000", True)
        self.send_gcode(f"G90 G0 Z{CYLINDER_Z_START}", True)
        
        # 3. Znalezienie współrzędnej X środka osi rurki
        self.find_x_center()
        self.status_label.config(text=f"Status: Znaleziono X_center: {self.x_center:.2f}")
        
        # 4. Znalezienie współrzędnej Z najwyżej położonej części rurki
        self.find_z_top()

        # 5. Znalezienie współrzędnej Y końcówki rurki
        self.find_y()

        # 6. Wykonanie 4 rowków z obrotem o 90 stopni
        for i in range(4):
            self.engrave_groove() #grawerowanie pojedynczego rowka
            
            if i < 3: # Obrót osi A o 90 stopni
               self.send_gcode(f"G91 G0 A90", True)
        # 7. Wygrawerowanie pierwszego pierścienia
        self.engrave_ring_a()

        # 8. Wygrawerowanie drugiego pierścienia
        self.engrave_ring_b() 
        self.status_label.config(text="Status: Program zakończony pomyślnie.")
        
    def find_x_center(self): # Operacja sondowania odpowiedzialna za znalezienie dokładnego środka elektrody w osi X
        # 1. Sondowanie lewej krawędzi
        self.send_gcode("G91") # Ustawienie trybu względnego
        self.send_gcode(f"G0 X-10") # Odsunięcie od rurki
        self.send_gcode(f"G38.2 X100 F{PROBE_FEEDRATE}") #Rozpoczęcie sondowania, głowica przemieszcza się w prawą stronę aż do uzyskania kontaktu z rurką
        probe_response = self.wait_for_probe_response(timeout=100) #Program czeka aż sonda dojedzie do rurki, następnie zapisuje współrzędną
        self.x_left=float(probe_response.split(':')[1].split(',')[0])
        
        # 2. Sondowanie prawej krawędzi
        self.send_gcode(f"G38.4 X-10 F{PROBE_FEEDRATE}",True) #Głowica odsuwa się od rurki do momentu zerwania kontaktu
        self.send_gcode(f"G0 X-10",True)    #Dodatkowe odsunięcie o 10mm
        self.send_gcode(f"G0 Z{Z_CLEARANCE}", True)     #Podniesienie głowicy na bezpiecznąwysokość
        self.send_gcode(f"G0 X20", True)    # Przejazd głowicy na prawą stronę rurki
        self.send_gcode(f"G0 Z{-Z_CLEARANCE}", True)    # Opuszczenie głowicy

        self.send_gcode(f"G38.2 X-20 F{PROBE_FEEDRATE}")    # Sondowanie przeprowadzane w sposób identyczny jak w przypadku lewej strony
        probe_response = self.wait_for_probe_response(timeout=100)
        self.send_gcode(f"G38.4 X10 F{PROBE_FEEDRATE}",True)
        self.send_gcode(f"G0 X10",True)
        self.x_right=float(probe_response.split(':')[1].split(',')[0])
        self.x_center = (self.x_left + self.x_right) / 2    # Obliczanie pozycji środka rurki będącego średnią między jednym i drugim bokiem
        
    def find_z_top(self): # Operacja sondowania celem znalezienia góry elektrody
        self.send_gcode("G91")
        self.send_gcode(f"G0 Z{Z_CLEARANCE}",True)
        self.send_gcode("G90")
        self.send_gcode(f"G0 X{self.x_center}",True)
        self.send_gcode(f"G38.2 Z-100 F{PROBE_FEEDRATE}", True)
        
        self.send_gcode(f"G38.4 Z10 F{PROBE_FEEDRATE}")
        response=self.wait_for_probe_response(timeout=100)
        self.z_top = float(response.split(':')[1].split(',')[1])

    def find_y(self): # Operacja znalezienia czubka elektrody
        self.send_gcode("G91")
        self.send_gcode(f"G0 Z{Z_CLEARANCE}",True)
        self.send_gcode(f"G0 Y50",True)
        self.send_gcode(f"G0 Z{-Z_CLEARANCE-10}",True)
        self.send_gcode(f"G38.2 Y-50 F{PROBE_FEEDRATE}")
        response=self.wait_for_probe_response(timeout=100)
        self.y=float(response.split(':')[1].split(',')[2])-(3.175/2)
        self.send_gcode(f"G38.4 Y50 F{PROBE_FEEDRATE}",True)

    def engrave_groove(self): # Grawerowanie pojedyńczego rowka
        self.send_gcode("G90",True)
        self.send_gcode(f"G0 Z{Z_CLEARANCE_ABSOLUTE}",True)
        self.send_gcode(f"G90 G1 Y{self.y-LENGTH_A-LENGTH_B-GROVE_MARIGIN} F1000",True)
        self.send_gcode(f"G0 X{self.x_center}",True)
        self.send_gcode(f"G0 Z{self.z_top-ENGRAVE_DEPTH}",True)
        self.send_gcode(f"G1 Y{self.y-LENGTH_A+GROVE_MARIGIN} F{ENGRAVE_FEEDRATE}",True)
        self.send_gcode(f"G0 Z{Z_CLEARANCE_ABSOLUTE}",True)
        self.send_gcode("G90")
        
    def engrave_ring_a(self): # Grawerowanie pierścienia A
        self.send_gcode("G90",True)
        self.send_gcode(f"G0 Z{Z_CLEARANCE_ABSOLUTE}",True)
        self.send_gcode(f"G1 Y{self.y-LENGTH_A} F1000",True)
        self.send_gcode(f"G0 Z{self.z_top-ENGRAVE_DEPTH}",True)
        self.send_gcode(f"G0 A-361",True)

    def engrave_ring_b(self): # Grawerowanie pierścienia B
        self.send_gcode("G90",True)
        self.send_gcode(f"G0 Z{Z_CLEARANCE_ABSOLUTE}",True)
        self.send_gcode(f"G1 Y{self.y-LENGTH_A-LENGTH_B} F1000",True)
        self.send_gcode(f"G0 Z{self.z_top-ENGRAVE_DEPTH}",True)
        self.send_gcode(f"G91 G0 A-361",True)


    

if __name__ == "__main__":
    app = GRBLControllerApp()
    app.mainloop()