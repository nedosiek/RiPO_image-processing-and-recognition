import os
import torch
import torch.optim as optim
import torch.nn as nn
from torchvision import transforms
from torchvision import datasets
from torch.utils.data import DataLoader
from tqdm import tqdm

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if device.type == "cuda":
    torch.backends.cudnn.benchmark = True

liczba_budynkow = 10

data_transforms = transforms.Compose([              #Skalujemy krótszy bok do 256,
    transforms.RandomResizedCrop(256),      #a potem wycinamy losowe 256x256
    transforms.RandomHorizontalFlip(),      #losowo obraca albo nie poziomo
    transforms.RandomRotation(30),          # obrót do 30 stopni
    transforms.RandomPerspective(distortion_scale=0.3, p=0.5), # znieksztalca udajac ze stoi sie blizej, dalej lub z boku
    transforms.ColorJitter(                 # zmiana kontrastu/jasności tez losowo
        brightness=0.3,
        contrast=0.3,
        saturation=0.3,
        hue=0.05
    ),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])
val_transforms = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(256), # Zawsze wycina środek, bez losowości
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

Model_src = 'model_pwr.pth'
train_dir = 'dataset'
val_dir = 'val'

train_data = datasets.ImageFolder(train_dir, transform=data_transforms)
val_data = datasets.ImageFolder(val_dir, transform=val_transforms)

train_loader = DataLoader(train_data, batch_size=32, shuffle=True, pin_memory=True)
val_loader = DataLoader(val_data, batch_size=32, shuffle=False, pin_memory=True)

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
        self.fc2 = nn.Linear(512, liczba_budynkow)

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


model = SimpleModel()
if os.path.exists(Model_src):
    print(f"Wczytuję wagi z {Model_src}...")
    model.load_state_dict(torch.load(Model_src))
else:
    print("Nie znaleziono pliku wag! Zaczynam naukę od zera.")

model.to(device)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.0005)
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=3)

num_epochs = 30
best_accuracy = 0.0
accuracy = 0.0
for epoch in range(num_epochs):
    # === TRENING ===
    model.train()
    running_loss = 0.0

    for images, labels in tqdm(train_loader, desc=f"Trenowanie epoki {epoch+1}"):
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item()

    model.eval()
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in val_loader:
            images = images.to(device)
            labels = labels.to(device)

            outputs = model(images)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
    accuracy = 100 * correct / total
    if(accuracy > best_accuracy):
        best_accuracy = accuracy
        torch.save(model.state_dict(), 'model_pwr.pth')
        print(f"Zapisano najlepszy model (Acc: {accuracy:.1f}%) Plik: model_pwr.pth")
    scheduler.step(accuracy)
    current_lr = optimizer.param_groups[0]['lr']
    print(f"Aktualny LR: {current_lr}")
    print(f"Epoka {epoch+1}/{num_epochs} | Loss: {running_loss/len(train_loader):.4f} | Accuracy: {accuracy:.1f}%")

torch.save(model.state_dict(), 'model_pwr_final.pth')
print(f"Zakończono naukę modelu! (Acc: {accuracy:.1f}%) Plik: model_pwr_final.pth")