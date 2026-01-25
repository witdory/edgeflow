#edgeflow/comms/broker.py
import redis
import time
import os
from typing import Dict
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
        wait_time = 1
        while True:
            try:
                r = redis.Redis(host=self.host, port=self.port, socket_timeout=5)
                r.ping() # 연결 테스트
                print(f"✅ Redis Connected: {self.host}:{self.port}")
                return r
            except redis.ConnectionError:
                print(f"⚠️ Redis Connection Failed ({self.host}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 30) # Max 30s wait

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
            self._redis.ltrim(topic, -size, -1) # Redis List Trim (Right is new)
            # [신규] Limit 정보 저장 (모니터링용)
            self._redis.set(f"edgeflow:meta:limit:{topic}", size)
        except Exception:
            pass

    def queue_size(self, topic: str) -> int:
        """대기열 크기 반환"""
        self._ensure_connected()
        try:
            return self._redis.llen(topic)
        except Exception:
            return 0

    def get_queue_stats(self) -> Dict[str, Dict[str, int]]:
        """모든 큐 상태 반환"""
        self._ensure_connected()
        stats = {}
        try:
            # 1. 모든 키 스캔 (최적화 필요하지만 일단 keys)
            # 실제 큐 이름 패턴이 명확하지 않으므로, known topics를 관리하거나 규칙 필요
            # 여기서는 간단히 limit 메타데이터가 있는 토픽만 조회하는 전략 사용
            meta_keys = self._redis.keys("edgeflow:meta:limit:*")
            
            for key in meta_keys:
                key_str = key.decode('utf-8')
                topic = key_str.replace("edgeflow:meta:limit:", "")
                
                limit_bytes = self._redis.get(key)
                limit = int(limit_bytes) if limit_bytes else 0
                current = self._redis.llen(topic)
                
                stats[topic] = {"current": current, "max": limit}
        except Exception as e:
            print(f"Redis Stats Error: {e}")
        return stats

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

    # ========== Serialization Protocol ==========
    
    def to_config(self) -> dict:
        """멀티프로세싱용 설정 딕셔너리 반환"""
        return {
            "__class_path__": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "host": self.host,
            "port": self.port
        }
    
    @classmethod
    def from_config(cls, config: dict) -> 'RedisBroker':
        """설정으로부터 인스턴스 생성"""
        return cls(host=config.get("host"), port=config.get("port"))