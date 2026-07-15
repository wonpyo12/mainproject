#!/usr/bin/env python3
"""VM/PC 전용 — 모델을 RPi4/VM 런타임용 ONNX 로 변환 및 다운로드 (1회 실행).

산출물(models_light/):
  - yolov8n.onnx               (사람 검출 - YOLOv8n)
  - osnet_x0_25.onnx           (ReID 512-dim 임베딩 - v2용)
  - osnet_x1_0.onnx            (ReID 512-dim 임베딩 - v3용)
  - face_detection_yunet.onnx  (앞/뒤 보조 얼굴인식, 다운로드)

필요 패키지 (VM/PC):
  pip install onnx ultralytics torch torchvision
  pip install git+https://github.com/KaiyangZhou/deep-person-reid.git
"""
from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "models_light"
OUT.mkdir(exist_ok=True)

IMGSZ = 320
OPSET = 12


def export_yolo() -> bool:
    try:
        from ultralytics import YOLO
    except Exception as e:
        print(f"[yolo] ultralytics 없음: {e}\n  pip install ultralytics")
        return False
    
    # yolov8n.pt가 없으면 자동으로 다운로드되어 학습/내보내기 진행됨
    print(f"[yolo] export yolov8n.pt → onnx (imgsz={IMGSZ}, opset={OPSET})")
    try:
        model = YOLO("yolov8n.pt")
        path = model.export(format="onnx", imgsz=IMGSZ, opset=OPSET, simplify=True)
        src = Path(path)
        dst = OUT / "yolov8n.onnx"
        shutil.copy2(src, dst)
        print(f"[yolo] OK → {dst}")
        return True
    except Exception as e:
        print(f"[yolo] 변환 실패: {e}")
        return False


def export_osnet(model_name: str, dst_name: str) -> bool:
    try:
        import torch
        import torchreid
    except Exception as e:
        print(f"[osnet] torch/torchreid 없음: {e}\n  pip install git+https://github.com/KaiyangZhou/deep-person-reid.git")
        return False
    
    print(f"[osnet] build {model_name} (pretrained=True)")
    try:
        model = torchreid.models.build_model(
            name=model_name, num_classes=1000, loss="softmax", pretrained=True)
        model.eval()
        dummy = torch.randn(1, 3, 256, 128)
        with torch.no_grad():
            out = model(dummy)
        print(f"[osnet] {model_name} feature dim = {tuple(out.shape)}")
        dst = OUT / dst_name
        torch.onnx.export(
            model, dummy, str(dst),
            input_names=["images"], output_names=["embedding"],
            opset_version=OPSET,
            dynamic_axes={"images": {0: "batch"}, "embedding": {0: "batch"}})
        print(f"[osnet] OK → {dst}")
        return True
    except Exception as e:
        print(f"[osnet] {model_name} 변환 실패: {e}")
        return False


def download_yunet() -> bool:
    url = ("https://github.com/opencv/opencv_zoo/raw/main/"
           "models/face_detection_yunet/face_detection_yunet_2023mar.onnx")
    dst = OUT / "face_detection_yunet.onnx"
    if dst.exists() and dst.stat().st_size > 0:
        print(f"[yunet] 이미 있음 → {dst}")
        return True
    try:
        print(f"[yunet] download → {dst}")
        urllib.request.urlretrieve(url, dst)
        print(f"[yunet] OK ({dst.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"[yunet] 다운로드 실패: {e}  (Pi 는 Haar 폴백 사용)")
        return False


def main() -> int:
    print(f"출력 폴더: {OUT}")
    r = {
        "yolo": export_yolo(), 
        "osnet_x0_25 (v2용)": export_osnet("osnet_x0_25", "osnet_x0_25.onnx"),
        "osnet_x1_0 (v3용)": export_osnet("osnet_x1_0", "osnet_x1_0.onnx"),
        "yunet": download_yunet()
    }
    print("\n=== 결과 ===")
    for k, v in r.items():
        print(f"  {k:18s}: {'OK' if v else 'FAIL'}")
    
    success = r["yolo"] and r["osnet_x0_25 (v2용)"] and r["osnet_x1_0 (v3용)"]
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
