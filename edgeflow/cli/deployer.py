import os
import yaml
import datetime
from jinja2 import Template
from kubernetes import client, config
from edgeflow.constants import REDIS_HOST, REDIS_PORT # 상수 임포트 필수

def ensure_infrastructure(k8s_apps, k8s_core):
    """
    Redis 인프라(Deployment + Service)가 없으면 띄우는 함수 (멱등성 보장)
    """
    print("🔍 Checking System Infrastructure...")
    
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
                k8s_core.read_namespaced_service(name=name, namespace="default")
            elif kind == 'Deployment':
                k8s_apps.read_namespaced_deployment(name=name, namespace="default")
            # print(f"  ✅ {kind}/{name} is running.")
        except client.exceptions.ApiException as e:
            if e.status == 404:
                print(f"  ⚠️ {kind}/{name} missing. Creating...")
                if kind == 'Service':
                    k8s_core.create_namespaced_service(namespace="default", body=manifest)
                elif kind == 'Deployment':
                    k8s_apps.create_namespaced_deployment(namespace="default", body=manifest)
            else:
                raise e
    
    print("  🚀 Infrastructure Check Complete.")

def deploy_to_k8s(app, image_tag):
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

    # K8s 연결
    config.load_kube_config()
    k8s_apps = client.AppsV1Api()
    k8s_core = client.CoreV1Api()

    # 1. 인프라 체크
    ensure_infrastructure(k8s_apps, k8s_core)

    print(f"🚀 Deploying {len(app.nodes)} nodes...")

    # 2. 노드별 배포
    for name, node in app.nodes.items():
        # ---------------------------------------------------------
        # A. Deployment 생성 (공통)
        # ---------------------------------------------------------
        yaml_str = dep_template.render(
            name=name,
            image=image_tag,
            device=getattr(node, 'device', None),
            replicas=getattr(node, 'replicas', 1),
            # 프레임워크 내부 통신용 환경변수 주입
            env_vars={
                "REDIS_HOST": REDIS_HOST,
                "REDIS_PORT": str(REDIS_PORT),
                "NODE_NAME": name
            }
        )
        manifest = yaml.safe_load(yaml_str)

        # ⭐ 핵심: 강제 재시작을 위해 Annotation에 배포 시간 기록
        if 'annotations' not in manifest['spec']['template']['metadata']:
            manifest['spec']['template']['metadata']['annotations'] = {}
        manifest['spec']['template']['metadata']['annotations']['kubectl.kubernetes.io/restartedAt'] = datetime.datetime.now().isoformat()

        try:
            k8s_apps.create_namespaced_deployment(namespace="default", body=manifest)
            print(f"  + [App] Created: {name}")
        except client.exceptions.ApiException as e:
            if e.status == 409: # Already Exists -> Update
                k8s_apps.patch_namespaced_deployment(name=manifest['metadata']['name'], namespace="default", body=manifest)
                print(f"  * [App] Updated: {name} (Rolling Update)")
            else:
                raise e

        # ---------------------------------------------------------
        # B. Service 생성 (Gateway 타입인 경우만)
        # ---------------------------------------------------------
        if getattr(node, 'type', None) == 'gateway' and has_svc_tpl:
            # nodePort만 사용자 설정 가능, 내부 port는 프레임워크 고정
            gateway_node_port = getattr(node, 'node_port', None)  # None이면 K8s 자동 할당
            
            svc_yaml = svc_template.render(
                name=name,
                port=8080,  # 프레임워크 내부 고정값
                node_port=gateway_node_port
            )
            svc_manifest = yaml.safe_load(svc_yaml)
            
            try:
                k8s_core.create_namespaced_service(namespace="default", body=svc_manifest)
                port_msg = f":{gateway_node_port}" if gateway_node_port else " (auto-assigned)"
                print(f"  + [Svc] Exposed Gateway: http://<NODE-IP>{port_msg}")
            except client.exceptions.ApiException as e:
                if e.status == 409:
                    # 서비스는 보통 설정이 잘 안 바뀌므로 패스하거나 patch
                    print(f"  . [Svc] Gateway service already exists.")
                else:
                    raise e