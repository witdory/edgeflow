#edgeflow/comms/socket_client.py
import socket
import os
import time

class GatewaySender:
    def __init__(self, host='localhost', port=8080):
        self.host = host or os.getenv('GATEWAY_HOST', 'localhost')
        self.port = port or int(os.getenv('GATEWAY_PORT', 8080))
        self.sock = None

    def _connect(self):
        """TCP 소켓 연결 시도"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 타임아웃 설정으로 무한 대기 방지
            self.sock.settimeout(5.0)
            self.sock.connect((self.host, self.port))
        except Exception as e:
            # print(f"Gateway Connect Fail: {e}") # 너무 잦은 로그 방지
            self.sock = None

    def send(self, data):
        """Length-Prefixed Framing 방식으로 데이터 전송"""
        if not self.sock:
            self._connect()
        
        if not self.sock:
            return False

        try:
            # 4바이트 길이 헤더 + 실제 데이터 전송
            length = len(data)
            self.sock.sendall(length.to_bytes(4, 'big') + data)
            return True
        except Exception:
            # 소켓 에러 시 닫고 초기화 (다음 호출 때 재연결 시도)
            if self.sock:
                self.sock.close()
            self.sock = None
            return False