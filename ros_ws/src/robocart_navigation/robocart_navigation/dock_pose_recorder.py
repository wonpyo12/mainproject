"""
dock_pose_recorder — 도킹 좌표 자동 저장 서비스

문제: return_params.yaml의 home_pose(x, y, yaw)를 줄자로 재서 손으로 적는 건 비현실적.
해결: 로봇을 도킹 위치에 두고 ROS Service 한 번 호출 → 현재 TF(map→base_footprint)를
      읽어서 yaml에 자동 저장.

서비스:
  /set_dock_pose  (std_srvs/Trigger)  — 현재 위치를 home_pose로 저장

파라미터:
  map_frame       (default: map)
  robot_frame     (default: base_footprint)
  output_path     (default: 빈 문자열 → 패키지 share/config/return_params.yaml 자동 탐색)
  tf_timeout_sec  (default: 2.0)

사용 (실전 배치):
  # 1) Nav2/AMCL 실행 + 로봇을 도킹 위치에 두기
  # 2) 다른 터미널에서:
  ros2 service call /set_dock_pose std_srvs/srv/Trigger

  # 또는 wait_return.launch.py 띄우면 자동으로 함께 실행됨
"""
import math
import os
import yaml
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener, TransformException
from ament_index_python.packages import get_package_share_directory


def _quat_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """쿼터니언 → yaw (rad). Z축 회전만 추출."""
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


class DockPoseRecorder(Node):
    def __init__(self) -> None:
        super().__init__("dock_pose_recorder")

        self.declare_parameter("map_frame", "map")
        self.declare_parameter("robot_frame", "base_footprint")
        self.declare_parameter("output_path", "")
        self.declare_parameter("tf_timeout_sec", 2.0)

        self._map_frame = str(self.get_parameter("map_frame").value)
        self._robot_frame = str(self.get_parameter("robot_frame").value)
        self._tf_timeout = float(self.get_parameter("tf_timeout_sec").value)

        self._output_path = self._resolve_output_path()

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        self._srv = self.create_service(Trigger, "/set_dock_pose", self._on_set_dock_pose)

        self.get_logger().info(
            f"dock_pose_recorder 준비 — /set_dock_pose 대기 "
            f"(map={self._map_frame}, robot={self._robot_frame}, out={self._output_path})"
        )

    def _resolve_output_path(self) -> str:
        explicit = str(self.get_parameter("output_path").value).strip()
        if explicit:
            return explicit
        share = get_package_share_directory("robocart_navigation")
        return os.path.join(share, "config", "return_params.yaml")

    def _on_set_dock_pose(self, _req: Trigger.Request, res: Trigger.Response) -> Trigger.Response:
        try:
            tf = self._tf_buffer.lookup_transform(
                self._map_frame,
                self._robot_frame,
                rclpy.time.Time(),
                Duration(seconds=self._tf_timeout),
            )
        except TransformException as e:
            msg = f"TF {self._map_frame} → {self._robot_frame} 조회 실패: {e}"
            self.get_logger().error(msg)
            res.success = False
            res.message = msg
            return res

        x = float(tf.transform.translation.x)
        y = float(tf.transform.translation.y)
        yaw = _quat_to_yaw(
            tf.transform.rotation.x,
            tf.transform.rotation.y,
            tf.transform.rotation.z,
            tf.transform.rotation.w,
        )

        try:
            self._write_yaml(x, y, yaw)
        except OSError as e:
            msg = f"yaml 쓰기 실패: {e}"
            self.get_logger().error(msg)
            res.success = False
            res.message = msg
            return res

        msg = f"home_pose 저장 → x={x:.3f}, y={y:.3f}, yaw={yaw:.3f} → {self._output_path}"
        self.get_logger().info(msg)
        res.success = True
        res.message = msg
        return res

    def _write_yaml(self, x: float, y: float, yaw: float) -> None:
        """기존 yaml을 읽어 home_pose만 갱신하고 다시 쓰기 (다른 키 보존)."""
        path = Path(self._output_path)
        data: dict = {}
        if path.exists():
            with path.open("r") as f:
                data = yaml.safe_load(f) or {}

        node = data.setdefault("mode_controller", {})
        params = node.setdefault("ros__parameters", {})
        params["home_pose"] = {"x": round(x, 3), "y": round(y, 3), "yaw": round(yaw, 3)}
        params.setdefault("nav_action_name", "navigate_to_pose")

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DockPoseRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
