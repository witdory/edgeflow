# EdgeFlow Performance Optimization Log

이 문서는 프로젝트 개발 과정에서 발생한 성능 이슈, 원인 분석, 그리고 해결 과정을 기록합니다.

---

## [2026-01-25] FPS 저하 및 중복 처리 이슈 (Initial Major Fix)

### 1. 이슈 개요
멀티프로세스 환경에서 시스템 구동 시 FPS가 기대치(30fps)의 절반 이하(10fps)로 떨어지고, CPU/네트워크 자원이 비정상적으로 낭비됨.

### 2. 원인 분석

#### A. Consumer 측: 무의미한 중복 추론 (CPU/GPU 낭비)
- **증상**: YOLO 노드가 같은 프레임을 계속 반복해서 처리함.
- **원인**: `pop_latest()` 함수가 새로운 데이터가 없을 때도 **직전에 읽었던 최신 데이터**를 그대로 반환함.
- **영향**: 처리 속도가 빠른 Consumer(GPU)가 Producer(Camera)보다 더 빨리 루프를 돌며 같은 이미지를 수십 번씩 재처리함.

#### B. Producer 측: 동기식 네트워크 병목 (Latency 증가)
- **증상**: Camera 루프 자체가 느려짐.
- **원인**: `DualRedisBroker.push()` 메서드가 `SET` (이미지 저장)과 `XADD` (메시지 알림)을 **각각 별도의 동기 요청**으로 보냄.
- **영향**: 네트워크 왕복 시간(RTT)이 2배로 늘어나 FPS 상한선을 제한함.

#### C. Core 측: 중복 핸들러 생성 (결정적 원인 💥)
- **증상**: 프레임 하나를 Redis로 2~3번씩 중복 전송함.
- **원인**: `system.link(cam).to(yolo)`와 `system.link(cam).to(logger)`를 호출할 때마다, Camera 노드에 **`RedisHandler`가 중복으로 추가됨**.
- **영향**: 토픽은 하나(`camera`)인데, 핸들러가 2개라 **똑같은 데이터를 두 번씩 직렬화하고 두 번씩 전송**. 네트워크/CPU 부하 2배 증가.

### 3. 해결 방안

#### A. Deduplication (중복 방지)
- Consumer가 `last_frame_id`를 기억하여, **새로운 ID가 도착했을 때만** 데이터를 반환하도록 수정.
- 데이터가 없으면 `XREAD(block=timeout)`을 통해 효율적으로 대기 (Busy Waiting 제거).
- `BrokerInterface`에 `pop_latest` 표준화 및 `RedisBroker`에도 적용.

#### B. Pipelining (파이프라이닝)
- Producer가 `SET`과 `XADD` 명령어를 **Redis Pipeline**으로 묶어서 한 번의 요청으로 전송.
- 네트워크 RTT를 50% 절감.

#### C. Handler Deduplication (핸들러 중복 제거)
- `_hydrate_node_handlers` 로직 수정.
- 같은 토픽(`node.name`)을 사용하는 핸들러가 이미 존재하면, 추가하지 않고 건너뜀.
- **1 Producer = 1 Redis Push** 보장.

### 4. 결과
- 불필요한 네트워크 트래픽 50% 이상 감소
- CPU/GPU 중복 연산 100% 제거
- **목표 FPS (30fps) 및 낮은 Latency 회복**
