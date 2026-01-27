# EdgeFlow 클러스터 실행 가이드 (Getting Started)

이 문서는 빈 Kubernetes 클러스터 환경에서 EdgeFlow 프레임워크를 설치하고, 예제 프로젝트를 배포하여 실행하는, 처음부터 끝까지의 과정을 설명합니다.

---

## 1. 사전 준비 (Prerequisites)

EdgeFlow를 실행하기 위해서는 다음 두 가지가 준비되어 있어야 합니다.

### 1-1. Kubernetes 클러스터
- **Edge Device**: [K3s](https://k3s.io/) 설치를 권장합니다. (가볍고 설치가 빠름)
- **Cloud/Server**: 모든 표준 Kubernetes 클러스터(EKS, GKE, kubeadm 등)를 지원합니다.

```bash
# K3s 설치 예시 (Linux)
curl -sfL https://get.k3s.io | sh -
```

### 1-2. Docker Registry
- EdgeFlow는 각 노드를 컨테이너 이미지로 빌드하여 배포합니다.
- 클러스터가 접근 가능한 컨테이너 레지스트리가 필요합니다. (Docker Hub, GHCR, 또는 로컬 레지스트리)

**로컬 레지스트리 실행 (테스트용):**
```bash
docker run -d -p 5000:5000 --restart=always --name registry registry:2
```
> **참고:** 로컬 레지스트리 사용 시, K3s/K8s 설정에서 `http://localhost:5000`을 insecure registry로 등록해야 할 수 있습니다.

---

## 2. 도구 설치

관리용 PC(또는 마스터 노드)에 `uv`와 `edgeflow` CLI를 설치합니다.

```bash
# 1. uv 설치
pip install uv

# 2. EdgeFlow CLI 설치
uv tool install git+https://github.com/seolgugu/edgeflow.git
```

---

## 3. 예제 프로젝트 준비

EdgeFlow 저장소를 클론하여 포함된 예제(`examples/my-robot`)를 사용해 봅시다.

```bash
# 저장소 클론
git clone https://github.com/seolgugu/edgeflow.git
cd edgeflow/examples/my-robot
```

이 예제 프로젝트는 다음과 같이 구성되어 있습니다:
- `main.py`: 파이프라인 정의 (Camera -> AI -> Monitor)
- `nodes/`: 각 노드의 소스 코드

---

## 4. 클러스터 배포 (Deploy)

EdgeFlow는 노드의 역할(Gateway)이나 하드웨어 요구사항(GPU, Camera)에 따라 파드를 적절한 노드에 배치하기 위해 **Kubernetes Node Label**을 사용합니다.

### 4-1. 노드 라벨링 (Node Labeling)

배포 전, 각 노드에 적절한 라벨을 붙여야 파드가 정상적으로 스케줄링됩니다. (단일 노드 클러스터라면 한 노드에 모두 붙이면 됩니다.)

```bash
# Gateway용 라벨 (필수)
kubectl label nodes <your-node-name> edgeflow.io/role=infra

# Camera 노드용 (device='video0'로 설정된 경우)
kubectl label nodes <your-node-name> edgeflow.io/device=video0

# GPU/NPU 노드용 (device='gpu'로 설정된 경우)
kubectl label nodes <your-node-name> edgeflow.io/device=gpu
```

> **Tip:** `<your-node-name>`은 `kubectl get nodes`로 확인할 수 있습니다.

### 4-2. 배포 실행

이제 `edgeflow deploy` 명령어로 클러스터에 배포합니다. `--registry` 옵션은 필수입니다.

```bash
# 로컬 레지스트리(localhost:5000)를 사용하는 경우
edgeflow deploy main.py --registry localhost:5000
```

**배포 과정:**
1. **Build**: 각 노드(`nodes/*`)를 Docker 이미지로 빌드합니다.
2. **Push**: 빌드된 이미지를 지정된 레지스트리(`localhost:5000/...`)로 푸시합니다.
3. **Manifest**: K8s Deployment/Service YAML 파일을 생성합니다.
4. **Apply**: 클러스터에 리소스를 생성하고 파드를 실행합니다.

---

## 5. 실행 확인 및 모니터링

### 5-1. 실행 상태 확인
```bash
# 파드 상태 확인
kubectl get pods

# 예상 출력:
# NAME                             READY   STATUS    RESTARTS   AGE
# redis-master-0                   1/1     Running   0          2m
# my-robot-nodes-camera-xxx        1/1     Running   0          30s
# my-robot-nodes-processing-xxx    1/1     Running   0          30s
```

### 5-2. 로그 모니터링
특정 노드가 잘 작동하는지 로그를 확인합니다.

```bash
# 카메라 노드 로그 확인
edgeflow logs camera
```

### 5-3. 대시보드 접속 (Gateway)
`gateway` 노드가 포함된 경우, NodePort를 통해 웹 대시보드에 접속할 수 있습니다.
(기본적으로 Gateway Service는 NodePort 30000번 대역을 사용하도록 설정될 수 있습니다. `kubectl get svc`로 확인하세요.)

```bash
kubectl get svc
# 출력 예시:
# gateway-service   NodePort   10.43.x.x   <none>   8000:30005/TCP
```
위 경우 `http://<NODE-IP>:30005` 로 접속하여 데이터를 확인할 수 있습니다.

---

## 6. 정리 (Cleanup)

테스트가 끝났다면 생성된 리소스를 정리합니다.

```bash
edgeflow clean
```
> **Note:** Redis 인프라는 다음 배포를 위해 유지됩니다. 완전히 삭제하려면 `kubectl delete deployment redis ...` 등을 직접 실행하세요.
