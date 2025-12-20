#edgeflow/comms.py
import redis
import socket
import time
import os
import struct
import json
import numpy as np
import cv2

class RedisBroker:
    def __init__(self, host='localhost', port=6379, key='video_stream'):
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.key = key
        self.redis = self._connect()

    def _connect(self):
        # 연결 재시도 로직
        while True:
            try:
                r = redis.Redis(host=self.host, port=self.port, socket_timeout=5)
                r.ping()
                return r
            except redis.ConnectionError:
                print(f"⚠️ Redis 연결 실패 ({self.host}). 3초 후 재시도...")
                time.sleep(3)

    def push(self, data):
        try: self.redis.rpush(self.key, data)
        except: pass

    def trim(self, size=1):
        try: self.redis.ltrim(self.key, -size, -1)
        except: pass

    def pop(self, timeout=0):
        try:
            res = self.redis.blpop(self.key, timeout=timeout)
            return res[1] if res else None
        except: return None

class GatewaySender:
    def __init__(self, host='localhost', port=8080):
        self.host = host or os.getenv('GATEWAY_HOST', 'localhost')
        self.port = port or int(os.getenv('GATEWAY_PORT', 8080))
        self.sock = None

    def _connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
        except: self.sock = None

    def send(self, data):
        if not self.sock: self._connect()
        if not self.sock: return False
        try:
            length = len(data)
            self.sock.sendall(length.to_bytes(4, 'big') + data)
            return True
        except:
            self.sock.close()
            self.sock = None
            return False


class Frame:
    def __init__(self, frame_id=0, timestamp=0.0, meta=None, data=None):
        self.frame_id = frame_id
        self.timestamp = timestamp
        self.meta = meta or {}
        self.data = data  # 사용자에게는 항상 Numpy(또는 Raw) 상태로 유지

    @classmethod
    def from_bytes(cls, raw_bytes, is_image=True):
        """네트워크/Redis에서 온 바이트를 객체로 변환 (역직렬화)"""
        if not raw_bytes or len(raw_bytes) < 16: return None
        
        try:
            f_id, ts = struct.unpack('!Id', raw_bytes[:12])
            json_len = struct.unpack('!I', raw_bytes[12:16])[0]
            meta = json.loads(raw_bytes[16:16+json_len].decode('utf-8'))
            payload = raw_bytes[16+json_len:]

            if is_image and len(payload) > 0:
                nparr = np.frombuffer(payload, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None: payload = img
                
            return cls(frame_id=f_id, timestamp=ts, meta=meta, data=payload)
        except Exception:
            return None

    def to_bytes(self):
        """객체를 Redis/TCP 전송용 바이트로 변환 (직렬화)"""
        # [핵심] 넘파이면 JPEG로, 이미 바이트면 그대로 처리 (자동 보정)
        if isinstance(self.data, np.ndarray):
            _, buf = cv2.imencode('.jpg', self.data)
            data_bytes = buf.tobytes()
        else:
            data_bytes = self.data if isinstance(self.data, bytes) else b""

        meta_bytes = json.dumps(self.meta).encode('utf-8')
        header = struct.pack('!Id', self.frame_id, self.timestamp)
        meta_header = struct.pack('!I', len(json_bytes))
        
        return header + meta_header + meta_bytes + data_bytes