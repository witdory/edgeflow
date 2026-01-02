import time
import numpy as np
import cv2
import random

# 프레임워크 모듈 임포트
from edgeflow import EdgeApp
from edgeflow.nodes import ProducerNode, ConsumerNode, FusionNode, GatewayNode
from edgeflow.nodes.gateway.interfaces.web import WebInterface
from edgeflow.comms import RedisBroker
from edgeflow.config import settings

# 앱 초기화
app = EdgeApp("test-system", broker=RedisBroker())

# ====================================================
# 1. Producer (데이터 생성)
# ====================================================

@app.node(name="cam_main", type="producer", fps=30, queue_size=1)
class Camera(ProducerNode):
    def produce(self):
        # [테스트용] 움직이는 공이 있는 더미 영상 생성
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 배경색 (약간의 노이즈)
        img[:] = (30, 30, 30) 
        
        # 움직이는 공 그리기 (시간 기반)
        t = time.time()
        cx = int(320 + 200 * np.sin(t * 2))
        cy = int(240 + 100 * np.cos(t * 2))
        cv2.circle(img, (cx, cy), 30, (0, 255, 255), -1)
        
        # 타임스탬프 표시
        cv2.putText(img, f"RAW: {t:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        return img


@app.node(name="lidar_sensor", type="producer", fps=10, queue_size=1)
class Lidar(ProducerNode):
    def produce(self):
        # 1. 360도 회전하는 각도 계산 (시간 기반)
        t = time.time()
        angle = (t * 180) % 360  # 1초에 반 바퀴 회전
        
        # 2. 레이더 스캔 라인 좌표 계산
        cx, cy = 320, 240
        length = 200
        dx = int(length * np.cos(np.deg2rad(angle)))
        dy = int(length * np.sin(np.deg2rad(angle)))
        
        # 3. 데이터 패킷 생성 (Visual용 이미지가 아니라, Fusion 계산용 Raw 데이터라고 가정)
        # 퓨전 노드에서 그림을 그리기 위해 "현재 각도" 정보를 보냄
        return {"angle": angle, "raw_points": np.random.rand(50, 2)}

# ====================================================
# 2. Consumer (AI 처리)
# ====================================================

@app.node(name="yolo_ai", type="consumer", replicas=1)
class YoloDetector(ConsumerNode):
    def process(self, frame_data):
        # [테스트용] 영상 처리를 흉내냄 (박스 그리기)
        img = frame_data.copy()
        
        # 중앙에 빨간 박스 (AI가 감지했다고 가정)
        cv2.rectangle(img, (200, 150), (440, 330), (0, 0, 255), 3)
        cv2.putText(img, "AI DETECTED", (200, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # 처리 지연 시뮬레이션 (약 30ms)
        time.sleep(0.03)
        
        return img, {"class": "person", "conf": 0.95}

# ====================================================
# 3. Fusion (센서 융합)
# ====================================================

@app.node(name="sensor_fusion", type="fusion")
class DepthFusion(FusionNode):
    def configure(self):
        self.slop = 0.1 # 100ms (꽤 넉넉하게 줌)

    def process(self, frames):
        # frames[0]: Camera, frames[1]: Lidar
        cam_frame = frames[0].data.copy() # 배경 이미지
        lidar_data = frames[1].data       # 라이다 데이터 (딕셔너리)
        
        # ---------------------------------------------------------
        # 1. 타임스탬프 분석
        # ---------------------------------------------------------
        t_cam = frames[0].timestamp
        t_lidar = frames[1].timestamp
        dt = abs(t_cam - t_lidar) * 1000 # 밀리초(ms) 단위 변환

        # ---------------------------------------------------------
        # 2. 라이다 데이터 시각화 (회전하는 선)
        # ---------------------------------------------------------
        # 라이다는 10fps라 뚝뚝 끊기며 돌아가고, 카메라는 30fps라 부드러움
        # 퓨전이 잘 되면, 라이다 선은 3프레임동안 멈춰있어야 함!
        if lidar_data:
            angle = lidar_data["angle"]
            cx, cy = 320, 240
            length = 200
            dx = int(length * np.cos(np.deg2rad(angle)))
            dy = int(length * np.sin(np.deg2rad(angle)))
            
            # 레이더 선 그리기 (빨간색)
            cv2.line(cam_frame, (cx, cy), (cx+dx, cy+dy), (0, 0, 255), 3)
            cv2.circle(cam_frame, (cx, cy), 5, (0, 0, 255), -1)

        # ---------------------------------------------------------
        # 3. [HUD] 동기화 상태 대시보드 그리기
        # ---------------------------------------------------------
        # (1) 시간차(Lag) 게이지 바
        bar_len = int(dt * 5) # 1ms당 5픽셀
        color = (0, 255, 0) if dt < 50 else (0, 165, 255) # 50ms 넘으면 주황색
        
        cv2.rectangle(cam_frame, (50, 400), (50 + 300, 430), (50, 50, 50), -1) # 배경바
        cv2.rectangle(cam_frame, (50, 400), (50 + bar_len, 430), color, -1)    # 값
        
        # (2) 텍스트 정보
        cv2.putText(cam_frame, f"SYNC DIFF: {dt:.1f} ms", (50, 390), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        cv2.putText(cam_frame, f"CAM Time  : {t_cam:.4f}", (50, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        # 라이다 시간이 멈춰있는지 확인하세요!
        cv2.putText(cam_frame, f"LIDAR Time: {t_lidar:.4f}", (50, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

        return cam_frame

# ====================================================
# 4. Gateway (웹 표출)
# ====================================================

@app.node(name="gateway", type="gateway")
class CentralHub(GatewayNode):
    def configure(self):
        # 웹 인터페이스 설정 (브라우저 접속 포트)
        # buffer_delay를 0으로 두어 최대한 실시간성 확보
        web = WebInterface(port=settings.GATEWAY_HTTP_PORT, buffer_delay=0.0)
        self.add_interface(web)

# ====================================================
# 5. 배선 및 실행 (Wiring)
# ====================================================

if __name__ == "__main__":
    print("🚧 Building Pipeline...")

    # 1. [Raw Stream] 카메라 -> 게이트웨이 (TCP 직결)
    # 목적: 원본 영상 확인 (Latency 최소)
    app.link("cam_main").to("gateway")

    # 2. [AI Stream] 카메라 -> AI -> 게이트웨이 (Redis -> TCP)
    # 목적: AI 처리 결과 확인
    app.link("cam_main").to("yolo_ai")
    app.link("yolo_ai").to("gateway")

    # 3. [Fusion Stream] 카메라 + 라이다 -> 퓨전 -> 게이트웨이
    # 목적: 이종 센서 동기화 확인
    app.link("cam_main").to("sensor_fusion")
    app.link("lidar_sensor").to("sensor_fusion")
    app.link("sensor_fusion").to("gateway")

    print("\n✅ System Ready! Open your browser:")
    print(f" - Raw Camera : http://localhost:{settings.GATEWAY_HTTP_PORT}/video/cam_main")
    print(f" - AI Result  : http://localhost:{settings.GATEWAY_HTTP_PORT}/video/yolo_ai")
    print(f" - Fusion     : http://localhost:{settings.GATEWAY_HTTP_PORT}/video/sensor_fusion")
    print("\nStarting EdgeFlow... (Press Ctrl+C to stop)")
    
    app.run()