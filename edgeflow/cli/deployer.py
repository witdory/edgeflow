# edgeflow/cli/deployer.py
"""K8s deployment system for per-node container architecture"""

import time
import os
import yaml
import json
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from jinja2 import Template
from kubernetes import client, config

from edgeflow.constants import (
    REDIS_HOST, REDIS_PORT, 
    GATEWAY_TCP_PORT, GATEWAY_HTTP_PORT, 
    DATA_REDIS_HOST, DATA_REDIS_PORT
)
from .builder import build_all_nodes


def ensure_namespace(k8s_core, namespace: str):
    """Ensure namespace exists, create if not"""
    if namespace == "default":
        return

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


def ensure_infra_resource(k8s_apps, k8s_core, namespace: str, template_name: str):
    """Deploy infrastructure template (Redis etc.)"""
    tpl_path = os.path.join(os.path.dirname(__file__), 'templates', template_name)
    with open(tpl_path, encoding='utf-8') as f:
        manifests = list(yaml.safe_load_all(f.read()))

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
                print(f"  ⚠️ [Infra] {kind}/{name} missing. Creating...")
                if kind == 'Service':
                    k8s_core.create_namespaced_service(namespace=namespace, body=manifest)
                elif kind == 'Deployment':
                    k8s_apps.create_namespaced_deployment(namespace=namespace, body=manifest)
            else:
                raise e


def ensure_infrastructure(k8s_apps, k8s_core, broker, namespace: str = "default"):
    """Deploy required Redis infrastructure based on broker type"""
    from edgeflow.comms.brokers.dual_redis import DualRedisBroker
    
    print(f"🔍 Checking Infrastructure for {broker.__class__.__name__}...")
    
    # Basic Redis (Control Plane) - always deploy
    ensure_infra_resource(k8s_apps, k8s_core, namespace, 'redis.yaml.j2')

    # Dual Mode -> also deploy Data Redis
    if isinstance(broker, DualRedisBroker):
        print(f"  🚀 Dual Mode Detected! Deploying Data Redis...")
        ensure_infra_resource(k8s_apps, k8s_core, namespace, 'redis-data.yaml.j2')
    
    print("  ✅ Infrastructure Ready.")


