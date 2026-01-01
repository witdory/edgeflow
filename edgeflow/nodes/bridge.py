# edgeflow/nodes/bridge.py
import socket
import struct
import time
from .base import BaseNode
from ..comms import Frame
from ..config import settings

class BridgeNode(BaseNode):
    """
    [Redis] -> [Bridge] -> (TCP Socket) -> [Gateway]
    Redis 토픽을 구독(Pop)하여, 결과값을 반환하지 않고 
    즉시 외부 TCP 서버(Gateway)로 전송하는 단방향 노드
    """
    def __init__(self, broker, input_topic, gateway_host='localhost', gateway_port=None):
        super().__init__(broker)
        self.input_topic = input_topic
        self.gateway_host = gateway_host or settings.GATEWAY_HOST
        self.gateway_port = gateway_port or settings.GATEWAY_TCP_PORT
        self.sock = None

    def setup(self):
        print(f"🌉 Bridge Node Started: {self.input_topic} >> {self.gateway_host}:{self.gateway_port}")
        self._connect()

    def _connect(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.gateway_host, self.gateway_port))
                print("✅ Connected to Gateway TCP!")
                break
            except Exception:
                time.sleep(2) # 재접속 대기

    def run(self):
        # ConsumerNode의 로직을 빌려쓰지 않고, 직접 루프를 돕니다. (훨씬 명확함)
        while self.running:
            # 1. Redis에서 데이터 꺼내기 (Blocking Pop)
            data = self.broker.pop(self.input_topic, timeout=1.0)
            if not data:
                continue

            # 2. TCP 전송 (연결 끊기면 재접속)
            if self.sock is None:
                self._connect()

            try:
                # Gateway가 읽는 방식(길이 4바이트 + 본문)으로 전송
                header = struct.pack('>I', len(data))
                self.sock.sendall(header + data)
            except (BrokenPipeError, ConnectionResetError):
                print("❌ Gateway Disconnected. Reconnecting...")
                self.sock.close()
                self.sock = None