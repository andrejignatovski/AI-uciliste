import customtkinter as ctk
import cv2
import os
import threading
import ssl
import smtplib
import requests
import winsound
import time

from PIL import Image
from datetime import datetime
from email.message import EmailMessage
from ultralytics import YOLO
from deepface import DeepFace

# =========================
# SETTINGS
# =========================

DATASET_PATH = r"D:\Python\FaceRecognition\database"

STREAM_URL = "IP-ADRESS"
RPI_CONTROL_URL = "IP-ADRESS"
DISTANCE_URL = "IP-ADRESS"

MODEL_NAME = "ArcFace"
CONF_THRESHOLD = 0.5
ACTIVE_TIMEOUT = 10
SAFE_DISTANCE = 20

# =============================
# EMAIL SETTINGS
# =============================

EMAIL_SENDER = "EMAIL"
EMAIL_PASSWORD = "YOUR_APP_PASSWORD"
EMAIL_RECEIVER = "EMAIL"

# =============================
# TELEGRAM SETTINGS
# =============================

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

# =========================
# CREATE DETECTIONS FOLDER
# =========================

os.makedirs("detections", exist_ok=True)

# =========================
# GLOBALS
# =========================

detected_people = set()
last_seen = {}

streaming = False
cap = None

# Ново: Глобални променливи за следење на состојбата на возилото
current_distance = 999.0  # Почетна безбедна вредност
is_moving_forward = False # Следи дали возилото моментално оди напред

# =========================
# RPI CONTROL
# =========================

def send_command(cmd):
    global is_moving_forward
    
    # БЛОКАДА: Ако има пречка, не дозволувај да тргне НАПРЕД
    if cmd == "forward" and current_distance < SAFE_DISTANCE:
        print("ДВИЖЕЊЕТО НАПРЕД Е БЛОКИРАНО! Има пречка!")
        obstacle_label.configure(text="Obstacle: BLOCK FORWARD", text_color="red")
        return

    try:
        r = requests.get(
            RPI_CONTROL_URL + cmd,
            timeout=2
        )
        print("COMMAND:", cmd)
        
        # Следи дали активната команда е за напред
        if cmd == "forward":
            is_moving_forward = True
        else:
            is_moving_forward = False
            
    except Exception as e:
        print("RPI ERROR:", e)

# =========================
# MODEL
# =========================

yolo = YOLO("yolov8n.pt")

# =========================
# GUI INITIALIZATION
# =========================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.geometry("1200x720")
root.title("AI Face + Vehicle Control")

# =========================
# TABS
# =========================

tabview = ctk.CTkTabview(root)
tabview.pack(expand=True, fill="both")

tab_live = tabview.add("Live")
tab_history = tabview.add("History")

# =========================
# LAYOUT
# =========================

main_frame = ctk.CTkFrame(tab_live)
main_frame.pack(fill="both", expand=True, padx=10, pady=10)

main_frame.grid_columnconfigure(0, weight=3)
main_frame.grid_columnconfigure(1, weight=1)

video_label = ctk.CTkLabel(main_frame, text="")
video_label.grid(row=0, column=0, padx=10, pady=10)

side_panel = ctk.CTkFrame(main_frame)
side_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

# =========================
# STATUS LABELS
# =========================

status = ctk.CTkLabel(side_panel, text="Stopped", text_color="red")
status.pack(pady=10)

email_status = ctk.CTkLabel(side_panel, text="Email: Idle")
email_status.pack(pady=5)

telegram_status = ctk.CTkLabel(side_panel, text="Telegram: Idle")
telegram_status.pack(pady=5)

distance_label = ctk.CTkLabel(side_panel, text="Distance: -- cm", text_color="cyan")
distance_label.pack(pady=5)

obstacle_label = ctk.CTkLabel(side_panel, text="Obstacle: NONE", text_color="green")
obstacle_label.pack(pady=5)

# =========================
# DETECTED PEOPLE BOX
# =========================

detected_box = ctk.CTkTextbox(side_panel, width=250, height=150)
detected_box.pack(pady=10)

# =========================
# STREAM CONTROLS
# =========================

ctk.CTkLabel(side_panel, text="Stream Control").pack(pady=5)

stream_frame = ctk.CTkFrame(side_panel)
stream_frame.pack(pady=5)

ctk.CTkButton(stream_frame, text="START", command=lambda: start_stream()).pack(side="left", padx=10)
ctk.CTkButton(stream_frame, text="STOP", fg_color="red", command=lambda: stop_stream()).pack(side="left", padx=10)

# =========================
# VEHICLE CONTROL
# =========================

ctk.CTkLabel(side_panel, text="Vehicle Control").pack(pady=10)

ctk.CTkButton(side_panel, text="⬆ Forward", command=lambda: send_command("forward")).pack(pady=2)
ctk.CTkButton(side_panel, text="⬇ Backward", command=lambda: send_command("backward")).pack(pady=2)
ctk.CTkButton(side_panel, text="⬅ Left", command=lambda: send_command("left")).pack(pady=2)
ctk.CTkButton(side_panel, text="➡ Right", command=lambda: send_command("right")).pack(pady=2)
ctk.CTkButton(side_panel, text="⛔ STOP", fg_color="red", command=lambda: send_command("stop")).pack(pady=10)

