import os
import torch
import timm
from torchvision import transforms
from PIL import Image

# ------------------------
# CONFIG
# ------------------------
IMG_SIZE = 224
CONFIDENCE_THRESHOLD = 0.80
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model_best.pth")

# ------------------------
# LOAD MODEL
# ------------------------
checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
classes = checkpoint["classes"]

model = timm.create_model(
    "tf_efficientnetv2_s",
    pretrained=False,
    num_classes=len(classes)
)
model.load_state_dict(checkpoint["model_state"])
model.to(DEVICE)
model.eval()

# ------------------------
# TRANSFORM
# ------------------------
transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    ),
])

def predict(image_path):
    img = Image.open(image_path).convert("RGB")
    img = transform(img).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        outputs = model(img)
        probs = torch.softmax(outputs, dim=1)[0]

    conf, idx = torch.max(probs, dim=0)
    species = classes[idx.item()]

    confidence = conf.item()

    if confidence >= CONFIDENCE_THRESHOLD:
        status = "KNOWN migratory bird"
    else:
        status = "POTENTIAL NEW species (verification required)"

    print("\n--- Prediction Result ---")
    print(f"Predicted species : {species}")
    print(f"Confidence        : {confidence:.3f}")
    print(f"Status            : {status}")

if __name__ == "__main__":
    img_path = input("Enter path to bird image: ").strip()
    predict(img_path)
