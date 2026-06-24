"""
return_trigger_bridge — 백엔드 ↔ ROS 결제 완료 브릿지

배경:
  node-backend (order.controller.js)의 결제 완료 처리 끝에
  `sendRobotReturnCommand()` 빈 스텁이 있음. 이걸 채우면 ROS에 신호 가능.

설계:
  ROS 노드가 HTTP 서버를 띄우고, 백엔드가 결제 완료 시 그쪽으로 POST.
  Socket.io 안 쓰는 이유: ROS용 인증 토큰 없음 + 단방향 이벤트라 HTTP가 더 단순.

엔드포인트:
  POST /return       — `/robocart/return` Empty 발행 (도킹 복귀 시작)
  GET  /health       — 200 OK (헬스체크)

백엔드 측 호출 예 (node-backend가 구현해야 할 부분):
  await fetch(`http://<ros-bridge-host>:5555/return`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({robot_serial: serial})
  });

사용:
  ros2 run robocart_navigation return_trigger_bridge
  ros2 run robocart_navigation return_trigger_bridge --ros-args -p port:=5555 -p bind_host:=0.0.0.0
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty


class _BridgeHandler(BaseHTTPRequestHandler):
    """HTTP 요청 처리. 노드 인스턴스는 server.bridge_node 로 접근."""

    def log_message(self, format, *args):
        self.server.bridge_node.get_logger().info(
            f"{self.client_address[0]} - {format % args}"
        )

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/return":
            self._respond(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(body_raw) if body_raw else {}
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid json"})
            return

        node = self.server.bridge_node
        node.publish_return(body.get("robot_serial", "unknown"))
        self._respond(200, {"status": "return_triggered"})

    def _respond(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReturnTriggerBridge(Node):
    def __init__(self) -> None:
        super().__init__("return_trigger_bridge")

        self.declare_parameter("port", 5555)
        self.declare_parameter("bind_host", "0.0.0.0")

        port = int(self.get_parameter("port").value)
        host = str(self.get_parameter("bind_host").value)

        self._pub = self.create_publisher(Empty, "/robocart/return", 1)

        self._server = HTTPServer((host, port), _BridgeHandler)
        self._server.bridge_node = self  # 핸들러에서 접근

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        self.get_logger().info(
            f"return_trigger_bridge 준비 — http://{host}:{port}/return (POST), /health (GET)"
        )

    def publish_return(self, robot_serial: str) -> None:
        self.get_logger().info(f"결제 완료 수신 (robot_serial={robot_serial}) → /robocart/return 발행")
        self._pub.publish(Empty())

    def destroy_node(self):
        self._server.shutdown()
        self._server.server_close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ReturnTriggerBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
