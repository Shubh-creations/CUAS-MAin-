"""
Bayesian Evidential Threat & Micro-Doppler Fusion Classifier (v4.0-Lattice).
Fuses Deep CNN Visual Features with Radar Micro-Doppler Rotor Blade Flash Modulation
and RF Protocol Fingerprints.
Specifically identifies and flags RF-Silent Autonomous Optical-Navigation Threats.
Outputs explainable diagnostic sub-scores (Kinematics, Payload, Stealth Anomaly, Swarm Coordination).
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import math
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

TACTICAL_DRONE_CLASSES = [
    "SURVEILLANCE_DRONE",
    "SUICIDE_DRONE",
    "CIVILIAN_MULTIROTOR",
    "CUSTOMIZED_DRONE",
    "AUTONOMOUS_LOITERING_MUNITION"
]

CLASS_THREAT_WEIGHTS = {
    "AUTONOMOUS_LOITERING_MUNITION": 1.00,
    "SUICIDE_DRONE": 0.95,
    "CUSTOMIZED_DRONE": 0.85,
    "SURVEILLANCE_DRONE": 0.60,
    "CIVILIAN_MULTIROTOR": 0.20
}

@dataclass
class DroneClassificationResult:
    predicted_class: str
    confidence: float
    threat_score: float                        # Overall Composite (0.0 to 100.0)
    probabilities: Dict[str, float]
    has_payload_risk: bool
    size_category: str                         # "SMALL", "MEDIUM", "LARGE"
    wingspan_estimate_px: int
    aspect_ratio: float
    # v4.0-Lattice Diagnostic Sub-Scores
    kinematic_lethality: float = 0.0           # 0 - 100
    payload_hazard: float = 0.0                # 0 - 100
    rf_stealth_anomaly: float = 0.0            # 0 - 100 (Max if fast closing with 0 RF)
    swarm_coordination_index: float = 0.0      # 0 - 100
    micro_doppler_rpm: float = 0.0             # Estimated rotor RPM
    rf_fingerprint: str = "UNKNOWN"            # Protocol detected
    is_autonomous_dark_threat: bool = False


class DeepDroneClassifier(nn.Module):
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
    """Multi-Modal Bayesian Threat Evaluator combining Vision + Radar Micro-Doppler + RF Fingerprint."""
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

        self.classes = TACTICAL_DRONE_CLASSES
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
                logger.warning(f"Using pretrained backbone: {e}")

        self.model.eval()

        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def classify_crop(
        self,
        crop_bgr: Optional[np.ndarray],
        radar_micro_doppler_rpm: Optional[float] = None,
        rf_protocol: Optional[str] = None,
        closing_speed_mps: float = 0.0,
        swarm_density: int = 1
    ) -> DroneClassificationResult:
        """
        Executes evidential multi-source threat fusion:
        - Vision CNN logits
        - Radar micro-Doppler blade harmonics (rotor RPM)
        - RF signal signatures / RF-Silent anomaly detection
        """
        # Default baseline
        aspect_ratio = 1.0
        wingspan_px = 64
        size_category = "MEDIUM"
        payload_risk = False
        payload_hazard = 10.0

        probs = np.array([0.25, 0.25, 0.20, 0.15, 0.15], dtype=np.float64)

        if crop_bgr is not None and crop_bgr.size > 0:
            h, w = crop_bgr.shape[:2]
            aspect_ratio = round(w / max(h, 1), 2)
            wingspan_px = max(w, h)

            if wingspan_px < 60:
                size_category = "SMALL"
            elif wingspan_px < 180:
                size_category = "MEDIUM"
            else:
                size_category = "LARGE"

            # Check bottom portion for slung munition / bomb canister
            try:
                bottom_crop = crop_bgr[int(h * 0.65):, :]
                gray_bottom = cv2.cvtColor(bottom_crop, cv2.COLOR_BGR2GRAY)
                variance = cv2.Laplacian(gray_bottom, cv2.CV_64F).var()
                if variance > 110.0:
                    payload_risk = True
                    payload_hazard = 85.0
            except Exception:
                pass

            # Vision CNN inference
            try:
                rgb_crop = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_crop)
                tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

                with torch.no_grad():
                    logits = self.model(tensor)
                    cnn_probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()
                    probs = cnn_probs
            except Exception:
                pass

        # 1. Kinematic Lethality Score (0 - 100)
        kinematic_lethality = min(100.0, max(10.0, (closing_speed_mps / 35.0) * 100.0))

        # 2. RF-Silent / Stealth Anomaly Detection
        # If target is closing fast (>15 m/s) and RF protocol is None or "RF-SILENT", it's an autonomous AI weapon
        rf_tag = rf_protocol or "RF-SILENT"
        is_autonomous_dark = False
        rf_stealth_anomaly = 15.0

        if (rf_protocol is None or rf_protocol == "RF-SILENT" or rf_protocol == "AUTONOMOUS_DARK") and closing_speed_mps > 12.0:
            is_autonomous_dark = True
            rf_stealth_anomaly = 95.0
            # Boost AUTONOMOUS_LOITERING_MUNITION probability
            probs[4] += 1.5
        elif rf_protocol in ["ExpressLRS", "Crossfire", "OcuSync-3"]:
            # High-performance C2 protocol typical of FPV suicide or reconnaissance
            rf_stealth_anomaly = 35.0
            probs[1] += 0.8  # SUICIDE_DRONE bias

        # 3. Radar Micro-Doppler Blade Flash Integration
        rpm_val = radar_micro_doppler_rpm or 18000.0
        if rpm_val > 20000.0:
            # Extreme high-RPM 5-7 inch FPV suicide drone
            probs[1] += 1.2
            kinematic_lethality = max(kinematic_lethality, 88.0)
        elif rpm_val < 11000.0 and not payload_risk:
            # Slower consumer photography drone
            probs[2] += 1.0  # CIVILIAN_MULTIROTOR bias

        # Renormalize Bayesian probabilities
        probs = np.maximum(1e-4, probs)
        probs = probs / np.sum(probs)

        predicted_idx = int(np.argmax(probs))
        pred_class = self.classes[predicted_idx]
        confidence = float(probs[predicted_idx])
        prob_dict = {self.classes[i]: round(float(probs[i]), 3) for i in range(len(self.classes))}

        # 4. Swarm Coordination Index
        swarm_coordination_index = min(100.0, float(swarm_density) * 25.0)

        # 5. Composite Threat Severity Index (0 - 100)
        base_threat_wt = CLASS_THREAT_WEIGHTS.get(pred_class, 0.5)
        threat_score = (
            base_threat_wt * 35.0 +
            (kinematic_lethality / 100.0) * 25.0 +
            (payload_hazard / 100.0) * 20.0 +
            (rf_stealth_anomaly / 100.0) * 15.0 +
            (swarm_coordination_index / 100.0) * 5.0
        )
        if is_autonomous_dark:
            threat_score += 15.0
        threat_score = round(min(100.0, max(5.0, threat_score)), 1)

        return DroneClassificationResult(
            predicted_class=pred_class,
            confidence=round(confidence, 3),
            threat_score=threat_score,
            probabilities=prob_dict,
            has_payload_risk=payload_risk,
            size_category=size_category,
            wingspan_estimate_px=wingspan_px,
            aspect_ratio=aspect_ratio,
            kinematic_lethality=round(kinematic_lethality, 1),
            payload_hazard=round(payload_hazard, 1),
            rf_stealth_anomaly=round(rf_stealth_anomaly, 1),
            swarm_coordination_index=round(swarm_coordination_index, 1),
            micro_doppler_rpm=round(rpm_val, 0),
            rf_fingerprint=rf_tag,
            is_autonomous_dark_threat=is_autonomous_dark
        )
