# edgeflow/comms/brokers/dual_redis.py
import redis.exceptions
import struct
import time
from typing import Dict
from .base import BrokerInterface # 기본 추상 클래스

from ...config import settings

#검증 필요
class DualRedisBroker(BrokerInterface):
    def __init__(self, ctrl_host=None, ctrl_port=None, 
                       data_host=None, data_port=None):
        
        # 인자 없으면 config.py(환경변수/상수) 값 사용
        ctrl_host = ctrl_host or settings.REDIS_HOST
        ctrl_port = ctrl_port or settings.REDIS_PORT
        data_host = data_host or settings.DATA_REDIS_HOST
        data_port = data_port or settings.DATA_REDIS_PORT

        # 1. 제어용 Redis (큐, 상태)
        self.ctrl_redis = redis.Redis(host=ctrl_host, port=ctrl_port)
        
        # 2. 데이터용 Redis (이미지 저장소)
        # 스마트 로컬 감지: localhost인 경우 연결 테스트 후 폴백
        self.data_redis = self._connect_data_redis(data_host, data_port, ctrl_port)

    def _connect_data_redis(self, host, port, fallback_port):
        """
        Data Redis 연결 시도. 실패 시(로컬 환경 등) Control Redis 포트로 폴백.
        """
        # 1. 원래 설정대로 연결 시도 (Timeout 0.5초로 줄임)
        r = redis.Redis(host=host, port=port, socket_connect_timeout=0.5)
        
        # 로컬호스트가 아니면 바로 리턴 (프로덕션/K8s 환경은 설정 무조건 신뢰)
        if host not in ("localhost", "127.0.0.1"):
            return r

        try:
            r.ping()
            return r
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
            # 2. 연결 실패 시 폴백 시도
            print(f"⚠️ [DualRedis] Failed to connect to Data Redis at {host}:{port}.")
            print(f"🔄 [DualRedis] Falling back to Control Redis port ({fallback_port}) for local testing.")
            
            fallback_r = redis.Redis(host=host, port=fallback_port)
            return fallback_r

    def push(self, topic, frame_bytes):
        """
        데이터는 Data Redis에 저장하고, ID만 Ctrl Redis 큐에 넣음
        """
        if len(frame_bytes) < 4:
            return

        # [수정] Pickle 대신 Frame 헤더(struct)에서 직접 ID 추출
        frame_id = struct.unpack('!I', frame_bytes[:4])[0]
        
        # 1. [Data Plane] 무거운 데이터 저장
        data_key = f"{topic}:data:{frame_id}"
        self.data_redis.set(data_key, frame_bytes, ex=5)
        
        # 2. [Control Plane] 가벼운 ID 줄 세우기
        self.ctrl_redis.lpush(topic, str(frame_id))
        
        # [삭제] 여기서 ltrim 하지 않음 (Producer Handler가 trim 호출함)
        # self.ctrl_redis.ltrim(topic, 0, 50)

    def pop(self, topic, timeout=0.1):
        """
        Ctrl Redis에서 ID를 꺼내고, Data Redis에서 실제 데이터를 가져옴
        """
        item = self.ctrl_redis.brpop(topic, timeout=timeout)
        if not item:
            return None
            
        _, frame_id_bytes = item
        frame_id = frame_id_bytes.decode('utf-8')
        
        data_key = f"{topic}:data:{frame_id}"
        raw_data = self.data_redis.get(data_key)
        
        if raw_data:
            return raw_data
        else:
            print(f"⚠️ Data missing in Redis #2 for ID: {frame_id}")
            return None

    def trim(self, topic, size):
        self.ctrl_redis.ltrim(topic, 0, size - 1)  # [Fix] inclusive index, so -1
        # [신규] Limit 정보 저장
        self.ctrl_redis.set(f"edgeflow:meta:limit:{topic}", size)

    def queue_size(self, topic: str) -> int:
        """대기열 크기 반환 (Control Redis 기준)"""
        try:
            return self.ctrl_redis.llen(topic)
        except Exception:
            return 0

    def get_queue_stats(self) -> Dict[str, Dict[str, int]]:
        """모든 큐 상태 반환"""
        stats = {}
        try:
            # Limit 메타데이터가 있는 토픽 기반으로 조회
            meta_keys = self.ctrl_redis.keys("edgeflow:meta:limit:*")
            
            for key in meta_keys:
                key_str = key.decode('utf-8')
                topic = key_str.replace("edgeflow:meta:limit:", "")
                
                limit_bytes = self.ctrl_redis.get(key)
                limit = int(limit_bytes) if limit_bytes else 0
                current = self.ctrl_redis.llen(topic)
                
                stats[topic] = {"current": current, "max": limit}
        except Exception as e:
            print(f"DualRedis Stats Error: {e}")
        return stats

    # ========== Serialization Protocol ==========
    
    def to_config(self) -> dict:
        """멀티프로세싱용 설정 딕셔너리 반환"""
        return {
            "__class_path__": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "ctrl_host": self.ctrl_redis.connection_pool.connection_kwargs.get('host'),
            "ctrl_port": self.ctrl_redis.connection_pool.connection_kwargs.get('port'),
            "data_host": self.data_redis.connection_pool.connection_kwargs.get('host'),
            "data_port": self.data_redis.connection_pool.connection_kwargs.get('port')
        }
    
    @classmethod
    def from_config(cls, config: dict) -> 'DualRedisBroker':
        """설정으로부터 인스턴스 생성"""
        return cls(
            ctrl_host=config.get("ctrl_host"),
            ctrl_port=config.get("ctrl_port"),
            data_host=config.get("data_host"),
            data_port=config.get("data_port")
        )