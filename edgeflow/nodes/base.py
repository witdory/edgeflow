#edgeflow/nodes/base.py
from abc import ABC, abstractmethod
import os
from ..comms import RedisBroker

class BaseNode(ABC):
    def __init__(self, broker=None, **kwargs):
        self.running = True
        self.__dict__.update(kwargs) # 메타데이터(node_port 등) 저장
        self.hostname = os.getenv("HOSTNAME", "localhost") # [신규] 노드 호스트명 식별자
        host = os.getenv("REDIS_HOST", "localhost")
        self.broker = broker  # 기존 comms.py의 RedisBroker 그대로 사용

        # [변경] 입출력 프로토콜 및 핸들러 관리
        self.input_protocol = "redis"  # 기본값
        self.input_topics = []         # 수신할 토픽들
        self.output_handlers = []      # 데이터를 보낼 배달부 목록

        if not self.broker:
            self.broker = RedisBroker(host)

    def send_result(self, frame):
        """[핵심] 연결된 모든 핸들러에게 데이터 전송"""
        if not frame: return
        for handler in self.output_handlers:
            handler.send(frame)


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
        """초기화 로직 (User Hook 포함)"""
        self.configure()

    def configure(self):
        """[User Hook] 사용자가 오버라이드하여 초기화 로직 구현"""
        pass

    @abstractmethod
    def run(self):
        pass

    def teardown(self):
        pass