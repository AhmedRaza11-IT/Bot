"""
train_captcha_model.py
----------------------
Train the TileCNN on labelled tile images saved by the bot.

Expected directory layout
-------------------------
captcha_tiles/
    240/          ← all tiles that show the number 240
        tile_001.png
        tile_002.png
        ...
    425/
        tile_001.png
        ...
    ...

Each PNG is an 80×80 (or similar) screenshot of a single CAPTCHA tile.
The folder name IS the label (3-digit number string).

Usage
-----
    python train_captcha_model.py

Outputs
-------
    captcha_model.pth   — trained weights (load with captcha_model.TileCNN)
    training_log.txt    — loss / accuracy per epoch
"""

import os
import sys
import time
import random
import pathlib
import logging
from collections import Counter

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import transforms
from PIL import Image

# ── Project import ────────────────────────────────────────────────────────────
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from captcha_model import TileCNN, IMG_SIZE, NORM_MEAN, NORM_STD

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR   = pathlib.Path(__file__).parent / "captcha_tiles"
MODEL_PATH = pathlib.Path(__file__).parent / "captcha_model.pth"
LOG_PATH   = pathlib.Path(__file__).parent / "training_log.txt"

EPOCHS      = 60
BATCH_SIZE  = 32
LR          = 1e-3
VAL_SPLIT   = 0.15   # fraction of data used for validation
SEED        = 42

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ── Dataset ───────────────────────────────────────────────────────────────────
class TileDataset(Dataset):
    """
    Loads tiles from captcha_tiles/<label>/*.png.
    label is a 3-digit string like "425".
    """

    def __init__(self, root: pathlib.Path, transform=None):
        self.transform = transform
        self.samples: list[tuple[pathlib.Path, tuple[int, int, int]]] = []

        invalid = 0
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            label_str = folder.name
            if not (label_str.isdigit() and len(label_str) == 3):
                log.warning(f"Skipping folder with non-3-digit name: {label_str}")
                continue
            d0, d1, d2 = int(label_str[0]), int(label_str[1]), int(label_str[2])
            for img_path in folder.glob("*.png"):
                self.samples.append((img_path, (d0, d1, d2)))

        if not self.samples:
            raise RuntimeError(
                f"No valid tile images found in {root}.\n"
                "Run the bot for a while to collect data first."
            )

        log.info(f"Dataset: {len(self.samples)} tiles, "
                 f"{len(set(s[1] for s in self.samples))} unique numbers")

        # Class balance summary
        counts = Counter(f"{d0}{d1}{d2}" for _, (d0, d1, d2) in self.samples)
        log.info(f"Top 10 classes: {counts.most_common(10)}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, (d0, d1, d2) = self.samples[idx]
        img = Image.open(path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, torch.tensor(d0), torch.tensor(d1), torch.tensor(d2)


# ── Transforms ────────────────────────────────────────────────────────────────
train_transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    # Data augmentation — simulate slight CAPTCHA variations
    transforms.RandomHorizontalFlip(p=0.1),
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
    transforms.RandomAffine(degrees=5, translate=(0.05, 0.05), scale=(0.9, 1.1)),
    transforms.ToTensor(),
    transforms.Normalize(mean=NORM_MEAN, std=NORM_STD),
])

val_transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=NORM_MEAN, std=NORM_STD),
])


# ── Training loop ─────────────────────────────────────────────────────────────
def train():
    torch.manual_seed(SEED)
    random.seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Using device: {device}")

    # ── Dataset split ─────────────────────────────────────────────────────────
    full_ds = TileDataset(DATA_DIR, transform=train_transform)
    n_val   = max(1, int(len(full_ds) * VAL_SPLIT))
    n_train = len(full_ds) - n_val
    train_ds, val_ds_raw = random_split(
        full_ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(SEED)
    )

    # Apply val transform to val split
    class _ValWrapper(Dataset):
        def __init__(self, subset, tfm):
            self.subset = subset
            self.tfm = tfm
        def __len__(self): return len(self.subset)
        def __getitem__(self, idx):
            path, (d0, d1, d2) = full_ds.samples[self.subset.indices[idx]]
            img = Image.open(path).convert("RGB")
            return self.tfm(img), torch.tensor(d0), torch.tensor(d1), torch.tensor(d2)

    val_ds = _ValWrapper(val_ds_raw, val_transform)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,  num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    log.info(f"Train: {len(train_ds)} | Val: {len(val_ds)}")

    # ── Model ─────────────────────────────────────────────────────────────────
    model = TileCNN().to(device)
    total_params = sum(p.numel() for p in model.parameters())
    log.info(f"Model parameters: {total_params:,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    best_val_acc = 0.0

    for epoch in range(1, EPOCHS + 1):
        # ── Train ─────────────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total   = 0

        for imgs, d0, d1, d2 in train_loader:
            imgs = imgs.to(device)
            d0, d1, d2 = d0.to(device), d1.to(device), d2.to(device)

            optimizer.zero_grad()
            l0, l1, l2 = model(imgs)
            loss = criterion(l0, d0) + criterion(l1, d1) + criterion(l2, d2)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * imgs.size(0)
            # A prediction is correct only if ALL 3 digits are right
            correct_mask = (
                (l0.argmax(1) == d0) &
                (l1.argmax(1) == d1) &
                (l2.argmax(1) == d2)
            )
            train_correct += correct_mask.sum().item()
            train_total   += imgs.size(0)

        scheduler.step()

        # ── Validate ──────────────────────────────────────────────────────────
        model.eval()
        val_correct = 0
        val_total   = 0

        with torch.no_grad():
            for imgs, d0, d1, d2 in val_loader:
                imgs = imgs.to(device)
                d0, d1, d2 = d0.to(device), d1.to(device), d2.to(device)
                l0, l1, l2 = model(imgs)
                correct_mask = (
                    (l0.argmax(1) == d0) &
                    (l1.argmax(1) == d1) &
                    (l2.argmax(1) == d2)
                )
                val_correct += correct_mask.sum().item()
                val_total   += imgs.size(0)

        avg_loss  = train_loss / train_total
        train_acc = 100.0 * train_correct / train_total
        val_acc   = 100.0 * val_correct   / val_total

        log.info(
            f"Epoch {epoch:3d}/{EPOCHS}  "
            f"loss={avg_loss:.4f}  "
            f"train_acc={train_acc:.1f}%  "
            f"val_acc={val_acc:.1f}%"
        )

        # ── Save best model ───────────────────────────────────────────────────
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), MODEL_PATH)
            log.info(f"   💾 Saved best model (val_acc={val_acc:.1f}%)")

    log.info(f"\nTraining complete. Best val_acc = {best_val_acc:.1f}%")
    log.info(f"Model saved to: {MODEL_PATH}")


if __name__ == "__main__":
    if not DATA_DIR.exists() or not any(DATA_DIR.iterdir()):
        print(
            "ERROR: No tile data found.\n"
            f"Expected: {DATA_DIR}/<3-digit-label>/*.png\n"
            "Run the bot for a while to collect tiles first, then re-run this script."
        )
        sys.exit(1)

    train()
