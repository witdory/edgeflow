import argparse
from .cli.inspector import inspect_app
from .cli.builder import build_and_push
from .cli.deployer import deploy_to_k8s

def main():
    parser = argparse.ArgumentParser(description="EdgeFlow CLI")
    subparsers = parser.add_subparsers(dest="command")

    # deploy 명령어
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("file", help="Path to main.py")
    deploy.add_argument("--registry", default="localhost:5000", help="Docker Registry")

    args = parser.parse_args()

    if args.command == "deploy":
        print(f"🔍 Inspecting {args.file}...")
        app = inspect_app(args.file)
        
        image_tag = f"{args.registry}/edgeflow-app:latest"
        
        print(f"🐳 Building & Pushing Image ({image_tag})...")
        build_and_push(image_tag)
        
        print(f"🚀 Deploying to Kubernetes...")
        deploy_to_k8s(app, image_tag)
        print("✅ Done!")

if __name__ == "__main__":
    main()