"""
mode_controller — RoboCart 모드별 자율주행 제어

기존 follower 토픽 패턴(/robocart/{wait,resume,register,reset}) 과 동일하게
`/robocart/return` Empty 토픽을 구독해 도킹 위치로 자율 복귀.

토픽:
  /robocart/return  (Empty)  — return 모드 진입, Nav2 NavigateToPose 호출
  /robocart/wait    (Empty)  — 진행 중 복귀 취소 (제자리 정지)
  /robocart/resume  (Empty)  — 진행 중 복귀 취소 (추종 재개)

파라미터 (return_params.yaml):
  home_pose.x, home_pose.y, home_pose.yaw  — 복귀 좌표 (map frame 기준)

사용:
  ros2 run robocart_navigation mode_controller
"""
import math
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import Empty
from geometry_msgs.msg import PoseStamped, Quaternion
from nav2_msgs.action import NavigateToPose


def _yaw_to_quat(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


class ModeController(Node):
    def __init__(self) -> None:
        super().__init__("mode_controller")

        self.declare_parameter("home_pose.x", 0.0)
        self.declare_parameter("home_pose.y", 0.0)
        self.declare_parameter("home_pose.yaw", 0.0)
        self.declare_parameter("nav_action_name", "navigate_to_pose")

        self.action_client = ActionClient(
            self, NavigateToPose, self.get_parameter("nav_action_name").value
        )

        self._goal_handle = None

        self.create_subscription(Empty, "/robocart/return", self._on_return, 1)
        self.create_subscription(Empty, "/robocart/wait",   self._on_cancel, 1)
        self.create_subscription(Empty, "/robocart/resume", self._on_cancel, 1)

        self.get_logger().info(
            "mode_controller 준비 — /robocart/return 대기 "
            f"(home: x={self.get_parameter('home_pose.x').value}, "
            f"y={self.get_parameter('home_pose.y').value}, "
            f"yaw={self.get_parameter('home_pose.yaw').value})"
        )

    def _on_return(self, _msg: Empty) -> None:
        if not self.action_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error("Nav2 NavigateToPose 액션 서버 없음 — Nav2 실행 중인지 확인")
            return

        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(self.get_parameter("home_pose.x").value)
        pose.pose.position.y = float(self.get_parameter("home_pose.y").value)
        pose.pose.orientation = _yaw_to_quat(
            float(self.get_parameter("home_pose.yaw").value)
        )

        goal = NavigateToPose.Goal()
        goal.pose = pose

        self.get_logger().info(
            f"복귀 시작 → ({pose.pose.position.x:.2f}, {pose.pose.position.y:.2f})"
        )

        send_future = self.action_client.send_goal_async(goal)
        send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future) -> None:
        handle = future.result()
        if not handle.accepted:
            self.get_logger().warn("Nav2 goal 거절됨")
            return
        self._goal_handle = handle
        handle.get_result_async().add_done_callback(self._on_result)

    def _on_result(self, future) -> None:
        status = future.result().status
        self.get_logger().info(f"복귀 종료 (status={status})")
        self._goal_handle = None

    def _on_cancel(self, _msg: Empty) -> None:
        if self._goal_handle is None:
            return
        self.get_logger().info("복귀 취소")
        self._goal_handle.cancel_goal_async()
        self._goal_handle = None


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ModeController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
