# edgeflow/__main__.py
import argparse
import sys
from .cli.inspector import inspect_app
from .cli.deployer import deploy_to_k8s
from .cli.manager import add_dependency, show_logs

def main():
    parser = argparse.ArgumentParser(description="EdgeFlow CLI v0.2.0")
    subparsers = parser.add_subparsers(dest="command")

    # ==========================
    # 1. DEPLOY Command
    # ==========================
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("file", help="Path to main.py")
    deploy.add_argument("--registry", default="localhost:5000", help="Docker Registry")
    deploy.add_argument("--namespace", default="edgeflow", help="K8s Namespace")
    deploy.add_argument("--dry-run", action="store_true", help="Only generate manifests, don't apply")
    deploy.add_argument("--no-build", action="store_false", dest="build", help="Skip building images")
    deploy.set_defaults(build=True)

    # ==========================
    # 2. ADD Command (Package)
    # ==========================
    add = subparsers.add_parser("add", help="Add dependency to node.toml")
    add.add_argument("package", help="Package Name (e.g. numpy)")
    add.add_argument("--node", help="Path to node folder (e.g. nodes/camera)")

    # ==========================
    # 3. LOGS Command
    # ==========================
    logs = subparsers.add_parser("logs", help="View node logs from K8s")
    logs.add_argument("node", help="Node Name (e.g. camera)")
    logs.add_argument("--namespace", "-n", default="edgeflow", help="K8s Namespace")

    args = parser.parse_args()

    # Dispatch Commands
    if args.command == "deploy":
        _handle_deploy(args)
    elif args.command == "add":
        add_dependency(args.package, args.node)
    elif args.command == "logs":
        show_logs(args.node, args.namespace)
    else:
        parser.print_help()


def _handle_deploy(args):
    print(f"🔍 Inspecting {args.file}...")
    try:
        system = inspect_app(args.file)
    except Exception as e:
        print(f"❌ Error loading app: {e}")
        sys.exit(1)
    
    print(f"🚀 Deploying System: {system.name} (Namespace: {args.namespace})")
    
    try:
        deploy_to_k8s(
            system=system,
            registry=args.registry,
            namespace=args.namespace,
            build=args.build,
            push=args.build,
            dry_run=args.dry_run
        )
        
        if args.dry_run:
            print("✅ Dry-run complete. Manifests saved in .build/ manifests")
        else:
            print("✅ Deployment complete!")
            
    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()