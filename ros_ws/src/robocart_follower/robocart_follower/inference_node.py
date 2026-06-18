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
import torch
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CompressedImage, Image as RosImage
from std_msgs.msg import Empty


def _bgr_to_imgmsg(bgr: "np.ndarray") -> RosImage:
    """numpy BGR → sensor_msgs/Image (cv_bridge 미사용, NumPy 2.x 호환)"""
    msg = RosImage()
    msg.height = int(bgr.shape[0])
    msg.width  = int(bgr.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = int(bgr.shape[1] * 3)   # bytes per row
    msg.data = bgr.tobytes()
    return msg

from .features import (
    KEEP_THRESHOLD,
    MATCH_THRESHOLD,
    compare_features,
    extract_features,
    load_features,
    save_features,
)


# YOLO/OSNet 로드는 import 비용이 커서 모듈 레벨로 두지 않고 lazy import
def _load_yolo(model_name: str):
    """YOLO 모델 로드 (사전학습 가중치 자동 다운로드)."""
    print(f"[inference_node] YOLO 로딩: {model_name} ...")
    from ultralytics import YOLO   # type: ignore
    return YOLO(model_name)


def _load_reid():
    """OSNet ReID 모델 로드 (사전학습 가중치 수동 다운로드)."""
    try:
        from .osnet import osnet_x0_25
        print("[inference_node] OSNet ReID 로딩...")
        model = osnet_x0_25(num_classes=1, pretrained=False, loss='softmax')
        ckpt_path = Path.home() / ".cache/torch/checkpoints/osnet_x0_25_imagenet.pth"
        if not ckpt_path.exists():
            print(f"[WARNING] 가중치 파일 없음: {ckpt_path}")
            print("  다운로드: https://drive.google.com/uc?id=1rb8UN5ZzPKRc_xvtHlyDh-cSz88YX9hs")
            return None
        state = torch.load(ckpt_path, map_location="cpu")
        model.load_state_dict(state, strict=False)
        model.eval()
        return model
    except Exception as e:
        print(f"[WARNING] OSNet 로드 실패: {e}")
        return None


class InferenceNode(Node):

    def __init__(self) -> None:
        super().__init__("inference_node")

        # ── 파라미터 ─────────────────────────────────────
        self.declare_parameter("yolo_model",        "yolov8n.pt")
        self.declare_parameter("conf_threshold",    0.45)
        self.declare_parameter("image_topic",       "/robocart/image_raw/compressed")
        self.declare_parameter("overlay_topic",     "/robocart/image_overlay/compressed")
        self.declare_parameter("features_path",     "/tmp/robocart_features.json")
        self.declare_parameter("motor_host",        "192.168.0.67")   # RPi4 IP
        self.declare_parameter("motor_port",        9999)
        self.declare_parameter("dry_run_socket",    False)            # 소켓 끄기(개발용)
        self.declare_parameter("lost_timeout_sec",       1.0)         # 사람 놓침 → lost 명령
        self.declare_parameter("auto_register_sec",      5.0)         # 등록 모드 N초 후 자동 등록 (0=비활성)
        self.declare_parameter("auto_reset_after_lost_sec", 10.0)     # 추종 대상 N초간 못 잡으면 자동 리셋 (0=비활성, 다음 손님용)
        # ── 바퀴 주행 파라미터 (사람 추종 시 카트 몸체 이동) ───
        self.declare_parameter("drive_enable",          True)         # 바퀴 주행 사용 여부
        self.declare_parameter("forward_speed",         0.20)         # 전진 속도 (m/s)
        self.declare_parameter("turn_speed",            0.50)         # 회전 속도 (rad/s)
        self.declare_parameter("bbox_h_min_ratio",      0.30)         # 사람 박스 높이/화면 높이 < 이 값이면 전진 (멀다)
        self.declare_parameter("bbox_h_max_ratio",      0.60)         # 사람 박스 높이/화면 높이 > 이 값이면 정지 (가깝다)
        self.declare_parameter("turn_dead_zone_ratio",  0.25)         # 화면 가운데 좌우 N% 안이면 몸체 회전 안 함 (서보가 처리)

        self.conf_thr     = self.get_parameter("conf_threshold").value
        img_topic         = self.get_parameter("image_topic").value
        overlay_topic     = self.get_parameter("overlay_topic").value
        self.feat_path    = Path(self.get_parameter("features_path").value)
        self.motor_host   = self.get_parameter("motor_host").value
        self.motor_port   = self.get_parameter("motor_port").value
        self.dry_socket   = self.get_parameter("dry_run_socket").value
        self.lost_to      = self.get_parameter("lost_timeout_sec").value
        self.auto_reg_sec   = float(self.get_parameter("auto_register_sec").value)
        self.auto_reset_sec = float(self.get_parameter("auto_reset_after_lost_sec").value)
        self.drive_enable   = bool(self.get_parameter("drive_enable").value)
        self.fwd_speed      = float(self.get_parameter("forward_speed").value)
        self.turn_speed     = float(self.get_parameter("turn_speed").value)
        self.bbox_h_min     = float(self.get_parameter("bbox_h_min_ratio").value)
        self.bbox_h_max     = float(self.get_parameter("bbox_h_max_ratio").value)
        self.turn_dz_ratio  = float(self.get_parameter("turn_dead_zone_ratio").value)

        # ── YOLO 로드 ────────────────────────────────────
        self.yolo = _load_yolo(self.get_parameter("yolo_model").value)
        print("  [OK] YOLO 준비 완료")

        # ── OSNet ReID 로드 ───────────────────────────────
        self.reid_model = _load_reid()
        if self.reid_model is not None:
            print("  [OK] OSNet ReID 준비 완료")
        else:
            print("  [INFO] OSNet ReID 미사용 (HSV만으로 동작)")

        # ── 등록된 특징 로드 ─────────────────────────────
        self.registered = load_features(self.feat_path)
        self.register_deadline: float | None = None
        self.lost_since: float | None = None    # 추종 대상 놓친 시점 (자동 리셋용)
        if self.registered:
            print(f"  [OK] 등록 정보 로드: {self.feat_path}")
            self.mode = "track"
        else:
            print(f"  [INFO] 등록 정보 없음 → 등록 모드")
            self.mode = "register"
            # 자동 등록 타이머 시작 (셀프서비스용)
            if self.auto_reg_sec > 0:
                self.register_deadline = time.time() + self.auto_reg_sec
                print(f"  [INFO] {self.auto_reg_sec:.0f}초 후 자동 등록 (가장 큰 사람)")

        # ── ROS QoS ──────────────────────────────────────
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # 구독 (BEST_EFFORT — camera_node 와 일치)
        self.create_subscription(CompressedImage, img_topic, self._on_image, qos)
        print(f"  [OK] 구독: {img_topic}")

        # 발행 (오버레이) — compressed + raw 동시 발행 (RViz Image 디스플레이는 raw 필요)
        self.overlay_pub = self.create_publisher(CompressedImage, overlay_topic, qos)
        raw_overlay_topic = overlay_topic.replace("/compressed", "")
        self.overlay_raw_pub = self.create_publisher(RosImage, raw_overlay_topic, 10)
        print(f"  [OK] 오버레이 발행: {overlay_topic} (compressed)")
        print(f"  [OK] 오버레이 발행: {raw_overlay_topic} (raw, RViz용)")

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

        # ── 등록/리셋/대기 트리거 토픽 (RViz와 함께 쓰는 헤드리스 모드) ───
        self._reg_request = False
        self.create_subscription(Empty, "/robocart/register", self._on_register_cmd, 1)
        self.create_subscription(Empty, "/robocart/reset",    self._on_reset_cmd,    1)
        self.create_subscription(Empty, "/robocart/wait",     self._on_wait_cmd,     1)
        self.create_subscription(Empty, "/robocart/resume",   self._on_resume_cmd,   1)
        print("  [OK] 등록/리셋/대기 명령 토픽 구독")
        print("       등록: ros2 topic pub /robocart/register std_msgs/Empty {} --once")
        print("       리셋: ros2 topic pub /robocart/reset    std_msgs/Empty {} --once")
        print("       대기: ros2 topic pub /robocart/wait     std_msgs/Empty {} --once")
        print("       재개: ros2 topic pub /robocart/resume   std_msgs/Empty {} --once")
        print("       시각화: rviz2  →  Image(/robocart/image_overlay/compressed)")

        print("[inference_node] 준비 완료 (Ctrl+C 종료)")

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
            return

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

        # ── 대기 모드 ─────────────────────────────────
        if self.mode == "wait":
            self._draw_wait_overlay(frame, boxes)
            self._publish_overlay(frame)
            return

        # ── 등록 모드 ─────────────────────────────────
        if self.mode == "register":
            self._draw_register_overlay(frame, boxes)

            # 카운트다운 + 시간 경과 시 자동 등록 트리거
            if self.register_deadline is not None:
                remaining = self.register_deadline - time.time()
                if remaining > 0:
                    cv2.putText(frame, f"REG IN {int(remaining)+1}s",
                                (10, 70), cv2.FONT_HERSHEY_SIMPLEX,
                                1.2, (0, 200, 255), 3)
                elif boxes:
                    # 시간 만료 + 사람 있음 → 자동 등록 실행
                    self._reg_request = True
                    self.register_deadline = None
                else:
                    # 시간 만료 + 사람 없음 → 사람 보일 때까지 자동 등록 대기
                    cv2.putText(frame, "WAITING FOR PERSON",
                                (10, 70), cv2.FONT_HERSHEY_SIMPLEX,
                                0.9, (0, 200, 255), 2)
                    self._reg_request = True   # 보이는 첫 프레임에 등록

            if self._reg_request and boxes:
                # 가장 큰 박스 선택
                largest = max(boxes, key=lambda d: (d["bbox"][2] - d["bbox"][0]) *
                                                    (d["bbox"][3] - d["bbox"][1]))
                feat = extract_features(frame, largest["bbox"], reid_model=self.reid_model)
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

        # 오버레이 발행 (RViz에서 /robocart/image_overlay/compressed 로 시각화)
        self._publish_overlay(frame)

    # ════════════════════════════════════════════════════
    # 추종 단계
    # ════════════════════════════════════════════════════
    def _track_step(self, frame, boxes: list[dict], w: int) -> None:
        h = frame.shape[0]
        best = None   # (score, bbox)
        if self.registered is not None:
            for d in boxes:
                cf = extract_features(frame, d["bbox"], reid_model=self.reid_model)
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
                self.lost_since = None       # 사람 다시 찾음 → 자동 리셋 카운트다운 취소
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                bbox_h = y2 - y1
                self.prev_cx = cx
                self._send({"type": "track", "x": int(cx), "y": int(cy), "score": round(score, 3)})
                # 바퀴 주행 명령 (별도 송신)
                if self.drive_enable:
                    linear, angular = self._compute_drive(cx, bbox_h, w, h)
                    self._send({"type": "drive", "linear": round(linear, 3), "angular": round(angular, 3)})
                # 시각화 (초록)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                cv2.putText(frame, f"TRACK {score:.2f}", (x1, max(20, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if self.drive_enable:
                    cv2.putText(frame, f"DRIVE lin={linear:+.2f} ang={angular:+.2f}",
                                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                self._draw_other_boxes(frame, boxes, (x1, y1, x2, y2))
                return

        # 잠금 잃음 → lost 송신 + 자동 리셋 카운트다운 시작
        if self.locked and (now - self.last_seen_t) > self.lost_to:
            self.locked = False
            self.prev_cx = None
            self._send({"type": "lost"})
            if self.drive_enable:
                self._send({"type": "stop"})    # 바퀴도 정지
            print("[inference_node] 사람 놓침 → lost 송신")
            if self.auto_reset_sec > 0:
                self.lost_since = now

        # 자동 리셋 카운트다운 (lost 상태 + 카운트다운 활성)
        if not self.locked and self.lost_since is not None and self.auto_reset_sec > 0:
            elapsed = now - self.lost_since
            remaining = self.auto_reset_sec - elapsed
            if remaining > 0:
                cv2.putText(frame, f"NEXT USER IN {int(remaining)+1}s",
                            (10, 110), cv2.FONT_HERSHEY_SIMPLEX,
                            0.9, (0, 200, 255), 2)
            else:
                self._do_reset(reason=f"추종 대상 {self.auto_reset_sec:.0f}초 잃음")

        self._draw_other_boxes(frame, boxes, None)

    def _draw_other_boxes(self, frame, boxes: list[dict], locked_bbox) -> None:
        for d in boxes:
            if d["bbox"] == locked_bbox:
                continue
            x1, y1, x2, y2 = d["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 180, 180), 1)

    def _compute_drive(self, cx: float, bbox_h: int, w: int, h: int) -> tuple[float, float]:
        """사람 bbox 위치/크기 → 선속도(전진), 각속도(회전) 계산.

        - bbox 높이/화면 높이 비율로 거리 추정 (작으면 멀어서 전진, 크면 가까워서 정지)
        - bbox cx가 화면 가운데 데드존을 벗어나면 몸체 회전 (서보 한계 백업)
        """
        # 1) 선속도: 거리 기반 (bbox 높이 비율)
        h_ratio = bbox_h / h if h > 0 else 0.0
        if h_ratio < self.bbox_h_min:
            linear = self.fwd_speed         # 사람 멀다 → 전진
        elif h_ratio > self.bbox_h_max:
            linear = 0.0                    # 사람 가깝다 → 정지 (후진은 안전상 비활성)
        else:
            linear = 0.0                    # 적정 거리

        # 2) 각속도: 좌우 위치 기반 (가운데 데드존 안이면 서보가 처리)
        center_x = w / 2.0
        offset = cx - center_x
        dead_zone_px = self.turn_dz_ratio * w / 2.0   # 화면 가운데 좌우 N% 안
        if abs(offset) > dead_zone_px:
            # 사람이 오른쪽이면 angular > 0 (반시계 → 카트가 우회전), 왼쪽이면 < 0
            # ROS 표준: angular.z > 0 = 반시계, 본체 좌회전
            # 사람이 우측이면 카트가 우회전해야 → angular < 0
            angular = -self.turn_speed if offset > 0 else self.turn_speed
        else:
            angular = 0.0

        return linear, angular

    # ════════════════════════════════════════════════════
    # 등록/리셋 명령 콜백 (ros2 topic pub 으로 트리거)
    # ════════════════════════════════════════════════════
    def _on_register_cmd(self, _msg) -> None:
        print("[inference_node] 등록 명령 수신 → 다음 프레임의 가장 큰 사람을 등록")
        self._reg_request = True
        self.mode = "register"

    def _on_reset_cmd(self, _msg) -> None:
        self._do_reset(reason="수동 리셋 명령")

    def _on_wait_cmd(self, _msg) -> None:
        """대기 명령 → 등록 정보는 유지하고 추종만 일시 정지 + 모터 중앙 복귀."""
        if self.registered is None:
            print("[inference_node] 대기 명령 무시 — 등록된 사용자가 없음")
            return
        print("[inference_node] 대기 명령 수신 → 추종 정지, 모터 중앙 복귀")
        self.mode = "wait"
        self.locked = False
        self.prev_cx = None
        self.lost_since = None    # 자동 리셋 카운트다운 해제 (대기 중에는 사라져도 OK)
        self._send({"type": "center"})
        if self.drive_enable:
            self._send({"type": "stop"})

    def _on_resume_cmd(self, _msg) -> None:
        """대기 종료 → 등록된 사용자 즉시 재추종 (재등록 없이)."""
        if self.mode != "wait":
            print(f"[inference_node] 재개 명령 무시 — 현재 모드: {self.mode}")
            return
        if self.registered is None:
            print("[inference_node] 재개 명령 무시 — 등록된 사용자가 없음")
            return
        print("[inference_node] 재개 명령 수신 → 추종 재개")
        self.mode = "track"

    def _do_reset(self, reason: str) -> None:
        """등록 정보 삭제 + register mode 복귀 + 자동 등록 타이머 재시작."""
        print(f"[inference_node] {reason} → 등록 정보 삭제, 등록 모드 전환")
        if self.feat_path.exists():
            self.feat_path.unlink()
        self.registered = None
        self.locked = False
        self.prev_cx = None
        self.lost_since = None
        self.mode = "register"
        self._reg_request = False
        if self.auto_reg_sec > 0:
            self.register_deadline = time.time() + self.auto_reg_sec
            print(f"[inference_node] {self.auto_reg_sec:.0f}초 후 자동 등록")
        else:
            self.register_deadline = None

    def _draw_register_overlay(self, frame, boxes: list[dict]) -> None:
        h, w = frame.shape[:2]
        cv2.putText(frame, "REGISTER MODE — press R when ready",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        for d in boxes:
            x1, y1, x2, y2 = d["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)

    def _draw_wait_overlay(self, frame, boxes: list[dict]) -> None:
        """대기 모드: 사람 박스만 회색 + WAITING 표시 (추종/매칭 X)."""
        cv2.putText(frame, "WAITING — press resume to continue",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)
        for d in boxes:
            x1, y1, x2, y2 = d["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 180, 180), 1)

    # ════════════════════════════════════════════════════
    def _publish_overlay(self, frame) -> None:
        now = self.get_clock().now().to_msg()
        # compressed (다운스트림 호환)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            msg = CompressedImage()
            msg.header.stamp = now
            msg.header.frame_id = "camera"
            msg.format = "jpeg"
            msg.data = buf.tobytes()
            self.overlay_pub.publish(msg)
        # raw (RViz Image 디스플레이용) — cv_bridge 미사용 (NumPy 2.x 호환)
        raw = _bgr_to_imgmsg(frame)
        raw.header.stamp = now
        raw.header.frame_id = "camera"
        self.overlay_raw_pub.publish(raw)


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
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
