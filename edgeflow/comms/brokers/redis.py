#edgeflow/comms/broker.py
import redis
import time
import os
from .base import BrokerInterface

class RedisBroker(BrokerInterface):
    def __init__(self, host=None, port=None):
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self._redis = None  # Lazy: 아직 연결 안 함

    def _ensure_connected(self):
        """첫 호출 시에만 연결, 이후엔 재사용"""
        if self._redis is None:
            self._redis = self._connect()
    
    def _connect(self):
        """Redis 연결 재시도 로직"""
        while True:
            try:
                r = redis.Redis(host=self.host, port=self.port, socket_timeout=5)
                r.ping() # 연결 테스트
                print(f"✅ Redis Connected: {self.host}:{self.port}")
                return r
            except redis.ConnectionError:
                print(f"⚠️ Redis Connection Failed ({self.host}). Retrying in 3s...")
                time.sleep(3)

    def push(self, topic: str, data: bytes):
        """데이터 큐에 넣기 (Producer)"""
        if not data: return
        self._ensure_connected()
        try:
            self._redis.rpush(topic, data)
        except Exception as e:
            print(f"Redis Push Error: {e}")

    def trim(self, topic: str, size: int =1):
        """오래된 데이터 삭제 (메모리 관리)"""
        self._ensure_connected()
        try:
            self._redis.ltrim(topic, -size, -1)
        except Exception:
            pass

    def pop(self, topic: str, timeout: int=0):
        """데이터 가져오기 (Consumer) - Blocking"""
        self._ensure_connected()
        try:
            # blpop은 (key, value) 튜플을 반환하므로 value([1])만 리턴
            res = self._redis.blpop(topic, timeout=timeout)
            return res[1] if res else None
        except Exception as e:
            print(f"Redis Pop Error: {e}")
            return None