# Edgeflow CLI 사용 가이드

Edgeflow v0.2.0부터 제공되는 강력한 CLI 도구 사용법입니다.
개발(Development), 빌드(Build), 운영(Operation) 전 과정을 터미널에서 제어할 수 있습니다.

---

## 1. 노드 배포 (`deploy`)

`main.py`에 정의된 시스템을 분석하여 Docker 이미지를 빌드하고 Kubernetes에 배포합니다.

```bash
# 기본 사용법
edgeflow deploy main.py --registry <your-registry>

# 예시
edgeflow deploy examples/my-robot/main.py --registry localhost:5000
```

### 주요 옵션
| 옵션 | 설명 |
| :--- | :--- |
| `--registry` | 이미지를 저장할 Docker Registry 주소 (필수) |
| `--namespace` | K8s 네임스페이스 지정 (기본값: `edgeflow`) |
| `--dry-run` | 실제 배포하지 않고, `.build/` 폴더에 매니페스트(YAML)만 생성 |
| `--no-build` | 이미지 빌드를 건너뛰고 기존 이미지를 사용하여 배포 |

> **꿀팁**: `--dry-run`을 사용하면 생성될 Dockerfile과 K8s YAML을 눈으로 미리 검토할 수 있습니다!

---

## 2. 패키지 추가 (`add`)

특정 노드에만 필요한 파이썬 라이브러리를 추가합니다. `node.toml`을 직접 열지 않아도 됩니다.

```bash
# 노드 지정하여 패키지 추가
edgeflow add <패키지명> --node <노드경로>

# 예시: 카메라 노드에 numpy 추가
edgeflow add numpy --node nodes/camera
```

*   **실행 결과**: `nodes/camera/node.toml` 파일의 `dependencies` 목록에 `"numpy"`가 자동으로 추가됩니다.
*   **빌드 반영**: 다음 `deploy` 실행 시 `uv`가 자동으로 해당 패키지를 포함하여 빌드합니다.

---

## 3. 로그 조회 (`logs`)

분산된 노드들의 로그를 쉽게 열람합니다. `kubectl logs` 명령어를 몰라도 됩니다.

```bash
# 노드 이름으로 로그 조회
edgeflow logs <노드이름>

# 예시
edgeflow logs camera
edgeflow logs yolo -n my-namespace
```

*   **특징**: `Deployment`로 배포된 파드(Pod)를 자동으로 찾아 로그를 스트리밍(`-f`)합니다.
*   `-n` 옵션으로 네임스페이스를 지정할 수 있습니다.

---

## 요약

| 단계 | 명령어 | 역할 |
| :--- | :--- | :--- |
| **개발** | `edgeflow add` | 노드별 필요한 라이브러리 추가 |
| **배포** | `edgeflow deploy` | 빌드 및 클러스터 배포 자동화 |
| **운영** | `edgeflow logs` | 실행 중인 노드 상태 모니터링 |
