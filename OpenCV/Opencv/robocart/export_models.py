#!/usr/bin/env python3
"""VM 전용 — 모델을 RPi4 런타임용 ONNX 로 변환 (1회 실행).

산출물(models_light/):
  - yolov8n.onnx               (사람 검출)
  - osnet_x0_25.onnx           (ReID 512-dim 임베딩)
  - face_detection_yunet.onnx  (앞/뒤 보조, 다운로드)

필요(VM): ultralytics, torch, torchreid, onnx
  pip install onnx torchreid
실행:
  python3 export_models.py
"""
from __future__ import annotations

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
        print(f"[yolo] ultralytics 없음: {e}")
        return False
    pt = HERE / "yolov8n.pt"
    if not pt.exists():
        print(f"[yolo] {pt} 없음")
        return False
    print(f"[yolo] export {pt.name} → onnx (imgsz={IMGSZ}, opset={OPSET})")
    model = YOLO(str(pt))
    path = model.export(format="onnx", imgsz=IMGSZ, opset=OPSET, simplify=True)
    src = Path(path)
    dst = OUT / "yolov8n.onnx"
    shutil.copy2(src, dst)
    print(f"[yolo] OK → {dst}")
    return True


def export_osnet() -> bool:
    try:
        import torch
        import torchreid
    except Exception as e:
        print(f"[osnet] torch/torchreid 없음: {e}\n  pip install torchreid")
        return False
    print("[osnet] build osnet_x0_25 (pretrained=True)")
    model = torchreid.models.build_model(
        name="osnet_x0_25", num_classes=1000, loss="softmax", pretrained=True)
    model.eval()
    dummy = torch.randn(1, 3, 256, 128)
    with torch.no_grad():
        out = model(dummy)
    print(f"[osnet] feature dim = {tuple(out.shape)}")
    dst = OUT / "osnet_x0_25.onnx"
    torch.onnx.export(
        model, dummy, str(dst),
        input_names=["images"], output_names=["embedding"],
        opset_version=OPSET,
        dynamic_axes={"images": {0: "batch"}, "embedding": {0: "batch"}})
    print(f"[osnet] OK → {dst}")
    return True


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
    r = {"yolo": export_yolo(), "osnet": export_osnet(), "yunet": download_yunet()}
    print("\n=== 결과 ===")
    for k, v in r.items():
        print(f"  {k:6s}: {'OK' if v else 'FAIL'}")
    # yolo/osnet 둘 다 있어야 런타임 가능
    return 0 if (r["yolo"] and r["osnet"]) else 1


if __name__ == "__main__":
    sys.exit(main())
