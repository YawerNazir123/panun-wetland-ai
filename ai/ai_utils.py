import os
import torch
import timm
from torchvision import transforms
from PIL import Image

# -----------------------------
# CONFIG
# -----------------------------
DEVICE = torch.device("cpu")
IMG_SIZE = 224
TEMPERATURE = 1.3   # ✅ YOU CHOSE THIS (keep it)

# -----------------------------
# PATHS
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model_best_50_species.pth")

# -----------------------------
# LOAD MODEL
# -----------------------------
checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
CLASSES = checkpoint["classes"]

model = timm.create_model(
    "tf_efficientnetv2_s",
    pretrained=False,
    num_classes=len(CLASSES)
)

model.load_state_dict(checkpoint["model_state"])
model.to(DEVICE)
model.eval()

# -----------------------------
# TRANSFORMS
# -----------------------------
transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    ),
])

# -----------------------------
# PREDICT
# -----------------------------
def predict_image(image_path: str):
    image = Image.open(image_path).convert("RGB")
    tensor = transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        logits = model(tensor) / TEMPERATURE
        probs = torch.softmax(logits, dim=1)[0]

    confidence, idx = torch.max(probs, dim=0)

    confidence = float(confidence.item()) * 100
    class_raw = CLASSES[idx.item()]

    return {
        "species": class_raw.replace("_", " ").title(),
        "scientific": class_raw.lower().replace("_", " "),
        "confidence": round(confidence, 2)
    }
