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

DATASET_PATH = r"C:\Users\emilt\Python\FaceRecognition\database"
STREAM_URL = "http://192.168.88.192:8000/video"
RPI_CONTROL_URL = "http://192.168.88.192:8000/move/"

MODEL_NAME = "ArcFace"
CONF_THRESHOLD = 0.5

# =============================
# EMAIL SETTINGS
# =============================
EMAIL_SENDER = "********"
EMAIL_PASSWORD = "********"
EMAIL_RECEIVER = "********"

# =============================
# TELEGRAM SETTINGS
# =============================
BOT_TOKEN = "************"
CHAT_ID = "************"

ACTIVE_TIMEOUT = 10


# =========================
# RPI CONTROL
# =========================

def send_command(cmd):
    try:
        requests.get(RPI_CONTROL_URL + cmd, timeout=2)
        print("🚗", cmd)
    except Exception as e:
        print("RPI ERROR:", e)


# =========================
# MODEL
# =========================

yolo = YOLO("yolov8n.pt")

detected_people = set()
last_seen = {}

streaming = False
cap = None


# =========================
# GUI
# =========================

ctk.set_appearance_mode("dark")

root = ctk.CTk()
root.geometry("950x650")
root.title("AI Face + Vehicle Control System")


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
# STATUS
# =========================

status = ctk.CTkLabel(side_panel, text="Stopped", text_color="red")
status.pack(pady=10)

email_status = ctk.CTkLabel(side_panel, text="Email: Idle")
email_status.pack(pady=5)

telegram_status = ctk.CTkLabel(side_panel, text="Telegram: Idle")
telegram_status.pack(pady=5)


detected_box = ctk.CTkTextbox(side_panel, width=250, height=150)
detected_box.pack(pady=10)


# =========================
# STREAM CONTROL (START/STOP PARALLEL)
# =========================

ctk.CTkLabel(side_panel, text="Stream Control").pack(pady=5)

stream_frame = ctk.CTkFrame(side_panel)
stream_frame.pack(pady=5)

ctk.CTkButton(stream_frame, text="START",
              command=lambda: start_stream()).pack(side="left", padx=10)

ctk.CTkButton(stream_frame, text="STOP",
              fg_color="red",
              command=lambda: stop_stream()).pack(side="left", padx=10)


# =========================
# VEHICLE CONTROL
# =========================

ctk.CTkLabel(side_panel, text="Vehicle Control").pack(pady=5)

ctk.CTkButton(side_panel, text="⬆ Forward",
              command=lambda: send_command("forward")).pack(pady=1)

ctk.CTkButton(side_panel, text="⬇ Backward",
              command=lambda: send_command("backward")).pack(pady=1)

ctk.CTkButton(side_panel, text="⬅ Left",
              command=lambda: send_command("left")).pack(pady=1)
ctk.CTkButton(side_panel, text="➡ Right",
              command=lambda: send_command("right")).pack(pady=1)

ctk.CTkButton(side_panel, text="⛔ STOP",
              fg_color="red",
              command=lambda: send_command("stop")).pack(pady=10)


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
# EMAIL
# =========================

def send_email(name):
    try:
        email_status.configure(text="Email: Sending...", text_color="orange")

        msg = f"Detected: {name}\nTime: {datetime.now()}"

        em = EmailMessage()
        em["From"] = EMAIL_SENDER
        em["To"] = EMAIL_RECEIVER
        em["Subject"] = "Face Detection"
        em.set_content(msg)

        context = ssl.create_default_context()

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(em)

        email_status.configure(text="Email: SENT ✔", text_color="green")

    except:
        email_status.configure(text="Email: ERROR ❌", text_color="red")


# =========================
# TELEGRAM
# =========================

def send_telegram(name):
    try:
        telegram_status.configure(text="Telegram: Sending...", text_color="orange")

        msg = f"👤 {name}\n📅 {datetime.now()}"

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=5
        )

        telegram_status.configure(text="Telegram: SENT ✔", text_color="green")

    except:
        telegram_status.configure(text="Telegram: ERROR ❌", text_color="red")


# =========================
# STREAM FUNCTION
# =========================

def stream():
    global cap, streaming, detected_people, last_seen

    cap = cv2.VideoCapture(STREAM_URL)

    skip = 0

    while streaming:

        ret, frame = cap.read()
        if not ret:
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

                            add_history(name)

                            send_email(name)

                            send_telegram(name)


                    cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)

                    cv2.putText(frame, name, (x1,y1-10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.8, (0,255,0), 2)


            for p in list(last_seen.keys()):
                if now - last_seen[p] > 10:
                    detected_people.discard(p)
                    del last_seen[p]


            detected_box.delete("1.0", "end")
            detected_box.insert("0.0", "\n".join(detected_people))


        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)
        img = img.resize((600, 340))

        photo = ctk.CTkImage(light_image=img, size=(600, 340))

        video_label.configure(image=photo)
        video_label.image = photo


    cap.release()


# =========================
# START / STOP STREAM
# =========================

def start_stream():
    global streaming, detected_people, last_seen

    detected_people.clear()
    last_seen.clear()

    streaming = True
    status.configure(text="Streaming", text_color="green")

    threading.Thread(target=stream, daemon=True).start()


def stop_stream():
    global streaming
    streaming = False
    status.configure(text="Stopped", text_color="red")


root.mainloop()
