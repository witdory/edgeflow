import time
import numpy as np
import cv2
import os

from edgeflow import EdgeApp
from edgeflow.nodes import ProducerNode, ConsumerNode, GatewayNode
from edgeflow.nodes.gateway.interfaces.web import WebInterface
from edgeflow.comms import RedisBroker
from edgeflow.config import settings

# 앱 초기화
app = EdgeApp("test-distributed-system", broker=RedisBroker())

# ============================================================
# 1. 가짜 카메라 노드 (Producer) - 움직이는 공 애니메이션
# 목표 배포지: k3s-worker-1 (device="camera" 라벨이 있는 곳)
# ============================================================
@app.node(name="fake_camera", type="producer", device="camera", fps=30, queue_size=1)
class FakeCamera(ProducerNode):
    def configure(self):
        self.hostname = os.getenv("HOSTNAME", "unknown-host")
        print(f"📸 [Camera] Initialized on host: {self.hostname}")

    def produce(self):
        # 검은색 배경 이미지 생성 (480x640)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)  # 어두운 회색 배경
        
        # 움직이는 공 그리기 (시간 기반 애니메이션)
        t = time.time()
        cx = int(320 + 200 * np.sin(t * 2))
        cy = int(240 + 100 * np.cos(t * 2))
        cv2.circle(img, (cx, cy), 30, (0, 255, 255), -1)  # 노란 공
        
        # 호스트네임 + 타임스탬프 표시
        cv2.putText(img, f"Src: {self.hostname}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(img, f"Time: {t:.2f}", (10, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return img


# ============================================================
# 2. 가짜 GPU 처리 노드 (Consumer)
# 목표 배포지: k3s-worker-2,3,4 중 하나 (device="gpu" 라벨이 있는 곳)
# ============================================================
@app.node(name="gpu_processor", type="consumer", device="gpu", replicas=2)
class GpuProcessor(ConsumerNode):
    def configure(self):
        self.hostname = os.getenv("HOSTNAME", "unknown-host")
        print(f"🧠 [GPU] Initialized on host: {self.hostname}")

    def process(self, frame):
        processed_img = frame.copy()
        
        # AI 처리 표시 (빨간 박스 + 텍스트)
        cv2.rectangle(processed_img, (150, 100), (490, 380), (0, 0, 255), 3)
        cv2.putText(processed_img, "AI DETECTED", (150, 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(processed_img, f"Processed by: {self.hostname}", (10, 450), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        time.sleep(0.2)
        return processed_img


# ============================================================
# 3. 웹 게이트웨이 (실시간 영상 스트리밍)
# ============================================================
@app.node(name="gateway", type="gateway", node_port=30080)
class VideoGateway(GatewayNode):
    def configure(self):
        web = WebInterface(port=settings.GATEWAY_HTTP_PORT, buffer_delay=0.0)
        self.add_interface(web)


# ============================================================
# 4. 연결 및 실행
# ============================================================
if __name__ == "__main__":
    print("🚧 Building Pipeline...")
    
    # 카메라 -> GPU -> Gateway 연결
    app.link("fake_camera").to("gpu_processor")
    app.link("gpu_processor").to("gateway")
    
    # Raw 영상도 Gateway로 직접 전송 (처리 전 원본)
    app.link("fake_camera").to("gateway")
    
    print(f"\n✅ System Ready! Open your browser:")
    print(f" - Health Check: http://<NODE-IP>:30080/health")
    print(f" - Raw Camera : http://<NODE-IP>:30080/video/fake_camera")
    print(f" - AI Result  : http://<NODE-IP>:30080/video/gpu_processor")
    print("\n🚀 Starting EdgeFlow...")
    
    app.run()