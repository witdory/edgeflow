#edgeflow/nodes/producer.py
"""
ProducerNode - 데이터 생성 노드 (카메라, 센서 등)

Arduino Pattern:
- setup(): 초기화
- loop(): 데이터 생성 및 반환 (return으로 Frame 전송)
"""
import time
from .base import EdgeNode
from ..comms import Frame


class ProducerNode(EdgeNode):
    """데이터를 생성하여 다운스트림으로 전송하는 노드"""
    node_type = "producer"
    
    def __init__(self, broker=None, fps=30, topic="default", queue_size=1, **kwargs):
        super().__init__(broker, **kwargs)
        self.fps = fps
        self.queue_size = queue_size
        self._frame_id = 0

    def loop(self):
        """
        [User Hook] 데이터를 생성하여 반환
        - return: 이미지/데이터 (자동으로 Frame으로 포장되어 전송됨)
        - return None: 루프 종료
        """
        raise NotImplementedError("ProducerNode requires loop() implementation")

    def _run_loop(self):
        """[Internal] FPS에 맞춰 loop() 반복 호출"""
        print(f"🚀 Producer started (FPS: {self.fps})")
        
        while self.running:
            start = time.time()
            
            # 사용자 loop() 실행
            raw_data = self.loop()
            if raw_data is None:
                break

            # Frame 포장
            if isinstance(raw_data, Frame):
                frame = raw_data
                if frame.frame_id == 0:
                    frame.frame_id = self._frame_id
            else:
                frame = Frame(
                    frame_id=self._frame_id, 
                    timestamp=time.time(), 
                    data=raw_data
                )
            
            self.send_result(frame)
            self._frame_id += 1
            
            # FPS 제어
            elapsed = time.time() - start
            time.sleep(max(0, (1.0 / self.fps) - elapsed))