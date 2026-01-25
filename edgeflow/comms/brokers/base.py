#edgeflow/comms/brokers/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class BrokerInterface(ABC):
    """
    모든 Broker가 구현해야 하는 인터페이스입니다.
    노드들은 이 인터페이스에만 의존하게 됩니다.
    """
    @abstractmethod
    def push(self, topic: str, data: bytes):
        """데이터를 브로커에 푸시합니다."""
        pass

    @abstractmethod
    def pop(self, topic: str, timeout: int = 0) -> bytes | None:
        """브로커에서 데이터를 팝합니다."""
        pass
        
    @abstractmethod
    def pop_latest(self, topic: str, timeout: int = 0) -> bytes | None:
        """
        [QoS: REALTIME] 가장 최신의 데이터만 가져옵니다.
        - 오래된 데이터는 스킵합니다.
        - 중복된 데이터(이미 읽은 frame_id)는 반환하지 않아야 합니다.
        """
        pass
    
    @abstractmethod
    def trim(self, topic: str, size: int):
        """스트림의 크기를 관리합니다."""
        pass

    @abstractmethod
    def queue_size(self, topic: str) -> int:
        """현재 토픽 대기열의 크기를 반환합니다."""
        pass

    @abstractmethod
    def get_queue_stats(self) -> Dict[str, Dict[str, int]]:
        """모든 대기열의 상태(current, max)를 반환합니다."""
        pass
    
    def reset(self):
        """
        브로커의 상태를 초기화합니다 (선택적 구현).
        - 예: Redis FLUSHALL, 파일 삭제 등
        - 시스템 시작 시 메인 프로세스에서 단 한 번 호출됩니다.
        """
        pass
    
    # ========== Serialization Protocol (Multiprocessing Support) ==========
    
    @abstractmethod
    def to_config(self) -> Dict[str, Any]:
        """
        이 브로커를 다시 생성하기 위한 설정 딕셔너리를 반환합니다.
        멀티프로세싱 환경에서 자식 프로세스로 전달됩니다.
        """
        pass
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any]) -> 'BrokerInterface':
        """
        설정 딕셔너리로부터 브로커 인스턴스를 생성합니다.
        자식 프로세스에서 호출됩니다.
        """
        pass
