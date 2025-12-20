#main.py
from edgeflow import EdgeApp
import time
import numpy as np
import cv2

app = EdgeApp("test-app")

@app.producer(fps=10)
def camera():
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    return frame 

@app.consumer(replicas=1)
def ai(frame): 
    cv2.putText(frame, "Processed", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    metadata = {
        "detected": True,
        "count": 1,
        "timestamp": time.time()
    }
    return frame, metadata

@app.gateway(port=8000)
class MySmartGateway:
    def setup(self):
        # ROS2 노드 초기화/연결
        print("Gateway 연결 준비 완료 (ROS2/HTTP 초기화 가능)")
        # self.ros_pub = ROS2Publisher("/result")
    
    def on_message(self, frame, meta):
        """
        Consumer로부터 데이터가 도착할 때마다 실행
        frame: 이미지 바이트, meta: 결과 데이터 딕셔너리
        """
        if meta.get("detected"):
            print(meta)
            # self.ros_pub.publish(meta)
        
        # 리턴한 값은 Gateway의 MJPEG 스트림 화면에 표시됨
        # 만약 화면에 표시하고 싶지 않으면 None 리턴
        return frame

if __name__ == "__main__":
    app.run()