#!/usr/bin/env python3
"""
inference_node — VM용 YOLO 추론 + 사람 매칭 + 소켓 송신 (무거움)

역할:
  1) `/robocart/image_raw/compressed` 구독 → YOLOv8n 사람 탐지
  2) 등록 모드: `R` 키 → 가장 큰 사람 bbox 특징을 features.json 에 저장
  3) 추종 모드: 저장된 특징과 매칭 → 최고 점수 사람 bbox 결정
  4) TCP 소켓으로 RPi4 motor_node 에 명령 송신
  5) 결과 이미지를 `/robocart/image_overlay/compressed` 로 발행 (RViz 시각화)

소켓 프로토콜 (JSON, 줄바꿈 종료):
  {"type":"track","x":320,"y":240,"score":0.83}
  {"type":"lost"}
  {"type":"center"}
"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CompressedImage

from .features import (
    KEEP_THRESHOLD,
    MATCH_THRESHOLD,
    compare_features,
    extract_features,
    load_features,
    save_features,
)


# YOLO 로드는 import 비용이 커서 모듈 레벨로 두지 않고 lazy import
def _load_yolo(model_name: str):
    """YOLO 모델 로드 (사전학습 가중치 자동 다운로드)."""
    print(f"[inference_node] YOLO 로딩: {model_name} ...")
    from ultralytics import YOLO   # type: ignore
    return YOLO(model_name)


class InferenceNode(Node):

    def __init__(self) -> None:
        super().__init__("inference_node")

        # ── 파라미터 ─────────────────────────────────────
        self.declare_parameter("yolo_model",       "yolov8n.pt")
        self.declare_parameter("conf_threshold",   0.45)
        self.declare_parameter("image_topic",      "/robocart/image_raw/compressed")
        self.declare_parameter("overlay_topic",    "/robocart/image_overlay/compressed")
        self.declare_parameter("features_path",    "/tmp/robocart_features.json")
        self.declare_parameter("motor_host",       "192.168.0.67")   # RPi4 IP
        self.declare_parameter("motor_port",       9999)
        self.declare_parameter("dry_run_socket",   False)            # 소켓 끄기(개발용)
        self.declare_parameter("lost_timeout_sec", 1.0)              # 사람 놓침 → lost 명령

        self.conf_thr   = self.get_parameter("conf_threshold").value
        img_topic       = self.get_parameter("image_topic").value
        overlay_topic   = self.get_parameter("overlay_topic").value
        self.feat_path  = Path(self.get_parameter("features_path").value)
        self.motor_host = self.get_parameter("motor_host").value
        self.motor_port = self.get_parameter("motor_port").value
        self.dry_socket = self.get_parameter("dry_run_socket").value
        self.lost_to    = self.get_parameter("lost_timeout_sec").value

        # ── YOLO 로드 ────────────────────────────────────
        self.yolo = _load_yolo(self.get_parameter("yolo_model").value)
        print("  [OK] YOLO 준비 완료")

        # ── 등록된 특징 로드 ─────────────────────────────
        self.registered = load_features(self.feat_path)
        if self.registered:
            print(f"  [OK] 등록 정보 로드: {self.feat_path}")
            self.mode = "track"
        else:
            print(f"  [INFO] 등록 정보 없음 → 등록 모드 (R 키로 등록)")
            self.mode = "register"

        # ── ROS QoS ──────────────────────────────────────
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # 구독
        self.create_subscription(CompressedImage, img_topic, self._on_image, qos)
        print(f"  [OK] 구독: {img_topic}")

        # 발행 (오버레이)
        self.overlay_pub = self.create_publisher(CompressedImage, overlay_topic, qos)
        print(f"  [OK] 오버레이 발행: {overlay_topic}")

        # ── 추적 상태 ────────────────────────────────────
        self.prev_cx: float | None = None
        self.last_seen_t: float = 0.0
        self.locked: bool = False

        # ── 소켓 (motor_node 클라이언트) ─────────────────
        self._sock: socket.socket | None = None
        self._sock_lock = threading.Lock()
        if not self.dry_socket:
            threading.Thread(target=self._socket_reconnect_loop, daemon=True).start()
        else:
            print("  [INFO] dry_run_socket=True → 소켓 송신 안 함")

        # ── 키 입력 (등록 트리거) ────────────────────────
        # OpenCV 창 표시 (등록용)
        self._show_window = True
        self._reg_request = False

        print("[inference_node] 준비 완료. R=등록, Q=종료")

    # ════════════════════════════════════════════════════
    # 소켓: motor_node 로 접속/재접속
    # ════════════════════════════════════════════════════
    def _socket_reconnect_loop(self) -> None:
        while rclpy.ok():
            try:
                s = socket.create_connection((self.motor_host, self.motor_port), timeout=2.0)
                s.settimeout(None)
                with self._sock_lock:
                    self._sock = s
                print(f"[inference_node] 소켓 연결 ✓ {self.motor_host}:{self.motor_port}")
                # 끊김 감지: 매 5초 헬스체크
                while rclpy.ok():
                    time.sleep(5.0)
                    try:
                        s.send(b"")   # 연결 살아있는지
                    except OSError:
                        break
            except OSError:
                pass
            with self._sock_lock:
                self._sock = None
            time.sleep(2.0)

    def _send(self, payload: dict) -> None:
        if self.dry_socket:
            print(f"  [DRY-SOCK] {payload}")
            return
        with self._sock_lock:
            s = self._sock
        if s is None:
            return
        try:
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except OSError:
            with self._sock_lock:
                self._sock = None

    # ════════════════════════════════════════════════════
    # 이미지 콜백 (메인 처리)
    # ════════════════════════════════════════════════════
    def _on_image(self, msg: CompressedImage) -> None:
        # CompressedImage → numpy
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            print("[DEBUG] imdecode → None (디코드 실패)")
            return

        # [임시 디버그] 첫 프레임 저장 + 30 프레임마다 통계 출력
        if not getattr(self, "_dbg_saved", False):
            cv2.imwrite("/tmp/recv_test.jpg", frame)
            self._dbg_saved = True
            print(f"[DEBUG] 첫 프레임 저장 → /tmp/recv_test.jpg  shape={frame.shape}  mean={frame.mean():.0f}")
        self._dbg_count = getattr(self, "_dbg_count", 0) + 1
        if self._dbg_count % 30 == 0:
            print(f"[DEBUG] 누적 {self._dbg_count}프레임  mean={frame.mean():.0f}")

        # YOLO 추론 (사람만)
        results = self.yolo.predict(
            frame, classes=[0], conf=self.conf_thr, verbose=False
        )
        boxes = []
        for r in results:
            if r.boxes is None:
                continue
            for b in r.boxes:
                x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                score = float(b.conf[0])
                boxes.append({"bbox": (x1, y1, x2, y2), "score": score})

        h, w = frame.shape[:2]

        # ── 등록 모드 ─────────────────────────────────
        if self.mode == "register":
            self._draw_register_overlay(frame, boxes)
            if self._reg_request and boxes:
                # 가장 큰 박스 선택
                largest = max(boxes, key=lambda d: (d["bbox"][2] - d["bbox"][0]) *
                                                    (d["bbox"][3] - d["bbox"][1]))
                feat = extract_features(frame, largest["bbox"])
                if feat is not None:
                    save_features(feat, self.feat_path)
                    self.registered = feat
                    self.mode = "track"
                    self._reg_request = False
                    print(f"[inference_node] 등록 완료 → {self.feat_path}")
                else:
                    print("[inference_node] 특징 추출 실패 (박스 너무 작음)")

        # ── 추종 모드 ─────────────────────────────────
        else:
            self._track_step(frame, boxes, w)

        # 오버레이 발행
        self._publish_overlay(frame)

        # 로컬 창 (등록용 키 입력)
        if self._show_window:
            try:
                cv2.imshow("RoboCart Follower (R=등록 Q=종료)", frame)
                k = cv2.waitKey(1) & 0xFF
                if k == ord("r") or k == ord("R"):
                    print("[inference_node] R 입력 → 등록 요청")
                    self._reg_request = True
                    self.mode = "register"
                elif k == ord("q") or k == ord("Q"):
                    rclpy.shutdown()
            except cv2.error:
                self._show_window = False   # GUI 없는 환경

    # ════════════════════════════════════════════════════
    # 추종 단계
    # ════════════════════════════════════════════════════
    def _track_step(self, frame, boxes: list[dict], w: int) -> None:
        best = None   # (score, bbox)
        if self.registered is not None:
            for d in boxes:
                cf = extract_features(frame, d["bbox"])
                if cf is None:
                    continue
                s = compare_features(self.registered, cf, prev_cx=self.prev_cx)
                if best is None or s > best[0]:
                    best = (s, d["bbox"])

        now = time.time()
        if best is not None:
            score, (x1, y1, x2, y2) = best
            thr = MATCH_THRESHOLD if not self.locked else KEEP_THRESHOLD
            if score >= thr:
                self.locked = True
                self.last_seen_t = now
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                self.prev_cx = cx
                self._send({"type": "track", "x": int(cx), "y": int(cy), "score": round(score, 3)})
                # 시각화 (초록)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                cv2.putText(frame, f"TRACK {score:.2f}", (x1, max(20, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                self._draw_other_boxes(frame, boxes, (x1, y1, x2, y2))
                return

        # 잠금 잃음
        if self.locked and (now - self.last_seen_t) > self.lost_to:
            self.locked = False
            self.prev_cx = None
            self._send({"type": "lost"})
            print("[inference_node] 사람 놓침 → lost 송신")

        self._draw_other_boxes(frame, boxes, None)

    def _draw_other_boxes(self, frame, boxes: list[dict], locked_bbox) -> None:
        for d in boxes:
            if d["bbox"] == locked_bbox:
                continue
            x1, y1, x2, y2 = d["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 180, 180), 1)

    def _draw_register_overlay(self, frame, boxes: list[dict]) -> None:
        h, w = frame.shape[:2]
        cv2.putText(frame, "REGISTER MODE — press R when ready",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        for d in boxes:
            x1, y1, x2, y2 = d["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)

    # ════════════════════════════════════════════════════
    def _publish_overlay(self, frame) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ok:
            return
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera"
        msg.format = "jpeg"
        msg.data = buf.tobytes()
        self.overlay_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = InferenceNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[inference_node] Ctrl+C 종료")
    finally:
        if node is not None:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
