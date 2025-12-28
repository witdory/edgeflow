import time
from .base import BaseNode
from ..comms import Frame  # 기존 Frame 재사용

class ProducerNode(BaseNode):
    def __init__(self, fps=30, queue_size=1):
        super().__init__()
        self.fps = fps
        self.queue_size = queue_size

    def produce(self):
        """사용자가 구현해야 할 메소드"""
        raise NotImplementedError

    def run(self):
        print(f"🚀 Producer started (FPS: {self.fps})")
        frame_id = 0
        while self.running:
            start = time.time()
            
            # 사용자 로직 실행
            raw_data = self.produce()
            if raw_data is None: break

            # Frame 포장 (기존 로직)
            frame = Frame(frame_id=frame_id, timestamp=time.time(), data=raw_data)
            
            # Redis 전송 (기존 로직)
            self.broker.push(frame.to_bytes())
            self.broker.trim(self.queue_size)
            
            frame_id += 1
            
            # FPS 제어
            elapsed = time.time() - start
            time.sleep(max(0, (1.0/self.fps) - elapsed))