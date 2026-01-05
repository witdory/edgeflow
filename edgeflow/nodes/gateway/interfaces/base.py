#edgeflow/nodes/gateway/interfaces/base.py
from abc import ABC, abstractmethod

class BaseInterface(ABC):
    def __init__(self):
        self.broker = None
        self.edge_app = None
        self.gateway = None

    @abstractmethod
    def setup(self):
        """초기화 작업 (예: ROS 노드 생성, DB 연결)"""
        pass

    @abstractmethod
    async def on_frame(self, frame):
        """데이터가 들어왔을 때 수행할 동작 (비동기 필수)"""
        pass

    async def run_loop(self):
        """별도의 루프가 필요한 경우 (예: 웹서버 실행) 구현"""
        pass