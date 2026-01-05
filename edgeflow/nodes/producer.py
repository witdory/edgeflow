#edgeflow/nodes/producer.py
import time
from .base import BaseNode
from ..comms import Frame  # 기존 Frame 재사용

class ProducerNode(BaseNode):
    def __init__(self, broker, app, fps=30, **kwargs):
        super().__init__(broker=broker, app=app, **kwargs)
        self.fps = fps
        self.queue_size = kwargs.get("queue_size", 1)

    def produce(self):
        """사용자가 구현해야 할 메소드"""
        raise NotImplementedError

    def run(self):
        print(f"🚀 Producer started (FPS: {self.fps})")
        frame_id = 0
        last_metric_publish_time = time.time()
        while self.running:
            start = time.time()
            
            # 사용자 로직 실행
            raw_data = self.produce()
            if raw_data is None: break

            # --- Metrics Start ---
            self._start_frame_timer() # For FPS
            # --- Metrics End ---

            # Frame 포장 (기존 로직)
            if isinstance(raw_data, Frame):
                frame = raw_data
                if frame.frame_id == 0:
                    frame.frame_id = frame_id
            else:
                frame = Frame(frame_id=frame_id, timestamp=time.time(), data=raw_data)
            
            self.send_result(frame)
            
            frame_id += 1
            
            # FPS 제어 (테스트용 fps 제한 기능)
            elapsed = time.time() - start
            time.sleep(max(0, (1.0/self.fps) - elapsed))

            # --- Publish Metrics periodically ---
            current_time = time.time()
            if current_time - last_metric_publish_time > self.metrics_interval_sec:
                self._publish_metrics()
                last_metric_publish_time = current_time