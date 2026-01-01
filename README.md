# 🌊 EdgeFlow (v0.2.0)

**EdgeFlow**는 Redis Pub/Sub 기반의 **분산형 실시간 비디오/센서 데이터 처리 프레임워크**입니다.
복잡한 네트워크 소켓 프로그래밍 없이도, 데코레이터(`@app.node`)만으로 **카메라 스트리밍, AI 추론, 센서 퓨전, 웹 모니터링** 시스템을 손쉽게 구축할 수 있습니다.

---

## ✨ 핵심 특징 및 설계 철학 (Core Features & Philosophy)

EdgeFlow는 **'최신 데이터 우선(Latest-first)'** 및 **'완전 분산(Fully Distributed)'** 원칙을 바탕으로 설계되었습니다.

### 1. ⚡ 극한의 실시간성 (Latest-First & Tunable)
* **최신 데이터 보장:** 제어 시스템에서 오래된 데이터는 무의미합니다. 시스템 과부하 시 큐에 쌓인 데이터를 과감히 버리고(Drop), **가장 최근 프레임**을 최우선으로 처리합니다.
* **지연 vs 안정성 튜닝:** 사용자는 **`queue_size`**(Redis)와 **`buffer_delay`**(Gateway) 파라미터를 통해, 상황에 맞춰 **'Zero Latency'** 와 **'Smooth Streaming'** 사이의 균형을 직접 조절할 수 있습니다.

### 2. 📡 완전 분산 아키텍처 (Distributed & Stateless)
* **물리적 분리:** Redis를 통해 데이터가 흐르므로, 카메라(Edge)와 AI 서버(GPU Server)가 서로 다른 머신에 있어도 완벽하게 동작합니다.
* **Stateless 확장:** 모든 처리 노드(Consumer)는 상태를 가지지 않으므로, 노드를 복제하는 것만으로 즉각적인 수평 확장이 가능합니다.
* **멀티 토픽:** 여러 센서 데이터를 토픽별(예: `cam_1`, `lidar_raw`)로 구분하여 독립적으로 처리합니다.

### 3. 🌪️ 이종 센서 퓨전 (Time-Sync Fusion)
* **FusionNode:** 서로 다른 주사율(FPS)을 가진 센서(예: 30FPS 카메라 + 10FPS 라이다) 데이터를 **타임스탬프 기준으로 정밀하게 동기화**하여 처리합니다. (`slop` 기반 매칭)
* **SLAM/Robotics 최적화:** 로보틱스 및 자율주행 알고리즘 구현에 필수적인 데이터 정렬을 자동으로 수행합니다.

### 4. 🧩 모듈형 설계 및 편의성 (Modular & Developer Friendly)
* **웹 게이트웨이 내장:** 별도의 백엔드 개발 없이, 브라우저에서 실시간 영상과 메타데이터(JSON)를 확인하는 MJPEG/API 서버가 내장되어 있습니다.
* **플러그인 & DI:** 통신 브로커(Redis)는 의존성 주입(DI)으로, 게이트웨이 인터페이스는 플러그인(`add_interface`) 방식으로 설계되어 유연한 확장이 가능합니다.

---

## 🛠 아키텍처 (Architecture)

EdgeFlow는 **Producer(생산) ➡️ Consumer/Fusion(가공) ➡️ Gateway(소비/시각화)** 의 파이프라인으로 구성됩니다.

(추후 다이어그램 추가 예정)

## 🚀 시작하기 (Quick Start)

### 1. 사전 요구 사항 (Prerequisites)
* Python 3.9+
* Redis Server (Local or Remote)
* Git

### 2. 설치 (Installation)

**1) 저장소 복제**
```bash
git clone https://github.com/witdory/edgeflow.git
cd edgeflow
```

**2) 가상환경 생성 및 활성화 (권장)**
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

**3) 의존성 설치**
```bash
pip install -r requirements.txt
```

### 3. 예제 실행 (`main.py`)

아래 코드를 `main.py`로 작성하고, 각 노드들을 실행하면, 카메라 데이터 생성부터 AI 처리, 웹 시각화까지 한 번에 테스트할 수 있습니다.

```bash
python main.py --node gateway
python main.py --node cam
python main.py --node lidar
python main.py --node fusion
python main.py --node bridge
```

```python
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
@app.node(name="lidar", type="producer", fps=10, topic="lidar_data")
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
```

---

## 📚 노드 문서 (Nodes Documentation)

### 1. ProducerNode (`type="producer"`)
데이터를 생성하여 Redis로 송출합니다.
* **주요 설정:** `fps` (주사율), `topic` (출력 토픽)
* **구현:** `produce(self)` 메서드에서 데이터(Numpy 등) 반환.

### 2. ConsumerNode (`type="consumer"`)
단일 토픽을 구독하여 데이터를 가공한 뒤 재송출합니다.
* **주요 설정:** `input_topic` (구독), `output_topic` (발행)
* **구현:** `process(self, frame)` 메서드에서 처리 결과 반환.

### 3. FusionNode (`type="fusion"`)
여러 토픽의 데이터를 **타임스탬프(Timestamp) 기준으로 동기화**하여 처리합니다. SLAM이나 센서 퓨전에 필수적입니다.
* **주요 설정:** `configure()`에서 `self.input_topics` 및 `self.slop`(허용 오차) 설정.
* **작동 원리:** 내부 버퍼를 사용하여 오차 범위 내의 프레임 쌍을 찾아 `process(self, frames)`로 전달합니다.

### 4. GatewayNode (`type="gateway"`)
Redis 데이터를 외부(Web, TCP 등)로 노출합니다.
* **플러그인 시스템:** `add_interface()`를 통해 `WebInterface` 등 다양한 통신 모듈을 장착할 수 있습니다.
* **WebInterface:** MJPEG 스트리밍 및 REST API를 제공합니다.

---

## 🖥️ 웹 대시보드 라우트

Gateway 실행 시 콘솔에 사용 가능한 접속 주소가 표시됩니다.

| Method | Path | 설명 |
| :--- | :--- | :--- |
| `GET` | `/video` | 기본(default) 토픽 스트리밍 |
| `GET` | `/video/{topic}` | 특정 토픽(예: `fused_view`) 스트리밍 |
| `GET` | `/api/status` | 최신 메타데이터 JSON 조회 |
| `GET` | *(Custom)* | 사용자가 추가한 커스텀 API |

---