def deploy_to_k8s(
    system,  # System instance
    registry: str,
    namespace: str = "default",
    build: bool = True,
    push: bool = True,
    dry_run: bool = False
):
    """
    Deploy System to Kubernetes with per-node images.
    
    Args:
        system: System instance with registered nodes
        registry: Docker registry URL
        namespace: K8s namespace
        build: Whether to build images before deploy
        push: Whether to push images to registry
        dry_run: If True, save manifests to .build/ instead of applying
    """
    project_root = Path.cwd()
    
    # Load templates
    tpl_dir = Path(__file__).parent / 'templates'
    with open(tpl_dir / 'deployment.yaml.j2', encoding='utf-8') as f:
        dep_template = Template(f.read())
    
    svc_tpl_path = tpl_dir / 'service.yaml.j2'
    has_svc_tpl = svc_tpl_path.exists()
    if has_svc_tpl:
        with open(svc_tpl_path, encoding='utf-8') as f:
            svc_template = Template(f.read())

    # Build per-node images
    node_paths = [spec.path for spec in system.specs.values()]
    
    if build:
        images = build_all_nodes(
            project_root=project_root,
            node_paths=node_paths,
            registry=registry,
            push=push,
            dry_run=dry_run
        )
    else:
        # Assume images already exist
        images = {
            path: f"{registry}/{project_root.name}-{path.replace('/', '-')}:latest"
            for path in node_paths
        }

    if dry_run:
        # Save manifests to .build/
        manifest_dir = project_root / ".build" / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        print(f"📄 [Dry-run] Saving manifests to {manifest_dir}")
        
        for name, spec in system.specs.items():
            image_tag = images.get(spec.path, "unknown")
            node_type = spec.config.get("type", "generic")
            is_gateway = node_type == "gateway"
            
            yaml_str = dep_template.render(
                name=name.replace('_', '-'),
                image=image_tag,
                node_module=spec.path.replace("/", "."),
                device=spec.config.get("device"),
                replicas=spec.config.get("replicas", 1),
                is_gateway=is_gateway,
                env_vars={
                    "REDIS_HOST": f"{REDIS_HOST}.{namespace}.svc.cluster.local",
                    "REDIS_PORT": str(REDIS_PORT),
                    "DATA_REDIS_HOST": f"{DATA_REDIS_HOST}.{namespace}.svc.cluster.local",
                    "DATA_REDIS_PORT": str(DATA_REDIS_PORT),
                    "GATEWAY_HOST": f"gateway-svc.{namespace}.svc.cluster.local",
                    "GATEWAY_TCP_PORT": str(GATEWAY_TCP_PORT),
                    "NODE_NAME": name
                }
            )
            
            manifest_path = manifest_dir / f"{name.replace('_', '-')}-deployment.yaml"
            manifest_path.write_text(yaml_str)
            print(f"  📄 Saved: {manifest_path}")
        
        return

    # Connect to K8s
    try:
        config.load_kube_config()
    except Exception:
        k3s_config = "/etc/rancher/k3s/k3s.yaml"
        if os.path.exists(k3s_config):
            print(f"📁 Using K3s config: {k3s_config}")
            config.load_kube_config(config_file=k3s_config)
        else:
            raise Exception("kubeconfig not found")
    
    k8s_apps = client.AppsV1Api()
    k8s_core = client.CoreV1Api()

    # Prepare namespace
    ensure_namespace(k8s_core, namespace)

    # Check infrastructure
    ensure_infrastructure(k8s_apps, k8s_core, system.broker, namespace)

    print(f"🚀 Deploying {len(system.specs)} nodes to namespace '{namespace}'...")

    # Deploy each node
    for name, spec in system.specs.items():
        image_tag = images.get(spec.path, "unknown")
        
        # Detect gateway type (will be determined at load time in new architecture)
        # For now, check config or path
        is_gateway = "gateway" in spec.path.lower() or spec.config.get("node_port") is not None

        yaml_str = dep_template.render(
            name=name.replace('_', '-'),
            image=image_tag,
            node_module=spec.path.replace("/", "."),
            device=spec.config.get("device"),
            replicas=spec.config.get("replicas", 1),
            is_gateway=is_gateway,
            env_vars={
                "REDIS_HOST": f"{REDIS_HOST}.{namespace}.svc.cluster.local",
                "REDIS_PORT": str(REDIS_PORT),
                "DATA_REDIS_HOST": f"{DATA_REDIS_HOST}.{namespace}.svc.cluster.local",
                "DATA_REDIS_PORT": str(DATA_REDIS_PORT),
                "GATEWAY_HOST": f"gateway-svc.{namespace}.svc.cluster.local",
                "GATEWAY_TCP_PORT": str(GATEWAY_TCP_PORT),
                "NODE_NAME": name,
                "EDGEFLOW_WIRING": json.dumps(system._resolve_wiring_config(name))
            }
        )
        manifest = yaml.safe_load(yaml_str)

        # Force restart with annotation
        if 'annotations' not in manifest['spec']['template']['metadata']:
            manifest['spec']['template']['metadata']['annotations'] = {}
        manifest['spec']['template']['metadata']['annotations']['kubectl.kubernetes.io/restartedAt'] = datetime.datetime.now().isoformat()

        try:
            k8s_apps.create_namespaced_deployment(namespace=namespace, body=manifest)
            print(f"  + [App] Created: {name}")
        except client.exceptions.ApiException as e:
            if e.status == 409:
                k8s_apps.patch_namespaced_deployment(
                    name=manifest['metadata']['name'], 
                    namespace=namespace, 
                    body=manifest
                )
                print(f"  * [App] Updated: {name} (Rolling Update)")
            else:
                raise e

        # Deploy Service for Gateway
        if is_gateway and has_svc_tpl:
            gateway_node_port = spec.config.get("node_port", 30000)
            
            svc_yaml = svc_template.render(
                name=name,
                port=GATEWAY_HTTP_PORT,
                tcp_port=GATEWAY_TCP_PORT,
                node_port=gateway_node_port
            )
            svc_manifest = yaml.safe_load(svc_yaml)
            
            try:
                k8s_core.create_namespaced_service(namespace=namespace, body=svc_manifest)
                print(f"  + [Svc] Exposed Gateway: http://<NODE-IP>:{gateway_node_port}")
            except client.exceptions.ApiException as e:
                if e.status == 409:
                    print(f"  🔄 Service exists. Re-creating...")
                    k8s_core.delete_namespaced_service(
                        name=svc_manifest['metadata']['name'], 
                        namespace=namespace
                    )
                    time.sleep(1)
                    k8s_core.create_namespaced_service(namespace=namespace, body=svc_manifest)
                    print(f"  + [Svc] Re-created: http://<NODE-IP>:{gateway_node_port}")
                elif e.status == 422:
                    print(f"  ❌ [Svc] Port Conflict: {gateway_node_port} is already in use by another service.")
                    print(f"     -> Change 'node_port' in {name}/node.toml or delete conflicting service.")
                else:
                    raise e

    print(f"✅ Deployment complete!")


def cleanup_namespace(namespace: str = "default"):
    """Delete all EdgeFlow deployments and services in namespace"""
    try:
        config.load_kube_config()
    except Exception:
        # Try k3s config location default
        k3s_config = "/etc/rancher/k3s/k3s.yaml"
        if os.path.exists(k3s_config):
            config.load_kube_config(config_file=k3s_config)
            
    k8s_apps = client.AppsV1Api()
    k8s_core = client.CoreV1Api()
    
    try:
        k8s_core.read_namespace(name=namespace)
    except client.exceptions.ApiException:
        print(f"⚠️ Namespace '{namespace}' does not exist.")
        return

    print(f"🧹 Clearing existing resources in '{namespace}'...")
    
    # Delete All Deployments
    deps = k8s_apps.list_namespaced_deployment(namespace)
    for d in deps.items:
        # Skip Redis infrastructure
        if 'redis' in d.metadata.name:
            continue
        k8s_apps.delete_namespaced_deployment(name=d.metadata.name, namespace=namespace)
        print(f"  - Deleted Deployment: {d.metadata.name}")
        
    # Delete All Services
    svcs = k8s_core.list_namespaced_service(namespace)
    for s in svcs.items:
        if 'redis' in s.metadata.name or s.metadata.name == 'kubernetes':
            continue
        k8s_core.delete_namespaced_service(name=s.metadata.name, namespace=namespace)
        print(f"  - Deleted Service: {s.metadata.name}")
    
    print("✅ Cleanup complete.")