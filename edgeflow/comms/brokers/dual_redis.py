# edgeflow/comms/brokers/dual_redis.py
import redis
import pickle
import time
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
        self.data_redis = redis.Redis(host=data_host, port=data_port)

    def push(self, topic, frame_bytes):
        """
        데이터는 Data Redis에 저장하고, ID만 Ctrl Redis 큐에 넣음
        """
        # (편의상 frame_bytes를 객체로 복원해서 ID 추출한다고 가정)
        # 실제로는 bytes 헤더에서 ID만 빠르게 읽는 게 좋음
        frame_obj = pickle.loads(frame_bytes)
        frame_id = frame_obj.frame_id
        
        # 1. [Data Plane] 무거운 데이터 저장 (Key-Value)
        # Expiry(만료 시간) 5초를 줘서 나중에 자동 삭제되게 함 (메모리 관리)
        data_key = f"{topic}:data:{frame_id}"
        self.data_redis.set(data_key, frame_bytes, ex=5)
        
        # 2. [Control Plane] 가벼운 ID 줄 세우기 (Queue)
        self.ctrl_redis.lpush(topic, str(frame_id))
        # 큐 길이 제한 (Trim) - 제어용 Redis에서 수행
        self.ctrl_redis.ltrim(topic, 0, 50)

    def pop(self, topic, timeout=0.1):
        """
        Ctrl Redis에서 ID를 꺼내고, Data Redis에서 실제 데이터를 가져옴
        """
        # 1. [Control Plane] ID 꺼내기 (Blocking Pop)
        item = self.ctrl_redis.brpop(topic, timeout=timeout)
        if not item:
            return None
            
        _, frame_id_bytes = item
        frame_id = frame_id_bytes.decode('utf-8')
        
        # 2. [Data Plane] 실제 데이터 조회
        data_key = f"{topic}:data:{frame_id}"
        raw_data = self.data_redis.get(data_key)
        
        if raw_data:
            # (옵션) 읽었으면 삭제해서 메모리 아끼기? 
            # 여러 Consumer가 읽어야 하면 삭제 금지 (TTL로 자동삭제 추천)
            # self.data_redis.delete(data_key) 
            return raw_data
        else:
            print(f"⚠️ Data missing in Redis #2 for ID: {frame_id}")
            return None

    def trim(self, topic, size):
        self.ctrl_redis.ltrim(topic, 0, size)

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