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


# struktura sieci/modulu
class SimpleModel(nn.Module):
    def __init__(self):
        super(SimpleModel, self).__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, 3, padding=1)
        self.conv4 = nn.Conv2d(128, 256, kernel_size=3, padding=1)

        self.bn1 = nn.BatchNorm2d(32)
        self.bn2 = nn.BatchNorm2d(64)
        self.bn3 = nn.BatchNorm2d(128)
        self.bn4 = nn.BatchNorm2d(256)

        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.5)

        self.fc1 = nn.Linear(256 * 16 * 16, 512)
        self.fc2 = nn.Linear(512, 10)

    def forward(self, x):
        x = self.pool(torch.relu(self.bn1(self.conv1(x))))
        x = self.pool(torch.relu(self.bn2(self.conv2(x))))
        x = self.pool(torch.relu(self.bn3(self.conv3(x))))
        x = self.pool(torch.relu(self.bn4(self.conv4(x))))

        x = x.view(x.size(0), -1)  # Spłaszczanie
        x = torch.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x

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

BAD_IMAGENET_CLASSES = {
    # Pojazdy
    436: 'beach wagon', 479: 'car wheel', 511: 'convertible', 575: 'golfcart', 609: 'jeep',
    627: 'limousine', 656: 'minivan', 661: 'Model T', 717: 'pickup', 734: 'police cruiser',
    751: 'racer', 779: 'school bus', 817: 'sports car', 829: 'streetcar', 864: 'tow truck',
    # Psy, koty, zwierzęta (zakresy)
    **{i: 'animal' for i in range(0, 398)},
    # Ludzie i jedzenie (wybrane)
    491: 'chain mail', 612: 'jinrikisha', 746: 'pug', 952: 'fig', 953: 'pineapple', 954: 'banana',
    955: 'jackfruit', 968: 'cup', 504: 'coffee mug', 413: 'cellphone'
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
    "A-1": {"wydzial": "jedynkaaaaaaaaaaaaaaaaa"},
    "C-1": {"wydzial": "Haha"},
    "C-13 (Serowiec)": {"wydzial": "pyszny ser"},
    "C-16": {"wydzial": "sigma16"},
    "C-18": {"wydzial": "sks"},
    "C-3/4": {"wydzial": "cetrzy-cztery"},
    "C-7": {"wydzial": "siedemB"},
    "D-1": {"wydzial": "dih"},
    "D-20": {"wydzial": "dupa20"},
    "H-6": {"wydzial": "haha-szesc"}
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