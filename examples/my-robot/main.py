# examples/my-robot/main.py
"""
Edgeflow v0.2.0 Example - QoS-based Stream Architecture
"""

from edgeflow import System, QoS, run
from edgeflow.comms import DualRedisBroker

# System 초기화 (broker 의존성 주입)
sys = System("my-robot", broker=DualRedisBroker())

# ============================================================
# 노드 등록 (폴더 경로로 참조 - lazy loading)
# ============================================================
cam = sys.node("nodes/camera", device="camera", fps=30)
gpu = sys.node("nodes/yolo", device="gpu", replicas=2)
gw  = sys.node("nodes/gateway", node_port=30080)

# ============================================================
# 연결 (Link Wiring with QoS)
# ============================================================
sys.link(cam).to(gpu, qos=QoS.REALTIME).to(gw)  # GPU: 최신만 (실시간)
sys.link(cam).to(gw)                             # Raw 영상 -> Gateway (TCP)

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
    
    run(sys)
