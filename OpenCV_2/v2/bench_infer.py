#!/usr/bin/env python3
"""추론·스트림 병목 진단 벤치마크 — 추종이 느린 머신(VM 등)에서 실행.

  python3 bench_infer.py                  # 추론 속도만
  python3 bench_infer.py --pi-ip 192.168.0.29   # + 카메라 수신 fps

참고치(호스트 i5-1334U): YOLO320=18ms, YOLO192=8ms, ReID x1_0=15ms, x0_25=3ms
여기서 잰 값이 참고치의 10배 이상이면 VM 코어 할당 부족을 의심.
"""
import argparse
import os
import time
import urllib.request

import numpy as np

from light_models import OnnxYolo, OnnxReID

HERE = os.path.dirname(os.path.abspath(__file__))
M = lambda n: os.path.join(HERE, "models_light", n)


def bench_infer(threads: int):
    print(f"CPU 코어: {os.cpu_count()}, onnx threads={threads}")
    frame = np.random.randint(0, 255, (480, 640, 3), np.uint8)
    crop = np.random.randint(0, 255, (300, 120, 3), np.uint8)

    for sz, name in [(320, "yolov8n.onnx"), (256, "yolov8n_256.onnx"), (192, "yolov8n_192.onnx")]:
        path = M(name)
        if not os.path.exists(path):
            print(f"YOLO {sz}: 모델 없음({name})")
            continue
        y = OnnxYolo(path, imgsz=sz, threads=threads)
        y.detect(frame)
        t = time.time()
        for _ in range(10):
            y.detect(frame)
        print(f"YOLO {sz}: {(time.time() - t) / 10 * 1000:.0f}ms/frame")

    for name in ["osnet_x1_0.onnx", "osnet_x0_25.onnx"]:
        r = OnnxReID(M(name), threads=threads)
        r.embed(crop)
        t = time.time()
        for _ in range(10):
            r.embed(crop)
        print(f"ReID {name}: {(time.time() - t) / 10 * 1000:.0f}ms/crop")


def bench_stream(url: str, seconds: float = 5.0):
    print(f"스트림 수신 측정({seconds:.0f}초): {url}")
    try:
        stream = urllib.request.urlopen(url, timeout=3.0)
    except Exception as e:
        print(f"  연결 실패: {e}")
        return
    buf, n, total = b"", 0, 0
    t_end = time.time() + seconds
    while time.time() < t_end:
        chunk = stream.read(8192)
        if not chunk:
            break
        total += len(chunk)
        buf += chunk
        while True:
            a = buf.find(b"\xff\xd8")
            b = buf.find(b"\xff\xd9")
            if a == -1 or b == -1 or a >= b:
                break
            n += 1
            buf = buf[b + 2:]
    stream.close()
    print(f"  수신: {n / seconds:.1f}fps, {total / seconds / 1024:.0f}KB/s")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pi-ip", default=None, help="지정 시 카메라 수신 fps도 측정")
    p.add_argument("--threads", type=int, default=4)
    args = p.parse_args()
    bench_infer(args.threads)
    if args.pi_ip:
        bench_stream(f"http://{args.pi_ip}:5000/video_feed")
