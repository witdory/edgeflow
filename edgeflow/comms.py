#edgeflow/comms.py
import redis
import socket
import time
import os

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