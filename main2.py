from edgeflow import EdgeApp
from edgeflow.nodes import ProducerNode, ConsumerNode, FusionNode, BridgeNode
from edgeflow.nodes.gateway import GatewayNode, WebInterface
from edgeflow.comms import RedisBroker
import numpy as np
import cv2

# [Dependency Injection] RedisBroker를 주입하여 앱 초기화
app = EdgeApp("robot-core", broker=RedisBroker(host='localhost', port=6379))

# 1. [Producer] 카메라 데이터 (30 FPS)
@app.node(name="cam", type="producer", fps=30, topic="cam_data")
class Camera(ProducerNode):
    def produce(self):
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        return frame

# 2. [Producer] 라이다 데이터 (10 FPS)
@app.node(name="lidar", type="producer", fps=5, topic="lidar_data")
class Lidar(ProducerNode):
    def produce(self):
        # 검은 배경 생성
        lidar_view = np.zeros((400, 400, 3), dtype=np.uint8)
        
        # 중앙에 초록색 점 하나 찍기 (로봇 위치)
        cv2.circle(lidar_view, (200, 200), 5, (0, 255, 0), -1)
        
        # 랜덤한 장애물 몇 개 찍기 (Lidar 데이터 흉내)
        for _ in range(10):
            x = np.random.randint(0, 400)
            y = np.random.randint(0, 400)
            cv2.circle(lidar_view, (x, y), 2, (0, 0, 255), -1)

        return lidar_view

# 3. [Fusion] 이종 센서 동기화
@app.node(name="fusion", type="fusion")
class SensorFusion(FusionNode):
    def configure(self):
        # 동기화할 토픽 목록과 허용 오차(slop) 설정
        self.input_topics = ["cam_data", "lidar_data"]
        self.output_topic = "fused_view"
        self.slop = 0.5

    def process(self, frames):
        cam_frame, lidar_frame = frames
        
        # 1. 카메라 배경 복사 (480x640)
        background = cam_frame.data.copy()
        
        # 2. 라이다 이미지 (400x400)
        lidar_img = lidar_frame.data
        lidar_resized = cv2.resize(lidar_img, (400, 400))

        
        background[40:440, 120:520] = lidar_resized

        # 4. 텍스트 추가
        cv2.putText(background, "FUSION OK", (50, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        return background

#4. bridge 정의
@app.node(name="bridge", type="bridge", input_topic = "fused_view")
class FusionBridge(BridgeNode):
    def configure(self):
        pass


# 5. [Gateway] 웹 시각화 (플러그인 장착)
@app.node(name="gateway", type="gateway")
class MyHub(GatewayNode):
    def configure(self):
        web = WebInterface(port=8000)
        
        # 커스텀 상태 API 추가
        @web.route("/api/status")
        async def status():
            return {"fusion": "active", "clients": len(self.active_clients)}

        self.add_interface(web)

if __name__ == "__main__":
    app.run()