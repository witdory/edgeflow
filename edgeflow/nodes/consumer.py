#edgeflow/nodes/consumer.py
"""
ConsumerNode - 데이터 처리 노드 (AI, GPU 등)

Arduino Pattern:
- setup(): 초기화 (모델 로딩 등)
- loop(data): 데이터 처리 및 반환
"""
import os
from .base import EdgeNode
from ..comms import Frame
from ..qos import QoS


class ConsumerNode(EdgeNode):
    """업스트림에서 데이터를 받아 처리하는 노드"""
    node_type = "consumer"
    
    def __init__(self, broker, replicas=1, **kwargs):
        super().__init__(broker=broker, **kwargs)
        self.replicas = replicas

    def loop(self, data):
        """
        [User Hook] 데이터를 처리하여 반환
        - data: 업스트림에서 받은 이미지/데이터
        - return: 처리된 결과 (자동으로 다운스트림 전송)
        - return None: 해당 프레임 스킵
        """
        raise NotImplementedError("ConsumerNode requires loop(data) implementation")

    def _run_loop(self):
        """[Internal] Stream에서 QoS에 따라 데이터를 받아 loop() 반복 호출"""
        # input_topics can be dict with 'topic' and 'qos' or just string
        if not self.input_topics:
            print(f"⚠️ No input topics for {self.name}")
            return
        
        first_input = self.input_topics[0]
        if isinstance(first_input, dict):
            target_topic = first_input['topic']
            qos = first_input.get('qos', QoS.REALTIME)
        else:
            target_topic = first_input
            qos = QoS.REALTIME
        
        group_name = getattr(self, 'name', 'default')
        consumer_id = self.hostname
        
        print(f"🧠 Consumer started (QoS: {qos.name}), Input: {target_topic}, Group: {group_name}")

        while self.running:
            # QoS에 따라 다른 읽기 전략
            if qos == QoS.REALTIME:
                # REALTIME: 최신만 읽기
                packet = self.broker.pop_latest(target_topic, timeout=1)
            else:
                # DURABLE/BALANCED: 순차 읽기 (Consumer Group)
                packet = self.broker.pop(target_topic, timeout=1, group=group_name, consumer=consumer_id)
            
            if not packet:
                continue

            frame = Frame.from_bytes(packet)
            if not frame:
                continue

            try:
                result = self.loop(frame.data)
                if result is None:
                    continue

                out_img, out_meta = result if isinstance(result, tuple) else (result, {})
                resp = Frame(frame.frame_id, frame.timestamp, out_meta, out_img)
                self.send_result(resp)

            except Exception as e:
                print(f"⚠️ Consumer Error: {e}")