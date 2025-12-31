#edgeflow/comms/brokers/base.py
from abc import ABC, abstractmethod

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
