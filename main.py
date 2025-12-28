from edgeflow import EdgeApp
from edgeflow.nodes.producer import ProducerNode
from edgeflow.nodes.consumer import ConsumerNode
from edgeflow.nodes.gateway import GatewayNode  # [추가됨]
import numpy as np
import cv2
import time

app = EdgeApp("test-app")

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

# 3. Gateway (Class 방식) [추가됨]
@app.node(name="gateway", type="gateway", port=8000)
class MyGateway(GatewayNode):
    def setup(self):
        super().setup() # 필수: FastAPI 라우트 등록 등을 위해 부모 setup 호출
        print("✅ Custom Gateway Setup Complete")

    def on_message(self, frame, meta):
        # 메타데이터 확인용 로그
        if meta.get("detected"):
            print(f"Alert: {meta}")
        return frame

if __name__ == "__main__":
    app.run()