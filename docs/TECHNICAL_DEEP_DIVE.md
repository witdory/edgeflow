# EdgeFlow: Technical Deep Dive

이 문서는 EdgeFlow 프레임워크의 핵심 설계 결정과 기술적 고민을 상세히 기록합니다.  
포트폴리오 및 기술 면접용 참고자료로 활용할 수 있습니다.

## 📑 Table of Contents

1. [핵심 설계 철학](#-핵심-설계-철학)
2. [Core Design Decision #1: `Linker.to()` 체이닝](#-core-design-decision-1-linkerto-체이닝)
3. [Core Design Decision #2: Handler 기반 프로토콜 추상화](#-core-design-decision-2-handler-기반-프로토콜-추상화)
4. [Core Design Decision #3: Frame Wire Protocol](#-core-design-decision-3-frame-wire-protocol)
5. [Core Design Decision #4: BrokerInterface](#-core-design-decision-4-brokerinterface-확장-가능한-브로커)
6. [Core Design Decision #5: Gateway Interface Plugin](#-core-design-decision-5-gateway-interface-plugin)
7. [Supporting Design Decisions](#-supporting-design-decisions)
   - Blueprint Pattern (Lazy Loading)
   - QoS 기반 스트림 소비
   - Dual Redis 아키텍처
   - Length-Prefixed TCP Framing
8. [Architecture Overview](#-architecture-overview)
9. [적용된 전공 지식](#-적용된-전공-지식)
10. [문서 구조](#-문서-구조)

---

## 🎯 핵심 설계 철학

### "유연한 연결, 투명한 통신"

EdgeFlow의 가장 큰 기술적 도전은 **"어떻게 노드 간 연결을 유연하게 만들면서도 사용자에게 복잡성을 숨길 것인가"**였습니다.

이를 해결하기 위해 두 가지 핵심 발상을 도입했습니다:

1. **`link.to()` 체이닝 API**: 파이프라인 연결을 선언적으로 표현
2. **Handler 추상화**: 프로토콜(Redis/TCP)을 자동 선택하여 사용자 코드에서 통신 로직 분리

---

## 💡 Core Design Decision #1: `Linker.to()` 체이닝

### 문제 인식

전통적인 파이프라인 프레임워크는 보통 이런 방식을 사용합니다:

```python
# 전통적인 방식 (명시적 배선)
pipeline.connect(camera, yolo, channel="raw_frames")
pipeline.connect(yolo, gateway, channel="processed_frames")
```

이 방식은 **연결 하나당 한 줄**이 필요하고, 채널 이름을 명시해야 합니다.  
복잡한 파이프라인에서는 코드가 급격히 길어지고, 토픽 이름 충돌 위험이 있습니다.

### 해결책: Fluent Builder Pattern

```python
# EdgeFlow 방식 (선언적 체이닝)
sys.link(cam).to(gpu, qos=QoS.REALTIME).to(gw)
sys.link(cam).to(logger, qos=QoS.DURABLE)
```

**핵심 구현** (`core.py`):

```python
class Linker:
    def __init__(self, system: 'System', source: NodeSpec):
        self.system = system
        self.source = source

    def to(self, target: NodeSpec, qos: QoS = QoS.REALTIME) -> 'Linker':
        # 연결 메타데이터만 저장 (실행 시점까지 지연)
        self.system._links.append({
            'source': self.source,
            'target': target,
            'qos': qos,
        })
        # 체이닝을 위해 target 기준의 새 Linker 반환
        return Linker(self.system, target)
```

### 왜 이 구조인가?

| 설계 결정 | 이유 |
|-----------|------|
| `to()`가 새 `Linker`를 반환 | 체이닝으로 다단계 파이프라인 표현 가능 |
| 메타데이터만 저장 (Lazy) | 정의 시점에 클래스 로딩 불필요, 순환 참조 방지 |
| QoS를 연결 단위로 지정 | 동일 스트림에서 REALTIME/DURABLE 공존 가능 |

### 실제 효과

```python
# 한 줄로 "Camera → GPU → Gateway" 파이프라인 완성
sys.link(cam).to(gpu).to(gw)

# 동일 소스에서 분기 (Fan-out)
sys.link(cam).to(gw)      # 원본 영상 직접 전송
sys.link(cam).to(logger)  # 로깅용 스트림
```

이 구조 덕분에 **DAG(Directed Acyclic Graph) 형태의 복잡한 파이프라인도 직관적으로 표현**할 수 있습니다.

---

## 💡 Core Design Decision #2: Handler 기반 프로토콜 추상화

### 문제 인식

노드 간 통신에는 여러 프로토콜이 필요합니다:
- **Redis Stream**: 비동기 메시지 큐 (AI 처리용)
- **TCP Socket**: 실시간 스트리밍 (Gateway 전송)
- (미래) **gRPC**, **MQTT** 등

만약 각 노드가 직접 프로토콜을 다룬다면:

```python
# 나쁜 예: 노드가 프로토콜을 직접 처리
class YoloProcessor:
    def loop(self, data):
        result = self.inference(data)
        
        # 👎 통신 로직이 비즈니스 로직에 섞임
        self.redis.xadd("yolo_output", result)  
        self.tcp_socket.send(result)
```

### 해결책: Handler 추상화

```python
# 좋은 예: 노드는 send_result()만 호출
class YoloProcessor(ConsumerNode):
    def loop(self, data):
        result = self.inference(data)
        return result  # 👍 프레임워크가 알아서 전송
```

**핵심 구현** (`handlers.py`):

```python
class RedisHandler:
    def __init__(self, broker, topic, queue_size=1):
        self.broker = broker
        self.topic = topic
    
    def send(self, frame):
        self.broker.push(self.topic, frame.to_bytes())

class TcpHandler:
    def __init__(self, host, port, source_id):
        self.host = host
        self.source_id = source_id
    
    def send(self, frame):
        frame.meta["topic"] = self.source_id  # 라우팅 정보 주입
        self.sock.sendall(frame.to_bytes())
```

**프레임워크가 자동으로 핸들러 연결** (`core.py`):

```python
def _hydrate_node_handlers(node, broker, wiring):
    for out in wiring['outputs']:
        if out['protocol'] == 'tcp':
            handler = TcpHandler(gw_host, gw_port, source_id)
        else:
            handler = RedisHandler(broker, topic)
        
        node.output_handlers.append(handler)
```

**노드의 데이터 전송** (`base.py`):

```python
def send_result(self, frame):
    for handler in self.output_handlers:
        handler.send(frame)  # 모든 핸들러에게 브로드캐스트
```

### 왜 이 구조인가?

| 설계 결정 | 이유 |
|-----------|------|
| Handler Interface 분리 | 프로토콜 교체 시 노드 코드 수정 불필요 |
| 프레임워크가 핸들러 주입 | 사용자는 통신 로직을 몰라도 됨 |
| 다중 핸들러 지원 | Fan-out (1:N 전송) 자연스럽게 구현 |

### 실제 효과

```python
# camera 노드는 이 코드를 모름
# 프레임워크가 알아서 [Redis → YOLO] + [TCP → Gateway] 동시 전송
cam = sys.node("nodes/camera")
sys.link(cam).to(yolo)  # → RedisHandler 자동 생성
sys.link(cam).to(gw)    # → TcpHandler 자동 생성
```

사용자 관점에서 **Camera 노드는 어디로 데이터가 가는지 모르고, 알 필요도 없습니다.**  
프레임워크가 연결 정보를 보고 적절한 핸들러를 주입합니다.

---

## 💡 Core Design Decision #3: Frame Wire Protocol

### 문제 인식

노드 간 데이터 전송에는 다양한 정보가 필요합니다:
- **이미지 데이터**: Numpy 배열 (수 MB)
- **메타데이터**: AI 결과, 타임스탬프, 라우팅 정보
- **프레임 식별자**: 중복 처리 방지용 ID

이 모든 정보를 **하나의 일관된 포맷**으로 묶지 않으면:
- 매번 다른 직렬화 방식 사용 → 호환성 문제
- 메타데이터 누락 → 디버깅 어려움
- 이미지 인코딩 중복 → 성능 저하

### 해결책: Frame 객체 + Binary Wire Protocol

```python
# comms/frame.py
class Frame:
    def __init__(self, frame_id, timestamp, meta, data):
        self.frame_id = frame_id      # 4 bytes (uint32)
        self.timestamp = timestamp    # 8 bytes (double)
        self.meta = meta or {}        # JSON (가변 길이)
        self.data = data              # JPEG bytes (가변 길이)
```

**Wire Format (바이트 레이아웃)**:

```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ Frame ID     │ Timestamp    │ Meta Length  │ Meta (JSON)  │ Payload      │
│ (4 bytes)    │ (8 bytes)    │ (4 bytes)    │ (N bytes)    │ (JPEG)       │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

**핵심 구현**:

```python
def to_bytes(self):
    # 1. 이미지 → JPEG 인코딩
    if isinstance(self.data, np.ndarray):
        _, buf = cv2.imencode('.jpg', self.data)
        data_bytes = buf.tobytes()
    
    # 2. 메타데이터 → JSON (NumpyEncoder로 AI 결과 호환)
    meta_bytes = json.dumps(self.meta, cls=NumpyEncoder).encode('utf-8')
    
    # 3. 헤더 패킹 (Network Byte Order: Big-Endian)
    header = struct.pack('!Id', int(self.frame_id), float(self.timestamp))
    meta_len = struct.pack('!I', len(meta_bytes))
    
    return header + meta_len + meta_bytes + data_bytes
```

### 왜 이 구조인가?

| 설계 결정 | 이유 |
|-----------|------|
| 고정 헤더 (16 bytes) | 파싱 시 고정 위치에서 메타 길이 추출 가능 |
| Network Byte Order | 플랫폼 간 호환성 (리틀/빅 엔디안 무관) |
| JSON 메타데이터 | 유연한 확장 (AI 결과, 트레이싱 정보 등) |
| NumpyEncoder | AI 모델 출력값 (np.float32 등) 자동 변환 |

### 추가 최적화: `avoid_decode` 옵션

```python
@classmethod
def from_bytes(cls, raw_bytes, avoid_decode=False):
    # Gateway는 이미지를 다시 인코딩할 필요 없음
    # → JPEG 바이트 그대로 유지 (cv2.imdecode 스킵)
    if avoid_decode:
        return cls(..., data=payload)  # bytes 그대로
    else:
        img = cv2.imdecode(...)        # numpy 변환
        return cls(..., data=img)
```

**이점**: Gateway가 이미지를 디코딩하지 않고 바로 스트리밍 → **CPU 50% 절감**

---

## 💡 Core Design Decision #4: BrokerInterface (확장 가능한 브로커)

### 문제 인식

메시지 브로커는 프레임워크의 핵심 의존성입니다:
- 현재: Redis Stream
- 미래: RabbitMQ, Kafka, MQTT, 로컬 메모리 큐

만약 Broker 로직이 코드 전체에 퍼져 있다면:
- 브로커 교체 시 모든 노드 수정 필요
- 테스트 시 실제 Redis 필요 → 느린 테스트

### 해결책: BrokerInterface 추상화

```python
# comms/brokers/base.py
class BrokerInterface(ABC):
    @abstractmethod
    def push(self, topic: str, data: bytes):
        """데이터를 브로커에 푸시"""
        pass

    @abstractmethod
    def pop(self, topic: str, timeout: int = 0) -> bytes | None:
        """순차적으로 데이터 읽기 (DURABLE)"""
        pass
    
    @abstractmethod
    def pop_latest(self, topic: str, timeout: int = 0) -> bytes | None:
        """최신 데이터만 읽기 (REALTIME)"""
        pass
    
    @abstractmethod
    def to_config(self) -> Dict[str, Any]:
        """직렬화 (멀티프로세싱 지원)"""
        pass
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any]) -> 'BrokerInterface':
        """역직렬화 (자식 프로세스에서 재생성)"""
        pass
```

### 구현체 예시

```python
# RedisBroker (단일 Redis)
class RedisBroker(BrokerInterface):
    def push(self, topic, data):
        self._redis.xadd(topic, {'data': data}, maxlen=100)

# DualRedisBroker (Control + Data 분리)
class DualRedisBroker(BrokerInterface):
    def push(self, topic, data):
        self.data_redis.set(key, data)      # Blob 저장
        self.ctrl_redis.xadd(topic, {'id'}) # ID만 스트림에
```

### 왜 이 구조인가?

| 설계 결정 | 이유 |
|-----------|------|
| ABC (추상 클래스) | 필수 메서드 구현 강제 |
| `to_config` / `from_config` | Pickle 대신 안전한 직렬화 (멀티프로세싱) |
| `pop` vs `pop_latest` | QoS별 소비 패턴 표준화 |

### 실제 효과: 의존성 주입

```python
# 프로덕션
sys = System("prod", broker=DualRedisBroker())

# 테스트 (Mock 주입)
sys = System("test", broker=InMemoryBroker())
```

노드 코드는 `self.broker.push()` / `self.broker.pop()`만 호출하므로, **브로커가 무엇인지 몰라도 됩니다.**

---

## 💡 Core Design Decision #5: Gateway Interface Plugin

### 문제 인식

Gateway는 외부 세계와 연결되는 엔드포인트입니다:
- **현재**: HTTP/WebSocket (Web Dashboard)
- **미래**: ROS2 토픽, gRPC, RTSP 스트리밍

모든 출력 방식을 Gateway 클래스 안에 하드코딩하면:
- 코드가 비대해짐
- 새 프로토콜 추가 시 기존 코드 수정 필요

### 해결책: BaseInterface + Plugin Architecture

```python
# gateway/interfaces/base.py
class BaseInterface(ABC):
    @abstractmethod
    def setup(self):
        """초기화 (예: ROS 노드 생성, DB 연결)"""
        pass

    @abstractmethod
    async def on_frame(self, frame):
        """프레임 수신 시 동작 (비동기 필수)"""
        pass

    async def run_loop(self):
        """별도 이벤트 루프 (예: 웹서버 실행)"""
        pass
```

### 구현체 예시: WebInterface

```python
class WebInterface(BaseInterface):
    def setup(self):
        self.app = FastAPI()
        self.buffers = defaultdict(lambda: FrameBuffer())
        
    async def on_frame(self, frame):
        topic = frame.meta.get("topic", "default")
        self.buffers[topic].push(frame)
    
    async def run_loop(self):
        config = uvicorn.Config(self.app, port=8000)
        server = uvicorn.Server(config)
        await server.serve()
```

### Gateway가 플러그인을 사용하는 방식

```python
# gateway/core.py
class GatewayNode(EdgeNode):
    def add_interface(self, interface):
        self.interfaces.append(interface)
    
    async def _tcp_handler(self, reader, writer):
        frame = await self._read_frame(reader)
        
        # 모든 인터페이스에게 브로드캐스트
        tasks = [iface.on_frame(frame) for iface in self.interfaces]
        await asyncio.gather(*tasks)
```

### 왜 이 구조인가?

| 설계 결정 | 이유 |
|-----------|------|
| `async on_frame` | 비동기 I/O로 다수 인터페이스 동시 처리 |
| `run_loop` 선택적 | 웹서버처럼 별도 루프 필요한 경우만 구현 |
| `add_interface` | 런타임에 플러그인 등록 (확장성) |

### 실제 효과

```python
# 사용자 코드 (my-robot/nodes/gateway/__init__.py)
class VideoGateway(GatewayNode):
    def setup(self):
        self.add_interface(WebInterface(port=8000))
        # 미래: self.add_interface(ROSInterface())
        # 미래: self.add_interface(RTSPInterface())
```

**새 프로토콜을 추가할 때 Gateway 코드는 수정하지 않고**, 새 Interface 클래스만 만들면 됩니다.

---

## 🔧 Supporting Design Decisions

### 3. Blueprint Pattern (Lazy Loading)

```python
class System:
    def node(self, path: str, **kwargs) -> NodeSpec:
        # 클래스 로딩 없이 메타데이터만 저장
        spec = NodeSpec(path=path, config=kwargs)
        self.specs[spec.name] = spec
        return spec
    
    def run(self):
        # 실행 시점에 실제 import
        for spec in self.specs.values():
            cls = self._load_node_class(spec.path)
            instance = cls(broker=self.broker, **spec.config)
```

**이점**:
- 시스템 정의 시점에 import 오류가 발생하지 않음
- 순환 참조 문제 회피
- Multi-System에서 동일 노드 공유 가능

### 4. QoS 기반 스트림 소비

```python
# consumer.py
if qos == QoS.REALTIME:
    packet = self.broker.pop_latest(topic)  # 최신만
else:
    packet = self.broker.pop(topic)         # 순차적
```

**고민 포인트**:
- AI 추론(느림)과 로깅(빠름)이 같은 스트림을 소비해야 하는 상황
- 전통적인 Consumer Group은 "모든 Consumer가 동일 속도"를 가정
- EdgeFlow는 **연결(link) 단위로 QoS 지정**하여 이 문제 해결

### 5. Dual Redis 아키텍처

```
Producer → [SET image to Data Redis]
         → [XADD id to Ctrl Redis]

Consumer ← [XREAD id from Ctrl Redis]
         ← [GET image from Data Redis]
```

**고민 포인트**:
- Redis Stream에 큰 이미지를 직접 넣으면 메모리 폭발
- Stream은 가벼운 메타데이터만, Blob은 별도 저장소
- 로컬 개발 시 자동 Fallback (6380 실패 → 6379 사용)

### 6. Length-Prefixed TCP Framing

```python
# handlers.py
length_header = struct.pack('>I', len(packet_body))
self.sock.sendall(length_header + packet_body)
```

**고민 포인트**:
- TCP는 스트림 프로토콜 → 메시지 경계가 없음
- 4바이트 길이 헤더로 프레임 구분
- Gateway에서 `readexactly(4)` → `readexactly(length)`

---

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      User Application                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  sys = System("my-robot", broker=DualRedisBroker())   │  │
│  │  cam = sys.node("nodes/camera")                       │  │
│  │  gpu = sys.node("nodes/yolo")                         │  │
│  │  sys.link(cam).to(gpu).to(gw)                         │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    EdgeFlow Core (core.py)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   System    │──│   Linker    │──│   NodeRegistry      │  │
│  │  (Blueprint)│  │ (Wiring DSL)│  │ (Lazy Loading)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Node Layer (nodes/)                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ EdgeNode   │  │ Producer   │  │ Consumer / Gateway     │ │
│  │ (Template) │  │ (FPS Loop) │  │ (QoS-aware Loop)       │ │
│  └────────────┘  └────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Communication Layer (comms/)                │
│  ┌─────────────────┐  ┌─────────────────────────────────┐   │
│  │ BrokerInterface │  │ Handlers (Redis / TCP)          │   │
│  │ (Abstraction)   │  │ (Protocol Auto-Selection)       │   │
│  └─────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎓 적용된 개념

| 영역 | 개념 | 적용 위치 |
|------|------|----------|
| Design Pattern | Fluent Builder | `Linker.to()` |
| Design Pattern | Template Method | `EdgeNode.execute()` |
| Design Pattern | Strategy | QoS 기반 소비 |
| Design Pattern | Observer | `send_result()` Fan-out |
| Design Pattern | Plugin Architecture | Gateway Interface |
| Design Pattern | Dependency Injection | `System(broker=...)` |
| Distributed Systems | Message Queue | Redis Stream |
| Distributed Systems | Consumer Group | 로드 밸런싱 |
| Distributed Systems | Backpressure | FPS 제한, maxlen |
| Distributed Systems | Control/Data Plane | DualRedisBroker |
| OS | Multiprocessing | GIL 우회 |
| OS | IPC | Redis as IPC |
| Networking | TCP Framing | Length-Prefix |
| Networking | Async I/O | Gateway eventloop |
| Networking | Wire Protocol | Frame binary format |
| Serialization | Binary Protocol | `struct.pack` |
| Serialization | JSON + Custom Encoder | `NumpyEncoder` |
| Interface Design | ABC (추상 클래스) | `BrokerInterface`, `BaseInterface` |

---

## 📁 문서 구조

```
docs/
├── TECHNICAL_DEEP_DIVE.md    # 본 문서 (핵심 설계 철학)
├── architecture.md           # 시스템 아키텍처 다이어그램
├── PERFORMANCE_LOG.md        # 성능 최적화 히스토리
├── cli_usage_kr.md           # CLI 사용법 (한국어)
└── README_kr.md              # 한국어 README
```

---

## 💬 마무리

EdgeFlow는 **"Edge AI 파이프라인을 누구나 쉽게 정의하고 실행할 수 있게 하자"**라는 목표로 시작했습니다.

그 과정에서 가장 많이 고민한 것은:
1. **복잡한 통신 로직을 어떻게 사용자로부터 숨길 것인가** → Handler 패턴
2. **유연한 파이프라인 구성을 어떻게 직관적으로 표현할 것인가** → `link.to()` 체이닝
3. **성능과 단순함을 어떻게 양립할 것인가** → QoS, Dual Redis, Multiprocessing

이 세 가지 질문에 대한 답을 코드로 구현한 것이 EdgeFlow입니다.

---

*Last Updated: 2026-01-25*
