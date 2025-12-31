from edgeflow import EdgeApp
from edgeflow.nodes.producer import ProducerNode
from edgeflow.nodes.consumer import ConsumerNode
from edgeflow.nodes.gateway import GatewayNode, WebInterface
from edgeflow.nodes.sync import SyncNode
from edgeflow.comms import RedisBroker
import numpy as np
import cv2
import time

app = EdgeApp("test-app", broker=RedisBroker())

# 1. Camera Producer
@app.node(name="camera", type="producer", fps=10)
class MyCamera(ProducerNode):
    def produce(self):
        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        return frame

# 2. AI Consumer
@app.node(name="ai", type="consumer", replicas=1)
class MyAI(ConsumerNode):
    def process(self, frame):
        cv2.putText(frame, "Class Mode!", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        return frame, {"detected": True, "ts": time.time()}

@app.node(name="gateway", type="gateway")
class MyHub(GatewayNode):
    def configure(self):
        # 1. 웹 인터페이스 생성
        web = WebInterface(port=8000)
        
        @web.route("/api/detected")
        async def check_detected():
            # web.latest_meta 에 접근 가능 (단, 동시성 주의 필요하지만 읽기만 하면 OK)
            is_detected = web.latest_meta.get("detected", False)
            return {"alert": is_detected}
            
        # 2. 장착
        self.add_interface(web)
        print("✅ Hub & Spoke Gateway Ready!")

if __name__ == "__main__":
    app.run()