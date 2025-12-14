#main.py
from edgeflow import EdgeApp
import time
import numpy as np
import cv2

app = EdgeApp("test-app")

@app.producer(fps=10)
def camera():
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    return frame # Numpy 반환 (자동 직렬화)

@app.consumer(replicas=1)
def ai(frame): # Numpy로 들어옴 (자동 역직렬화)
    cv2.putText(frame, "Processed", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return frame # Numpy 반환 (자동 직렬화)

@app.gateway(port=8000)
def view(frame):
    return frame

if __name__ == "__main__":
    import sys
    role = sys.argv[1] if len(sys.argv) > 1 else "producer"
    app.run(role)