#edgeflow/comms/brokers/base.py
from abc import ABC, abstractmethod

class BrokerInterface(ABC):
    """
    모든 Broker가 구현해야 하는 인터페이스입니다.
    노드들은 이 인터페이스에만 의존하게 됩니다.
    """
    @abstractmethod
    def push(self, data: bytes, key: str = "data"):
        """데이터를 브로커에 푸시합니다."""
        pass

    @abstractmethod
    def pop(self, timeout: int = 0) -> bytes | None:
        """브로커에서 데이터를 팝합니다."""
        pass
    
    @abstractmethod
    def trim(self, size: int):
        """스트림의 크기를 관리합니다."""
        pass
