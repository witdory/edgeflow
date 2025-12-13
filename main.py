from edgeflow import EdgeApp
import time
import numpy as np
import cv2

app = EdgeApp("test-app")

@app.producer(fps=10)
def camera():
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    

    _, buf = cv2.imencode('.jpg', frame)
    return buf.tobytes()

@app.consumer(replicas=1)
def ai(frame_bytes):
    # [핵심 수정] 받은 데이터는 bytes이므로, 다시 이미지(Numpy)로 복원해야 함
    nparr = np.frombuffer(frame_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    cv2.putText(frame, "Processed", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    _, buf = cv2.imencode('.jpg', frame)
    return buf.tobytes()

@app.gateway(port=8000)
def view(frame):
    return frame

if __name__ == "__main__":
    import sys
    role = sys.argv[1] if len(sys.argv) > 1 else "producer"
    app.run(role)