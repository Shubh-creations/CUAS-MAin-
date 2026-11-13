"""
Deep Learning Drone Classification & Threat Scoring Engine.
Uses CNN backbones (ResNet18 / MobileNetV2) and heuristic feature inspection
to classify aerial drones and estimate payload lethality.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
from torchvision import transforms
from PIL import Image

from utils.logger import get_logger

logger = get_logger("CUAS.Classifier")

DEFAULT_DRONE_CLASSES = [
    "SURVEILLANCE_DRONE",
    "SUICIDE_DRONE",
    "CIVILIAN_MULTIROTOR",
    "CUSTOMIZED_DRONE",
    "UNKNOWN_AIR_VEHICLE"
]

CLASS_THREAT_WEIGHTS = {
    "SUICIDE_DRONE": 1.0,
    "CUSTOMIZED_DRONE": 0.85,
    "SURVEILLANCE_DRONE": 0.60,
    "UNKNOWN_AIR_VEHICLE": 0.50,
    "CIVILIAN_MULTIROTOR": 0.20
}

@dataclass
class DroneClassificationResult:
    predicted_class: str
    confidence: float
    threat_score: float  # Scale 0.0 to 100.0
    probabilities: Dict[str, float]
    has_payload_risk: bool
    size_category: str   # "SMALL", "MEDIUM", "LARGE"
    wingspan_estimate_px: int
    aspect_ratio: float


class DeepDroneClassifier(nn.Module):
    """Deep Neural Network for Multi-Class Drone Recognition."""
    def __init__(self, num_classes: int = 5, architecture: str = "resnet18", pretrained: bool = True):
        super().__init__()
        self.architecture = architecture.lower()
        if self.architecture == "mobilenet_v2":
            self.backbone = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT if pretrained else None)
            in_features = self.backbone.last_channel
            self.backbone.classifier = nn.Sequential(
                nn.Dropout(0.3),
                nn.Linear(in_features, 128),
                nn.ReLU(inplace=True),
                nn.Linear(128, num_classes)
            )
        else:
            self.backbone = models.resnet18(weights=models.ResNet18_Weights.DEFAULT if pretrained else None)
            in_features = self.backbone.fc.in_features
            self.backbone.fc = nn.Sequential(
                nn.Dropout(0.3),
                nn.Linear(in_features, 128),
                nn.ReLU(inplace=True),
                nn.Linear(128, num_classes)
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)


class DroneClassifierEngine:
    """Production wrapper for model loading, image preprocessing, and inference."""
    def __init__(
        self,
        model_weights_path: Optional[str] = None,
        device: str = "auto",
        architecture: str = "resnet18"
    ):
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        logger.info(f"Initializing DroneClassifierEngine on {self.device} (Arch: {architecture})")

        self.classes = DEFAULT_DRONE_CLASSES
        self.model = DeepDroneClassifier(
            num_classes=len(self.classes),
            architecture=architecture,
            pretrained=True
        ).to(self.device)

        if model_weights_path and os.path.exists(model_weights_path):
            try:
                state_dict = torch.load(model_weights_path, map_location=self.device)
                self.model.load_state_dict(state_dict)
                logger.info(f"Loaded custom weights from {model_weights_path}")
            except Exception as e:
                logger.warning(f"Failed to load weights from {model_weights_path}: {e}. Using pretrained backbone.")

        self.model.eval()

        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def classify_crop(self, crop_bgr: np.ndarray) -> DroneClassificationResult:
        """Runs classification on a cropped bounding box image of the detected drone."""
        if crop_bgr is None or crop_bgr.size == 0:
            return DroneClassificationResult(
                predicted_class="UNKNOWN_AIR_VEHICLE",
                confidence=0.0,
                threat_score=20.0,
                probabilities={c: 0.2 for c in self.classes},
                has_payload_risk=False,
                size_category="UNKNOWN",
                wingspan_estimate_px=0,
                aspect_ratio=1.0
            )

        h, w = crop_bgr.shape[:2]
        aspect_ratio = round(w / max(h, 1), 2)
        wingspan_px = max(w, h)

        # Size category
        if wingspan_px < 60:
            size_category = "SMALL"
        elif wingspan_px < 180:
            size_category = "MEDIUM"
        else:
            size_category = "LARGE"

        # Heuristic payload inspection: check bottom 30% of crop for attached objects/slung loads
        payload_risk = False
        try:
            bottom_crop = crop_bgr[int(h * 0.70):, :]
            gray_bottom = cv2.cvtColor(bottom_crop, cv2.COLOR_BGR2GRAY)
            variance = cv2.Laplacian(gray_bottom, cv2.CV_64F).var()
            if variance > 120.0 and size_category in ["MEDIUM", "LARGE"]:
                payload_risk = True
        except Exception:
            payload_risk = False

        # Convert to PIL & Tensor
        try:
            rgb_crop = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_crop)
            tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

            with torch.no_grad():
                logits = self.model(tensor)
                probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()

            predicted_idx = int(np.argmax(probs))
            confidence = float(probs[predicted_idx])
            pred_class = self.classes[predicted_idx]
            prob_dict = {self.classes[i]: float(probs[i]) for i in range(len(self.classes))}
        except Exception as e:
            logger.error(f"Inference error during drone classification: {e}")
            pred_class = "UNKNOWN_AIR_VEHICLE"
            confidence = 0.50
            prob_dict = {c: 0.2 for c in self.classes}

        # Calculate threat score (0-100)
        base_weight = CLASS_THREAT_WEIGHTS.get(pred_class, 0.5)
        threat_score = base_weight * confidence * 70.0
        if payload_risk:
            threat_score += 25.0
        if size_category == "LARGE":
            threat_score += 15.0
        elif size_category == "MEDIUM":
            threat_score += 8.0

        threat_score = round(min(100.0, max(0.0, threat_score)), 1)

        return DroneClassificationResult(
            predicted_class=pred_class,
            confidence=round(confidence, 3),
            threat_score=threat_score,
            probabilities=prob_dict,
            has_payload_risk=payload_risk,
            size_category=size_category,
            wingspan_estimate_px=wingspan_px,
            aspect_ratio=aspect_ratio
        )
