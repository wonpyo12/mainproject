#!/usr/bin/env python3
"""
[라파] 복귀 컨트롤러 — /robocart/return 수신 → Nav2 NavigateToPose 로 홈 복귀

HJ의 robocart_navigation/mode_controller.py 를 현장 스택에 맞게 개조:
  - cmd_server 는 String("RETURN_HOME") 을 발행하고, HJ 원본은 Empty 를 구독해
    타입이 어긋난다 → 여기서는 String 과 Empty 둘 다 구독해 어느 쪽이든 동작.
  - 홈 좌표는 파라미터 (기본 map 원점 0,0,0 = 매핑 시작점/도킹 위치)

경로: 웹 복귀 버튼 → 백엔드 → TCP → cmd_server → /robocart/return → 여기 → Nav2

전제: Nav2 가동 + AMCL 정합(map 프레임) 상태여야 실제로 주행한다.

실행 (라파, bringup/Nav2 와 같은 도메인):
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=0
  python3 return_controller.py --ros-args -p home_pose.x:=0.0 -p home_pose.y:=0.0
"""
import math

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from action_msgs.msg import GoalStatus
from std_msgs.msg import Empty, String
from geometry_msgs.msg import PoseStamped, Quaternion, Twist
from nav2_msgs.action import NavigateToPose


def _yaw_to_quat(yaw):
    q = Quaternion()
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


class ReturnController(Node):
    def __init__(self):
        super().__init__("return_controller")

        self.declare_parameter("home_pose.x", 0.0)
        self.declare_parameter("home_pose.y", 0.0)
        self.declare_parameter("home_pose.yaw", 0.0)

        self.action_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self._goal_handle = None

        # cmd_server(String) / HJ mode_controller 규약(Empty) 모두 수용
        self.create_subscription(String, "/robocart/return", self._on_return, 1)
        self.create_subscription(Empty, "/robocart/return_empty", self._on_return, 1)

        # 긴급 정지/해제 (cmd_server HALT/RESUME → wait/resume 발행)
        self.create_subscription(Empty, "/robocart/wait", self._on_halt, 1)
        self.create_subscription(Empty, "/robocart/resume", self._on_resume, 1)

        # 도착하면 follower reset (다음 손님 등록 모드) — HJ 규약 유지
        self._reset_pub = self.create_publisher(Empty, "/robocart/reset", 1)
        # 긴급 정지 제동용 — Nav2 goal 취소 후 잔여 속도를 즉시 0으로
        self._vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self._brake_left = 0
        self.create_timer(0.1, self._brake_tick)

        self.get_logger().info(
            f"return_controller 준비 — home=({self.get_parameter('home_pose.x').value}, "
            f"{self.get_parameter('home_pose.y').value})")

    def _on_return(self, _msg):
        if self._goal_handle is not None:
            self.get_logger().info("이미 복귀 주행 중 — 중복 무시")
            return
        if not self.action_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error("Nav2 NavigateToPose 액션 서버 없음 — Nav2 실행 중인지 확인")
            return

        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(self.get_parameter("home_pose.x").value)
        pose.pose.position.y = float(self.get_parameter("home_pose.y").value)
        pose.pose.orientation = _yaw_to_quat(float(self.get_parameter("home_pose.yaw").value))

        goal = NavigateToPose.Goal()
        goal.pose = pose
        self.get_logger().info(
            f"복귀 시작 → ({pose.pose.position.x:.2f}, {pose.pose.position.y:.2f})")

        send_future = self.action_client.send_goal_async(goal)
        send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        handle = future.result()
        if not handle.accepted:
            self.get_logger().warn("Nav2 goal 거절됨")
            return
        self._goal_handle = handle
        handle.get_result_async().add_done_callback(self._on_result)

    def _on_result(self, future):
        status = future.result().status
        self._goal_handle = None
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info("도킹 도착 → follower reset 발행")
            self._reset_pub.publish(Empty())
        else:
            self.get_logger().info(f"복귀 종료 (status={status}, reset 안 함)")

    def _on_halt(self, _msg):
        # 긴급 정지: 진행 중 Nav2 goal 취소 + 1초간 0속도 제동
        if self._goal_handle is not None:
            self.get_logger().info("긴급 정지 — 복귀 주행 취소")
            self._goal_handle.cancel_goal_async()
            self._goal_handle = None
        else:
            self.get_logger().info("긴급 정지 — 진행 중 goal 없음, 제동만")
        self._brake_left = 10   # 0.1s × 10 = 1초간 0속도 발행

    def _on_resume(self, _msg):
        self._brake_left = 0    # 제동 해제 (추종 재개는 cmd_server 래치가 담당)
        self.get_logger().info("정지 해제 수신")

    def _brake_tick(self):
        if self._brake_left > 0:
            self._brake_left -= 1
            self._vel_pub.publish(Twist())


def main():
    rclpy.init()
    node = ReturnController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
