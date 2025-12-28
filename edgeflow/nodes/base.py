from abc import ABC, abstractmethod
import os
from ..comms import RedisBroker

class BaseNode(ABC):
    def __init__(self):
        self.running = True
        host = os.getenv("REDIS_HOST", "localhost")
        self.broker = RedisBroker(host)  # 기존 comms.py의 RedisBroker 그대로 사용

    def execute(self):
        """노드 실행의 전체 흐름 제어 (Template Method)"""
        self.setup()
        try:
            self.run()
        except KeyboardInterrupt:
            print(f"🛑 {self.__class__.__name__} Stopped.")
        finally:
            self.teardown()

    def setup(self):
        pass

    @abstractmethod
    def run(self):
        pass

    def teardown(self):
        pass