# examples/my-robot/main.py
"""
Edgeflow v0.2.0 Example - Folder-based Node Definition
"""

from edgeflow import System
from edgeflow.comms import RedisBroker

# System 초기화 (broker 의존성 주입)
sys = System("my-robot", broker=RedisBroker())

# ============================================================
# 노드 등록 (폴더 경로로 참조 - lazy loading)
# ============================================================
cam = sys.node("nodes/camera", device="camera", fps=30, queue_size=1) #NodeSpec만 생성
gpu = sys.node("nodes/yolo", device="gpu", replicas=2)
gw  = sys.node("nodes/gateway", node_port=30080)

# ============================================================
# 연결 (Link Wiring)
# ============================================================
sys.link(cam).to(gpu).to(gw)       # GPU 결과 -> Gateway
sys.link(cam).to(gw)       # Raw 영상도 Gateway로 직접 전송

# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    print("🚧 Building Pipeline...")
    print(f"\n✅ System Ready!")
    print(f" - Health Check: http://<NODE-IP>:30080/health")
    print(f" - Raw Camera : http://<NODE-IP>:30080/video/camera")
    print(f" - AI Result  : http://<NODE-IP>:30080/video/yolo")
    print("\n🚀 Starting EdgeFlow...")
    
    sys.run()
