#edgeflow/nodes/base.py
import time
import json
from abc import ABC, abstractmethod
import os
from collections import defaultdict
from ..comms import RedisBroker

class BaseNode(ABC):
    def __init__(self, broker=None, app=None, **kwargs):
        self.app = app
        self.running = True
        host = os.getenv("REDIS_HOST", "localhost")
        self.broker = broker  # 기존 comms.py의 RedisBroker 그대로 사용
        self.metrics_interval_sec = kwargs.get("metrics_interval_sec", 1)

        # [변경] 입출력 프로토콜 및 핸들러 관리
        self.input_protocol = "redis"  # 기본값
        self.input_topics = []         # 수신할 토픽들
        self.output_handlers = []      # 데이터를 보낼 배달부 목록

        if not self.broker:
            self.broker = RedisBroker(host)

        self.metrics_channel = f"{self.app.name}:metrics" if self.app else "edgeflow_metrics"

        # Metrics tracking
        self._frame_count = 0
        self._fps_start_time = time.time()
        self._latency_measurements = defaultdict(list)
        self._max_latency_measurements = 100 # Keep a rolling average of last 100 measurements

    def _publish_metrics(self):
        """Publishes the current FPS and latency to the metrics channel."""
        if not self.app:
            return # Cannot publish without an app context

        fps = self.get_fps()
        avg_latencies = self.get_avg_latencies()

        metrics_data = {
            "node_name": self.name,
            "fps": fps,
            "avg_latency_ms": avg_latencies, # Changed to a dictionary
            "timestamp": time.time(),
        }
        
        self.broker.publish(self.metrics_channel, json.dumps(metrics_data))

        # Reset metrics after publishing to report fresh values next time
        self.reset_metrics()

    def _start_frame_timer(self):
        """Records the start time for a frame to calculate FPS."""
        self._frame_count += 1
        # No return value, just updates internal state

    def _record_latency(self, name: str, duration_sec: float):
        """Records a named latency measurement."""
        if duration_sec is not None:
            self._latency_measurements[name].append(duration_sec)
            # Trim the list to avoid growing indefinitely
            if len(self._latency_measurements[name]) > self._max_latency_measurements:
                self._latency_measurements[name].pop(0)

    def get_fps(self):
        """Calculates and returns the current FPS."""
        elapsed_time = time.time() - self._fps_start_time
        if elapsed_time > 0:
            return self._frame_count / elapsed_time
        return 0.0

    def get_avg_latencies(self) -> dict:
        """Calculates and returns a dictionary of average latencies in ms."""
        avg_latencies = {}
        for name, measurements in self._latency_measurements.items():
            if not measurements:
                avg_latencies[name] = 0.0
            else:
                avg = sum(measurements) / len(measurements)
                avg_latencies[name] = avg * 1000 # Convert to ms
        return avg_latencies

    def reset_metrics(self):
        """Resets all metrics counters."""
        self._frame_count = 0
        self._fps_start_time = time.time()
        self._latency_measurements.clear()

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
        pass

    @abstractmethod
    def run(self):
        pass

    def teardown(self):
        pass