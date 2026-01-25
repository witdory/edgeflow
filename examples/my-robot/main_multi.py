# examples/my-robot/main_multi.py
"""
Multi-System Example - Realtime + Logging with QoS
"""

from edgeflow import System, QoS, run
from edgeflow.comms import DualRedisBroker

# ============================================================
# System 1: Realtime Pipeline (Redis)
# ============================================================
sys = System("realtime", broker=DualRedisBroker())

cam = sys.node("nodes/camera", device="camera", fps=30)
gpu = sys.node("nodes/yolo", device="gpu", replicas=2)
gw  = sys.node("nodes/gateway", node_port=30080)
logger = sys.node("nodes/logger")

sys.link(cam).to(gpu, qos=QoS.REALTIME).to(gw)  # GPU: 최신만 (실시간)
sys.link(cam).to(gw)                             # Raw -> Gateway (TCP)
sys.link(cam).to(logger, qos=QoS.DURABLE)         # Raw -> Logger (내구성)

# ============================================================
# Run System
# ============================================================
if __name__ == "__main__":
    print("🚧 Building Multi-System Pipeline...")
    print(f"\n✅ System Ready!")
    print(f" - Realtime: camera -> yolo (QoS.REALTIME) -> gateway")
    print(f" - Logging:  camera -> logger (QoS.DURABLE)")
    print("\n🚀 Starting EdgeFlow (Multi-System)...")
    
    sys.run()
    #run(sys) #if using multi Systems
