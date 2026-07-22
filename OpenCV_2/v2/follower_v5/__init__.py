# -*- coding: utf-8 -*-
"""follower_v5 패키지 모듈.

분산 처리 기반 YOLOv8 + ReID + MOSSE 보간 + Nav2 복귀 추종 패키지.
"""

from __future__ import annotations

from .camera import MjpegCamera
from .config import parse_args
from .main import main
from .ros_node import RobotController
from .tracker_loop import register, run_tracking
from .worker import DetectionWorker

__all__ = [
    "parse_args",
    "main",
    "MjpegCamera",
    "DetectionWorker",
    "RobotController",
    "register",
    "run_tracking",
]
