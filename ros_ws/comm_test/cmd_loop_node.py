#!/usr/bin/env python3
"""
ROS2 통신 검증용 미니 추적 노드 (로봇 없이 노트북 단독 테스트)

전체 파이프라인의 데이터 흐름만 검증한다:
  /image (sensor_msgs/Image) 구독
    → 가짜 계산 (프레임 평균 밝기를 사용자 위치라고 가정)
    → /cmd_vel (geometry_msgs/Twist) 발행

실행 (WSL):
  source /opt/ros/humble/setup.bash
  # 터미널1: 가짜 카메라
  ros2 run image_tools cam2image --ros-args -p burger_mode:=true
  # 터미널2: 이 노드
  python3 cmd_loop_node.py
  # 터미널3: 명령 확인
  ros2 topic echo /cmd_vel
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist


class CmdLoopNode(Node):
    def __init__(self):
        super().__init__('cmd_loop_node')
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.sub = self.create_subscription(Image, '/image', self.on_image, qos)
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.count = 0

    def on_image(self, msg: Image):
        # 실제 구현에서는 여기서 robocart의 인식/매칭을 호출한다.
        # 지금은 흐름 검증용으로 프레임 평균 밝기를 오프셋이라 가정.
        n = len(msg.data)
        mean = sum(msg.data[: min(n, 3000)]) / min(n, 3000) / 255.0  # 0~1

        twist = Twist()
        twist.angular.z = round((mean - 0.5) * 2.0, 3)  # -1 ~ +1
        twist.linear.x = 0.1
        self.pub.publish(twist)

        self.count += 1
        if self.count % 30 == 0:
            self.get_logger().info(
                f'{self.count} frames → cmd_vel(angular.z={twist.angular.z})')


def main():
    rclpy.init()
    node = CmdLoopNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
