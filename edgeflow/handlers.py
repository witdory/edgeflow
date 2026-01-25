# edgeflow/handlers.py
import socket
import struct
import asyncio

class RedisHandler:
    def __init__(self, broker, topic, queue_size=1):
        self.broker = broker
        self.topic = topic
        self.queue_size = queue_size

    def send(self, frame):
        # Redis 브로커를 통해 전송 (기존 Broker.push 재사용)
        self.broker.push(self.topic, frame.to_bytes())

        if self.queue_size > 0:
            self.broker.trim(self.topic, self.queue_size)

class TcpHandler:
    def __init__(self, host, port, source_id):
        self.host = host
        self.port = port
        self.source_id = source_id
        self.sock = None

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(0.5)  # Fast fail if Gateway not ready
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None) # Blocking mode for sending
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (socket.timeout, ConnectionRefusedError, OSError):
            # print(f"⚠️ TCP Connect Failed: {e}") 
            # Quietly fail to allow retry in next frame
            if self.sock:
                self.sock.close()
            self.sock = None

    def send(self, frame):
        if self.sock is None:
            self.connect()
            if self.sock is None: return

        try:
            # 1. [Identity] Gateway 라우팅을 위해 소스 ID 주입
            # 원본 프레임의 메타데이터를 수정하는 것이므로 주의 (복사본 사용 권장되나 성능상 직접 수정)
            frame.meta["topic"] = self.source_id

            # 2. [Serialization] Frame -> Bytes
            packet_body = frame.to_bytes()
            
            # 3. [Framing] 길이 헤더 추가 (4 bytes)
            length_header = struct.pack('>I', len(packet_body))
            
            # print(f"DEBUG: TcpHandler sending topic={frame.meta.get('topic')} len={len(packet_body)}")
            self.sock.sendall(length_header + packet_body)

        except (BrokenPipeError, ConnectionResetError):
            self.sock.close()
            self.sock = None
        except Exception as e:
            # print(f"⚠️ Send Error: {e}")
            self.sock = None