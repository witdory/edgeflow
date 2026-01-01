#edgeflow/nodes/consumer.py
import os
from .base import BaseNode
from ..comms import Frame, GatewaySender # 기존 TCP Sender 재사용

class ConsumerNode(BaseNode):
    def __init__(self, broker, replicas=1, input_topic="default", output_topic = "default"):
        super().__init__(broker=broker)
        self.replicas = replicas
        self.sender = None
        self.input_topic = input_topic
        self.output_topic = output_topic


    def setup(self):
        # 기존 TCP Sender 연결 로직
        gw_host = os.getenv("GATEWAY_HOST", "localhost")
        self.sender = GatewaySender(gw_host)

    def process(self, data):
        """사용자가 구현해야 할 메소드"""
        raise NotImplementedError

    def run(self):
        print(f"🧠 Consumer started (Replicas: {self.replicas}), Input Topic: {self.input_topic}")
        while self.running:
            # Redis에서 가져오기
            packet = self.broker.pop(self.input_topic, timeout=1)
            if not packet: continue

            # 역직렬화
            frame = Frame.from_bytes(packet)
            if not frame: continue

            try:
                # 사용자 로직 실행
                result = self.process(frame.data)
                if result is None: continue

                # 결과 처리 (Tuple or Data)
                out_img, out_meta = result if isinstance(result, tuple) else (result, {})
                if "topic" not in out_meta:
                    out_meta["topic"] = self.output_topic


                # Gateway 전송 (TCP)
                resp = Frame(frame.frame_id, frame.timestamp, out_meta, out_img)
                self.sender.send(resp.to_bytes())

            except Exception as e:
                print(f"⚠️ Consumer Error: {e}")