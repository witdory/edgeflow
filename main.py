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
def view(frame):
    return frame

if __name__ == "__main__":
    app.run()