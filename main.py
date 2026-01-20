import time
import numpy as np
import cv2
import os

from edgeflow import EdgeApp
from edgeflow.nodes import ProducerNode, ConsumerNode

# 앱 초기화
app = EdgeApp("test-distributed-system")

# ============================================================
# 1. 가짜 카메라 노드 (Producer)
# 목표 배포지: k3s-worker-1 (device="camera" 라벨이 있는 곳)
# ============================================================
@app.node(name="fake_camera", type="producer", device="camera", fps=60)
class FakeCamera(ProducerNode):
    def configure(self):
        self.frame_count = 0
        # 현재 실행 중인 파드의 호스트네임을 가져옴 (배포 위치 확인용)
        self.hostname = os.getenv("HOSTNAME", "unknown-host")
        print(f"📸 [Camera] Initialized on host: {self.hostname}")

    def produce(self):
        self.frame_count += 1
        
        # 1. 검은색 빈 이미지 생성 (320x240)
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        
        # 2. 현재 호스트네임과 프레임 번호를 이미지에 적음
        msg_src = f"Src: {self.hostname} | Frame: {self.frame_count}"
        cv2.putText(img, msg_src, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.6, (255, 255, 255), 2)
        
        print(f"📤 [Camera] Sending frame {self.frame_count} from {self.hostname}")
        return img


# ============================================================
# 2. 가짜 GPU 처리 노드 (Consumer)
# 목표 배포지: k3s-worker-2,3,4 중 하나 (device="gpu" 라벨이 있는 곳)
# ============================================================
@app.node(name="gpu_processor", type="consumer", device="gpu", replicas=2)
class GpuProcessor(ConsumerNode):
    def configure(self):
        # 현재 실행 중인 파드의 호스트네임을 가져옴
        self.hostname = os.getenv("HOSTNAME", "unknown-host")
        print(f"🧠 [GPU] Initialized on host: {self.hostname}")

    def process(self, frame):
        # 카메라로부터 받은 이미지를 그대로 사용
        processed_img = frame.copy()
        
        # 1. 처리했다는 표시를 초록색 텍스트로 추가
        msg_proc = f"Processed by Node: {self.hostname}"
        cv2.putText(processed_img, msg_proc, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.6, (0, 255, 0), 2)
        
        print(f"📥 [GPU] Received & processed frame on {self.hostname}")
        
        # 실제 데이터 파이프라인에서는 처리 결과를 리턴하지만, 테스트에선 생략
        return None


# ============================================================
# 3. 연결 및 실행
# ============================================================
if __name__ == "__main__":
    # 카메라 -> GPU 프로세서 연결 (Redis Pub/Sub 자동 구성)
    app.link("fake_camera").to("gpu_processor")
    
    print("🚀 Starting EdgeFlow Test App...")
    # 로컬에서 실행하면 멀티스레드로 돌고,
    # 배포 후 K8s 안에서는 프레임워크가 알아서 단일 노드만 실행시킴
    app.run()