#edgeflow/nodes/base.py
"""
Arduino-style Node Base Class
- setup(): 한 번만 실행되는 초기화 로직
- loop(): 반복 실행되는 메인 로직
"""
from abc import ABC, abstractmethod
import os
from ..comms import RedisBroker


class EdgeNode(ABC):
    """
    Base class for all edge nodes.
    
    Arduino Pattern:
    - setup(): Called once at startup (user override)
    - loop(): Called repeatedly (user override)
    """
    node_type = "generic"
    
    def __init__(self, broker=None, **kwargs):
        self.running = True
        self.__dict__.update(kwargs)
        if not hasattr(self, 'name'):
            self.name = self.__class__.__name__
        self.hostname = os.getenv("HOSTNAME", "localhost")
        host = os.getenv("REDIS_HOST", "localhost")
        self.broker = broker

        # I/O protocol and handlers
        self.input_protocol = "redis"
        self.input_topics = []
        self.output_handlers = []

        if not self.broker:
            self.broker = RedisBroker(host)

    def send_result(self, frame):
        """연결된 모든 핸들러에게 데이터 전송"""
        if not frame:
            return
        for handler in self.output_handlers:
            handler.send(frame)

    def execute(self):
        """노드 실행 전체 흐름 제어 (Template Method)"""
        self._setup()
        try:
            self._run_loop()
        except KeyboardInterrupt:
            print(f"🛑 {self.__class__.__name__} Stopped.")
        finally:
            self.teardown()

    def _setup(self):
        """[Internal] 프레임워크 초기화 + 사용자 setup() 호출"""
        self.setup()

    def setup(self):
        """[User Hook] 한 번만 실행되는 초기화 로직 (Arduino setup)"""
        pass

    @abstractmethod
    def _run_loop(self):
        """[Internal] 서브클래스에서 loop() 호출 방식 정의"""
        pass

    def loop(self):
        """[User Hook] 반복 실행되는 메인 로직 (Arduino loop)"""
        raise NotImplementedError("Subclass must implement loop()")

    def teardown(self):
        """[User Hook] 종료 시 정리 로직"""
        pass