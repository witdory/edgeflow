# EdgeFlow CLI 사용 가이드

EdgeFlow는 Kubernetes 환경에 분산 AI 파이프라인을 쉽게 배포하고 관리할 수 있도록 전용 CLI 도구를 제공합니다.

## 🛠 설치 (Installation)

EdgeFlow CLI는 `uv`를 통해 전역 도구로 설치하는 것을 권장합니다.

```bash
# 1. uv 설치 (아직 없다면)
pip install uv

# 2. EdgeFlow CLI 설치 (전역 도구로 등록)
uv tool install git+https://github.com/seolgugu/edgeflow.git
```

설치가 완료되면 터미널 어디서든 `edgeflow` 명령어를 사용할 수 있습니다.

```bash
edgeflow --help
```

---

## 🚀 주요 명령어

### 1. 배포 (Deploy)

작성한 `main.py` 파일과 노드들을 분석하여 Kubernetes 매니페스트를 생성하고 배포합니다.

```bash
edgeflow deploy [MAIN_PY_PATH] [OPTIONS]
```

**사용 예시:**
```bash
# 기본 배포 (로컬 레지스트리 사용 시)
edgeflow deploy main.py --registry localhost:5000

# 특정 네임스페이스에 배포
edgeflow deploy main.py --registry localhost:5000 --namespace my-robot

# 드라이 런 (배포하지 않고 매니페스트 파일만 생성)
edgeflow deploy main.py --registry localhost:5000 --dry-run
```

**옵션:**
- `--registry`: 도커 이미지를 푸시할 레지스트리 주소 (필수, 예: `localhost:5000`, `docker.io/username`)
- `--namespace`: 배포할 Kubernetes 네임스페이스 (기본값: `default`)
- `--dry-run`: 실제 배포는 하지 않고 `.build/manifests` 경로에 YAML 파일만 생성합니다.
- `--no-build`: 이미지를 새로 빌드하지 않고 기존 이미지를 사용합니다.

### 2. 리소스 정리 (Clean)

배포된 파이프라인과 서비스를 네임스페이스에서 삭제합니다.

```bash
edgeflow clean [OPTIONS]
```

**사용 예시:**
```bash
# 기본 네임스페이스 정리
edgeflow clean

# 특정 네임스페이스 정리
edgeflow clean --namespace my-robot
```

**주의:** Redis 인프라(`redis`, `redis-data`)는 삭제되지 않고 유지됩니다. 인프라까지 삭제하려면 `kubectl delete`를 직접 사용해야 합니다.

### 3. 로그 확인 (Logs)

특정 노드의 로그를 실시간으로 확인합니다. (kubectl wrapper)

```bash
edgeflow logs [NODE_NAME] [OPTIONS]
```

**사용 예시:**
```bash
edgeflow logs camera-node
```

### 4. 업데이트 (Upgrade)

EdgeFlow 프레임워크를 최신 버전으로 자가 업데이트합니다. (`uv` 도구 활용)

```bash
edgeflow upgrade
```

**동작:**
- `uv tool install --force git+https://github.com/seolgugu/edgeflow.git` 명령어를 실행하여 최신 코드를 받아옵니다.

---

## 📂 프로젝트 구조 예시

CLI가 정상적으로 작동하려면 다음과 같은 프로젝트 구조를 권장합니다.

```
my-project/
├── main.py              # 파이프라인 정의 (System, Node 연결)
├── pyproject.toml       # 프로젝트 의존성
├── nodes/               # 노드 소스 코드
│   ├── camera/
│   │   ├── __init__.py
│   │   └── ...
│   └── yolo/
│       └── ...
└── ...
```

---

## ❓ 문제 해결 (Troubleshooting)

**Q. `command not found: edgeflow` 에러가 발생해요.**
A. `uv tool install` 후 PATH가 로드되지 않았을 수 있습니다. 터미널을 재시작하거나 `uv tool update-shell`을 실행해 보세요.

**Q. 배포 중 UnicodeDecodeError가 발생해요.**
A. 윈도우 환경에서 발생하던 인코딩 문제는 v0.2.0 버전에서 수정되었습니다. 최신 버전으로 업데이트해 주세요.
```bash
uv tool upgrade edgeflow
```