# =========================
# HISTORY
# =========================

history_box = ctk.CTkTextbox(tab_history, width=1000, height=700)
history_box.pack(pady=20)

def add_history(name):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_box.insert("end", f"{t} - {name}\n")
    history_box.see("end")

# =========================
# EMAIL & TELEGRAM FUNCTIONS
# =========================

def send_email(name, image_path):
    try:
        email_status.configure(text="Email: Sending...", text_color="orange")
        em = EmailMessage()
        em["From"] = EMAIL_SENDER
        em["To"] = EMAIL_RECEIVER
        em["Subject"] = "AI Detection Alert"
        em.set_content(f"Detected: {name}\nTime: {datetime.now()}")

        with open(image_path, "rb") as f:
            file_data = f.read()
            file_name = os.path.basename(image_path)

        em.add_attachment(file_data, maintype="image", subtype="jpeg", filename=file_name)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(em)

        email_status.configure(text="Email: SENT ✔", text_color="green")
    except Exception as e:
        print("EMAIL ERROR:", e)
        email_status.configure(text="Email: ERROR ❌", text_color="red")

def send_telegram(name, image_path):
    try:
        telegram_status.configure(text="Telegram: Sending...", text_color="orange")
        with open(image_path, "rb") as photo:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": f"👤 {name}"},
                files={"photo": photo},
                timeout=10
            )
        telegram_status.configure(text="Telegram: SENT ✔", text_color="green")
    except Exception as e:
        print("TELEGRAM ERROR:", e)
        telegram_status.configure(text="Telegram: ERROR ❌", text_color="red")

# =========================
# DISTANCE LOOP (Ажурирана со Авто-Стоп)
# =========================

def distance_loop():
    global current_distance
    global is_moving_forward
    
    while True:
        try:
            r = requests.get(DISTANCE_URL, timeout=1)
            dist = float(r.text)
            current_distance = dist  # Зачувај ја далечината во глобална променлива

            distance_label.configure(text=f"Distance: {dist:.1f} cm")

            if dist < SAFE_DISTANCE:
                obstacle_label.configure(text="Obstacle: DETECTED", text_color="red")
                
                # АВТО-СТОП: Ако оди напред и одеднаш се појави пречка, веднаш прати STOP
                if is_moving_forward:
                    print("КРИТИЧНО: Пречка детектирана при движење! Автоматско стопирање...")
                    send_command("stop")
                    is_moving_forward = False
            else:
                obstacle_label.configure(text="Obstacle: CLEAR", text_color="green")

        except Exception as e:
            distance_label.configure(text="Distance: OFFLINE")
            obstacle_label.configure(text="Obstacle: UNKNOWN", text_color="orange")

        time.sleep(0.5) # Намалено време за побрза реакција на сензорот (двапати во секунда)

# =========================
# STREAM FUNCTION
# =========================

def stream():
    global cap
    global streaming

    cap = cv2.VideoCapture(STREAM_URL)
    skip = 0

    while streaming:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        now = time.time()
        skip += 1

        if skip % 3 == 0:
            results = yolo(frame, conf=CONF_THRESHOLD, verbose=False)

            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    face = frame[y1:y2, x1:x2]

                    if face.size == 0:
                        continue

                    try:
                        dfs = DeepFace.find(
                            img_path=face,
                            db_path=DATASET_PATH,
                            model_name=MODEL_NAME,
                            enforce_detection=False,
                            silent=True
                        )

                        if len(dfs) > 0 and not dfs[0].empty:
                            identity = dfs[0].iloc[0]["identity"]
                            name = os.path.basename(os.path.dirname(identity))
                        else:
                            name = "Unknown"
                    except:
                        name = "Unknown"

                    if name != "Unknown":
                        last_seen[name] = now

                        if name not in detected_people:
                            detected_people.add(name)
                            winsound.Beep(1000, 200)

                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            image_path = f"detections/{name}_{timestamp}.jpg"
                            cv2.imwrite(image_path, frame)

                            add_history(name)

                            threading.Thread(target=send_email, args=(name, image_path), daemon=True).start()
                            threading.Thread(target=send_telegram, args=(name, image_path), daemon=True).start()

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            for p in list(last_seen.keys()):
                if now - last_seen[p] > ACTIVE_TIMEOUT:
                    detected_people.discard(p)
                    del last_seen[p]

            detected_box.delete("1.0", "end")
            detected_box.insert("0.0", "\n".join(detected_people))

        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)
        img = img.resize((780, 500))

        photo = ctk.CTkImage(light_image=img, size=(780, 500))
        video_label.configure(image=photo)
        video_label.image = photo

        time.sleep(0.01)

    if cap is not None:
        cap.release()

# =========================
# START / STOP STREAM
# =========================

def start_stream():
    global streaming
    if not streaming:
        streaming = True
        status.configure(text="Streaming", text_color="green")
        threading.Thread(target=stream, daemon=True).start()

def stop_stream():
    global streaming
    streaming = False
    status.configure(text="Stopped", text_color="red")
    video_label.configure(image=None)

# =========================
# START DISTANCE THREAD
# =========================

threading.Thread(target=distance_loop, daemon=True).start()

# =========================
# RUN GUI
# =========================

root.mainloop()
