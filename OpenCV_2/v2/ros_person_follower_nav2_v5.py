#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ros_person_follower_nav2_v5 — 엔트리 진입점 스크립트.

기능별로 분리된 `follower_v5` 모듈 패키지를 호출하여 실행합니다.
구조:
  - follower_v5/config.py: 설정 및 인자 파서
  - follower_v5/utils.py: DBG 로깅, 음성 안내, LED 통신
  - follower_v5/camera.py: MjpegCamera 스트림 수신
  - follower_v5/worker.py: DetectionWorker (YOLO+ReID+색상)
  - follower_v5/ros_node.py: RobotController (ROS2 P제어/Nav2)
  - follower_v5/tracker_loop.py: 등록(register) 및 추종 루프(run_tracking)
  - follower_v5/main.py: 진입점 실행 함수
"""

import sys
from follower_v5 import main

if __name__ == "__main__":
    sys.exit(main())
