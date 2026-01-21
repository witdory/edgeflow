import time
import os
import yaml
import datetime
from jinja2 import Template
from kubernetes import client, config
from edgeflow.constants import REDIS_HOST, REDIS_PORT # 상수 임포트 필수

def ensure_namespace(k8s_core, namespace):
    """네임스페이스 존재 확인 및 생성"""
    if namespace == "default": return

    try:
        k8s_core.read_namespace(name=namespace)
    except client.exceptions.ApiException as e:
        if e.status == 404:
            print(f"📦 Creating Namespace: {namespace}")
            ns_manifest = {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": namespace}
            }
            k8s_core.create_namespace(body=ns_manifest)
        else:
            raise e

def ensure_infrastructure(k8s_apps, k8s_core, namespace="default"):
    """
    Redis 인프라(Deployment + Service)가 없으면 띄우는 함수 (멱등성 보장)
    """
    print(f"🔍 Checking System Infrastructure (ns: {namespace})...")
    
    # Redis 템플릿 로드
    tpl_path = os.path.join(os.path.dirname(__file__), 'templates', 'redis.yaml.j2')
    with open(tpl_path) as f:
        manifests = list(yaml.safe_load_all(f.read()))

    # Deployment와 Service를 각각 체크하고 없으면 생성
    for manifest in manifests:
        kind = manifest['kind']
        name = manifest['metadata']['name']
        
        try:
            if kind == 'Service':
                k8s_core.read_namespaced_service(name=name, namespace=namespace)
            elif kind == 'Deployment':
                k8s_apps.read_namespaced_deployment(name=name, namespace=namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                print(f"  ⚠️ {kind}/{name} missing. Creating...")
                if kind == 'Service':
                    k8s_core.create_namespaced_service(namespace=namespace, body=manifest)
                elif kind == 'Deployment':
                    k8s_apps.create_namespaced_deployment(namespace=namespace, body=manifest)
            else:
                raise e
    
    print("  🚀 Infrastructure Check Complete.")

def deploy_to_k8s(app, image_tag, namespace="default"):
    # 템플릿 로드 (Deployment용)
    dep_tpl_path = os.path.join(os.path.dirname(__file__), 'templates', 'deployment.yaml.j2')
    with open(dep_tpl_path) as f:
        dep_template = Template(f.read())

    # 템플릿 로드 (Gateway Service용 - 새로 추가해야 함!)
    svc_tpl_path = os.path.join(os.path.dirname(__file__), 'templates', 'service.yaml.j2')
    has_svc_tpl = os.path.exists(svc_tpl_path)
    if has_svc_tpl:
        with open(svc_tpl_path) as f:
            svc_template = Template(f.read())

    # K8s 연결 (K3s 자동 감지 포함)
    try:
        config.load_kube_config()
    except Exception:
        # K3s 전용 경로 시도
        k3s_config = "/etc/rancher/k3s/k3s.yaml"
        if os.path.exists(k3s_config):
            print(f"📁 Using K3s config: {k3s_config}")
            config.load_kube_config(config_file=k3s_config)
        else:
            raise Exception("kubeconfig not found. Run: sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config")
    k8s_apps = client.AppsV1Api()
    k8s_core = client.CoreV1Api()

    # 0. 네임스페이스 준비
    ensure_namespace(k8s_core, namespace)

    # 1. 인프라 체크
    ensure_infrastructure(k8s_apps, k8s_core, namespace)

    print(f"🚀 Deploying {len(app.nodes)} nodes to namespace '{namespace}'...")

    # 2. 노드별 배포
    for name, node in app.nodes.items():
        # ---------------------------------------------------------
        # A. Deployment 생성 (공통)
        # ---------------------------------------------------------
        # Gateway 타입 여부 확인
        is_gateway = (getattr(node, 'type', None) == 'gateway')

        yaml_str = dep_template.render(
            name=name,
            image=image_tag,
            device=getattr(node, 'device', None),
            replicas=getattr(node, 'replicas', 1),
            is_gateway=is_gateway, # 템플릿에 전달하여 role:infra 할당 유도
            # 프레임워크 내부 통신용 환경변수 주입
            env_vars={
                "REDIS_HOST": f"{REDIS_HOST}.{namespace}.svc.cluster.local", # 네임스페이스 포함 DNS
                "REDIS_PORT": str(REDIS_PORT),
                "GATEWAY_HOST": f"gateway-svc.{namespace}.svc.cluster.local", # [신규] Gateway 주소 주입
                "GATEWAY_TCP_PORT": "8080", # [원복] TCP 포트 8080 고정
                "NODE_NAME": name
            }
        )
        manifest = yaml.safe_load(yaml_str)

        # ⭐ 핵심: 강제 재시작을 위해 Annotation에 배포 시간 기록
        if 'annotations' not in manifest['spec']['template']['metadata']:
            manifest['spec']['template']['metadata']['annotations'] = {}
        manifest['spec']['template']['metadata']['annotations']['kubectl.kubernetes.io/restartedAt'] = datetime.datetime.now().isoformat()

        try:
            k8s_apps.create_namespaced_deployment(namespace=namespace, body=manifest)
            print(f"  + [App] Created: {name}")
        except client.exceptions.ApiException as e:
            if e.status == 409: # Already Exists -> Update
                k8s_apps.patch_namespaced_deployment(name=manifest['metadata']['name'], namespace=namespace, body=manifest)
                print(f"  * [App] Updated: {name} (Rolling Update)")
            else:
                raise e

        # ---------------------------------------------------------
        # B. Service 생성 (Gateway 타입인 경우만)
        # ---------------------------------------------------------
        if getattr(node, 'type', None) == 'gateway' and has_svc_tpl:
            # nodePort만 사용자 설정 가능, 내부 port는 프레임워크 고정
            gateway_node_port = getattr(node, 'node_port', 30000)  # None이면 K8s 자동 할당
            
            svc_yaml = svc_template.render(
                name=name,
                port=8000,  # 프레임워크 웹 인터페이스 (HTTP)
                tcp_port=8080, # [신규] 내부 통신용 TCP 포트 추가
                node_port=gateway_node_port
            )
            svc_manifest = yaml.safe_load(svc_yaml)
            
            try:
                k8s_core.create_namespaced_service(namespace=namespace, body=svc_manifest)
                port_msg = f":{gateway_node_port}" if gateway_node_port else " (auto-assigned)"
                print(f"  + [Svc] Exposed Gateway: http://<NODE-IP>{port_msg}")
            except client.exceptions.ApiException as e:
                if e.status == 409:
                    # 서비스 설정 변경(포트 등) 반영을 위해 과감하게 재생성 (개발 편의성)
                    print(f"  🔄 Service exists. Re-creating to apply changes...")
                    k8s_core.delete_namespaced_service(name=svc_manifest['metadata']['name'], namespace=namespace)
                    config.time.sleep(1) # 삭제 대기
                    k8s_core.create_namespaced_service(namespace=namespace, body=svc_manifest)
                    port_msg = f":{gateway_node_port}" if gateway_node_port else " (auto-assigned)"
                    print(f"  + [Svc] Re-created Gateway Service: http://<NODE-IP>{port_msg}")
                # [신규] 포트 충돌(422) 시 강제 삭제 후 재생성 시도
                elif e.status == 422 and "provided port is already allocated" in str(e.body):
                    print(f"  ⚠️ Port {gateway_node_port} conflict detected. Deleting existing service...")
                    try:
                        # 기존 서비스 삭제 (이름으로 삭제)
                        k8s_core.delete_namespaced_service(name=svc_manifest['metadata']['name'], namespace=namespace)
                        print("  🗑️ Debug: Deleted conflicting service.")
                        # 잠시 대기 후 재생성
                        k8s_core.create_namespaced_service(namespace=namespace, body=svc_manifest)
                        print(f"  + [Svc] Re-created Gateway Service on port {gateway_node_port}")
                    except Exception as retry_e:
                        print(f"  ❌ Failed to resolve port conflict: {retry_e}")
                        raise retry_e
                else:
                    raise e