from edgeflow import EdgeApp
from edgeflow.nodes.producer import ProducerNode
from edgeflow.nodes.consumer import ConsumerNode
from edgeflow.nodes.gateway import GatewayNode, WebInterface
from edgeflow.nodes.fusion import FusionNode
from edgeflow.comms import RedisBroker
import numpy as np
import cv2
import time

app = EdgeApp("test-app", broker=RedisBroker())

# 1. Camera Producer
@app.node(name="camera", type="producer", fps=10, topic="camera_raw")
class MyCamera(ProducerNode):
    def produce(self):
        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        return frame

# 2. AI Consumer
@app.node(name="ai", type="consumer",input_topic="camera_raw", output_topic="ai_result", replicas=1)
class MyAI(ConsumerNode):
    def process(self, frame):
        cv2.putText(frame, "Topic 1", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        return frame, {"detected": True, "ts": time.time()}

# 1. Camera Producer
@app.node(name="camera2", type="producer", fps=10, topic="camera_raw2")
class MyCamera2(ProducerNode):
    def produce(self):
        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        return frame

# 2. AI Consumer
@app.node(name="ai2", type="consumer",input_topic="camera_raw2", output_topic="ai_result2", replicas=1)
class MyAI2(ConsumerNode):
    def process(self, frame):
        cv2.putText(frame, "Topic 2", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        return frame, {"detected": True, "ts": time.time()}

@app.node(name="gateway", type="gateway")
class MyHub(GatewayNode):
    def configure(self):
        # 1. 웹 인터페이스 생성
        web = WebInterface(port=8000, buffer_delay=0.0)
        
        @web.route("/api/status/{topic_name}")
        async def check_ai_status(topic_name: str):
            meta_data = web.latest_meta.get(topic_name, {})
            is_detected = meta_data.get("detected", False)
            return {
                "meta": meta_data,
                "alert": is_detected
            }
        self.add_interface(web)
        print("✅ Hub & Spoke Gateway Ready!")

if __name__ == "__main__":
    app.run()