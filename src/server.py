import io
import os
import socket
import threading
from fastapi import FastAPI, UploadFile, File
import uvicorn
import torch
import torch.nn as nn
from torchvision import transforms
import torchvision.models as models
from PIL import Image
from Model import SimpleModel

app = FastAPI()

CONFIDENCE_THRESHOLD = 60.0

# automatyczne IP
def udp_server():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind(("0.0.0.0", 9000))
        print(f"UDP server started on IP: {local_ip}:9000")

        while True:
            data, addr = udp_socket.recvfrom(1024)
            if data.decode('utf-8') == "GDZIE_JEST_SERWER_PWR":
                udp_socket.sendto(local_ip.encode('utf-8'), addr)
    except Exception as e:
        print(f"Błąd UDP: {e}")


# odpalamy UDP w osobnym watku
threading.Thread(target=udp_server, daemon=True).start()


# ladowanie wag
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# wczytywanie modelu
model = SimpleModel()
model.load_state_dict(torch.load("model_pwr.pth", map_location=device, weights_only=True))
model.to(device)
model.eval() # wyłącza nauke


# WERYFIKACJA "PRAWDZIWYCH" BUDYNKOW
# prosty model z wiedza ogolna
general_model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
general_model.to(device)
general_model.eval()

BAD_IMAGENET_CLASSES = set(range(0, 398)) | {
    436, 479, 511, 575, 609, 627, 656, 661, 717, 734,
    751, 779, 817, 829, 864, 491, 612, 746, 952, 953,
    954, 955, 968, 504, 413
}

# transformacje
val_transforms = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(256),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# slownik nazw
class_names = ["A-1", "C-1", "C-13 (Serowiec)", "C-16", "C-18", "C-3/4", "C-7", "D-1", "D-20", "H-6"]


BUILDING_INFO = {
    "A-1": {"wydzial": "Gmach Główny (Wydziały PPT i Mechaniczno-Energetycznego)"},
    "C-1": {"wydzial": "Informatyki i Telekomunikacji"},
    "C-13 (Serowiec)": {"wydzial": "Dział Rekrutacji, Dział Pomocy Socjalnej"},
    "C-16": {"wydzial": "Informatyki i Telekomunikacji"},
    "C-18": {"wydzial": "Strefa Kultury Studenckiej"},
    "C-3/4": {"wydzial": "Elektroniki, Fotoniki i Mikrosystemów"},
    "C-7": {"wydzial": "Budownictwa Lądowego i Wodnego"},
    "D-1": {"wydzial": "Inżynierii Środowiska"},
    "D-20": {"wydzial": "Elektryczny"},
    "H-6": {"wydzial": "Chemiczny"}
}

# endpoint przyjmujacy zdjecia - predykcja i zglaszanie bledow
@app.post("/predict")
async def predict_building(file: UploadFile = File(...)):
    try:
        # odczyt z telefonu
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data)).convert("RGB")

        #przygotowanie i wyslanie do modelu
        input_tensor = val_transforms(image).unsqueeze(0).to(device)

        with torch.no_grad():
            # krok 1: czy to wgl budynek
            gen_out = general_model(input_tensor)
            gen_pred = torch.argmax(gen_out, 1).item()

            # odrzucamy kategorie wskaz. na zwierzeta, ludzi itd
            if gen_pred in BAD_IMAGENET_CLASSES:
                print(f"Odrzucono obraz: wykryto '{BAD_IMAGENET_CLASSES[gen_pred]}'.")
                return {"budynek": "To nie jest budynek!", "pewnosc": 0, "wydzial": "-"}

            # krok 2: wlasciwa k;asyfikacja
            output = model(input_tensor)
            probabilities = torch.nn.functional.softmax(output, dim=1)
            conf, predicted = torch.max(probabilities, 1)

        confidence = conf.item() * 100
        building_idx = predicted.item()
        building = class_names[building_idx]
        info = BUILDING_INFO.get(building, {"wydzial": "Brak danych"})

        #print(f"Wykryty budynek: {building} ({confidence:.2f}%)")

        # krok 3: prog odrzucenia
        if(confidence < CONFIDENCE_THRESHOLD):
            return {
                "budynek": "Nie rozpoznano",
                "pewnosc": round(confidence, 2),
                "wydzial": "-"
            }
        else:
            return {
                "budynek": building,
                "pewnosc": round(confidence, 2),
                "wydzial": info["wydzial"]
            }

    except Exception as e:
        return {"error": f"Błąd przetwarzania obrazu: {str(e)}"}


# zglaszanie bledow
@app.post("/report")
async def report_error(file: UploadFile = File(...)):
    try:
        os.makedirs("raporty_od_uzytkownikow", exist_ok=True)
        file_path = os.path.join("raporty_od_uzytkownikow", file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        print(f"Zapisano błędne zdjęcie: {file.filename}")
        return {"status": "Zgłoszono pomyślnie"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("Starting server PWr Scanner...")
    uvicorn.run(app, host="0.0.0.0", port=8000)