"""
Hardware Acceleration & CUDA GPU Benchmark Utility for CUAS.
Validates NVIDIA CUDA availability, cuDNN status, VRAM, and runs deep inference benchmarks.
"""

import time
import sys
import torch
import torchvision.models as models
import torch.nn as nn

def run_cuda_check():
    print("=" * 65)
    print("      CUAS PLATFORM - HARDWARE ACCELERATION AUDIT")
    print("=" * 65)
    print(f"Python Runtime     : {sys.version.split()[0]}")
    print(f"PyTorch Version    : {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA Hardware Init : {'[AVAILABLE]' if cuda_available else '[NOT DETECTED]'}")

    if cuda_available:
        device_name = torch.cuda.get_device_name(0)
        device_count = torch.cuda.device_count()
        capability = torch.cuda.get_device_capability(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"GPU Accelerator    : {device_name}")
        print(f"Device Count       : {device_count}")
        print(f"Compute Capability : {capability[0]}.{capability[1]}")
        print(f"Dedicated VRAM     : {vram_gb:.2f} GB")
        print(f"cuDNN Status       : {'Enabled' if torch.backends.cudnn.is_available() else 'Disabled'}")
    else:
        print("[WARNING] Running on CPU host. CUDA hardware acceleration is recommended for high-FPS operations.")

    device = torch.device("cuda" if cuda_available else "cpu")

    # Benchmark Drone Classifier on target device
    print("-" * 65)
    print(f"Executing Deep Learning Benchmark on target device: {device}...")

    class BenchmarkDroneClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.base = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
            self.base.classifier[1] = nn.Linear(self.base.last_channel, 5)

        def forward(self, x):
            return self.base(x)

    model = BenchmarkDroneClassifier().to(device)
    model.eval()
    input_tensor = torch.randn(1, 3, 224, 224, device=device)

    # Warmup
    with torch.no_grad():
        for _ in range(15):
            _ = model(input_tensor)

    # Timing
    iterations = 100
    start = time.perf_counter()
    with torch.no_grad():
        for _ in range(iterations):
            _ = model(input_tensor)
            if cuda_available:
                torch.cuda.synchronize()
    end = time.perf_counter()

    avg_ms = ((end - start) / iterations) * 1000.0
    throughput_fps = 1000.0 / avg_ms

    print(f"Average Inference Latency : {avg_ms:.2f} ms")
    print(f"Peak Throughput           : {throughput_fps:.1f} FPS")
    print("=" * 65)
    if avg_ms < 50.0:
        print("[PASS] System satisfies real-time C-UAS operational latency (<50ms).")
    else:
        print("[ADVISORY] Throughput within acceptable simulation bounds.")
    print("=" * 65)

if __name__ == "__main__":
    run_cuda_check()
