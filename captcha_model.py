"""
captcha_model.py
----------------
CNN architecture for the BLS Spain tile CAPTCHA.

Each tile contains a 3-digit number rendered in a decorative / distorted font
with coloured backgrounds and strikethrough lines.

Architecture
------------
Input : 80×80 RGB image, normalised to [-1, 1]
Body  : 3 conv blocks (Conv → BN → ReLU → MaxPool)
Head  : Global average pool → Dropout → 3 parallel FC(10) classifiers
Output: Three digit logits → argmax → concat → e.g. "425"
"""

import torch
import torch.nn as nn

# Image size fed to the model
IMG_SIZE = 80

# Normalisation constants (computed over typical CAPTCHA palettes)
NORM_MEAN = [0.5, 0.5, 0.5]
NORM_STD  = [0.5, 0.5, 0.5]


class DigitBlock(nn.Module):
    """One conv block: Conv2d → BatchNorm → ReLU → MaxPool."""
    def __init__(self, in_ch: int, out_ch: int, pool: bool = True):
        super().__init__()
        layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        ]
        if pool:
            layers.append(nn.MaxPool2d(2))
        self.block = nn.Sequential(*layers)

    def forward(self, x):
        return self.block(x)


class TileCNN(nn.Module):
    """
    Predict a 3-digit number from a single tile image.

    forward() returns a tuple of three tensors, each shape (B, 10),
    representing logit scores for digit-0, digit-1, digit-2.
    """
    def __init__(self, dropout: float = 0.3):
        super().__init__()
        # Backbone: 80 → 40 → 20 → 10
        self.backbone = nn.Sequential(
            DigitBlock(3,   32),   # 80 → 40
            DigitBlock(32,  64),   # 40 → 20
            DigitBlock(64, 128),   # 20 → 10
            DigitBlock(128, 256, pool=False),  # 10 × 10 feature map
            nn.AdaptiveAvgPool2d(1),           # → (B, 256, 1, 1)
        )
        self.dropout = nn.Dropout(dropout)
        self.fc_shared = nn.Linear(256, 256)
        self.relu = nn.ReLU(inplace=True)

        # Three independent digit heads
        self.head0 = nn.Linear(256, 10)
        self.head1 = nn.Linear(256, 10)
        self.head2 = nn.Linear(256, 10)

    def forward(self, x):
        feat = self.backbone(x)             # (B, 256, 1, 1)
        feat = feat.view(feat.size(0), -1)  # (B, 256)
        feat = self.relu(self.fc_shared(self.dropout(feat)))
        return self.head0(feat), self.head1(feat), self.head2(feat)

    def predict_number(self, x) -> list[str]:
        """Return list of predicted 3-digit strings, one per image in batch."""
        self.eval()
        with torch.no_grad():
            l0, l1, l2 = self.forward(x)
            d0 = l0.argmax(dim=1)
            d1 = l1.argmax(dim=1)
            d2 = l2.argmax(dim=1)
        return [
            f"{a.item()}{b.item()}{c.item()}"
            for a, b, c in zip(d0, d1, d2)
        ]


def build_model() -> TileCNN:
    return TileCNN()
