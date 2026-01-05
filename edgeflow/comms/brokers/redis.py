#edgeflow/comms/broker.py
import redis
import time
import os
from .base import BrokerInterface

class RedisBroker(BrokerInterface):
    def __init__(self, host='localhost', port=6379):
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))

        self.redis = self._connect()

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
        try:
            self.redis.rpush(topic, data)
        except Exception as e:
            print(f"Redis Push Error: {e}")

    def trim(self, topic: str, size: int =1):
        """오래된 데이터 삭제 (메모리 관리)"""
        try:
            self.redis.ltrim(topic, -size, -1)
        except Exception:
            pass

    def pop(self, topic: str, timeout: int=0):
        """데이터 가져오기 (Consumer) - Blocking"""
        try:
            # blpop은 (key, value) 튜플을 반환하므로 value([1])만 리턴
            res = self.redis.blpop(topic, timeout=timeout)
            return res[1] if res else None
        except Exception as e:
            print(f"Redis Pop Error: {e}")
            return None

    def publish(self, channel: str, message: str):
        """Publish a message to a pub/sub channel."""
        try:
            self.redis.publish(channel, message)
        except Exception as e:
            print(f"Redis Publish Error: {e}")