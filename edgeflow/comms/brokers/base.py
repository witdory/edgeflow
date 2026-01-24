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
    def trim(self, topic: str, size: int):
        """스트림의 크기를 관리합니다."""
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
