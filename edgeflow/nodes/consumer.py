#edgeflow/nodes/consumer.py
import os
import time
from .base import BaseNode
from ..comms import Frame

class ConsumerNode(BaseNode):
    def __init__(self, broker, app, replicas=1, **kwargs):
        super().__init__(broker=broker, app=app, **kwargs)
        self.replicas = replicas
        

    def setup(self):
        pass

    def process(self, data):
        """사용자가 구현해야 할 메소드"""
        raise NotImplementedError

    def run(self):
        target_topic = self.input_topics[0] if self.input_topics else "default"
        print(f"🧠 Consumer started (Replicas: {self.replicas}), Input Topic: {self.input_topics}")

        last_metric_publish_time = time.time()

        while self.running:
            # Redis에서 가져오기 (Consumer의 Input은 무조건 Redis 고정)
            packet = self.broker.pop(target_topic, timeout=1)
            if not packet: continue

            # 역직렬화
            frame = Frame.from_bytes(packet)
            if not frame: continue

            # --- Metrics Start ---
            self._start_frame_timer() # For FPS
            # --- Metrics End was here, moved to after processing ---

            try:
                # 사용자 로직 실행 (with processing time measurement)
                process_start_time = time.time()
                result = self.process(frame.data)
                process_end_time = time.time()

                # --- New Metrics Calculation ---
                self._record_latency('processing', process_end_time - process_start_time)
                self._record_latency('end_to_end', process_end_time - frame.timestamp)

                if result is None: continue

                # 결과 처리 (Tuple or Data)
                out_img, out_meta = result if isinstance(result, tuple) else (result, {})
                


                # Gateway 전송 (TCP)
                resp = Frame(frame.frame_id, frame.timestamp, out_meta, out_img)
                self.send_result(resp)

            except Exception as e:
                print(f"⚠️ Consumer Error: {e}")
            
            # --- Publish Metrics periodically ---
            current_time = time.time()
            if current_time - last_metric_publish_time > self.metrics_interval_sec:
                self._publish_metrics()
                last_metric_publish_time = current_time