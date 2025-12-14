#edgeflow/cli.py
import typer
import subprocess
import os
import sys
import importlib.util
from jinja2 import Environment, FileSystemLoader

app = typer.Typer()

def load_user_app():
    """현재 경로의 main.py에서 app 객체를 로드"""
    try:
        spec = importlib.util.spec_from_file_location("user_main", "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    except Exception as e:
        print(f"❌ main.py를 찾을 수 없거나 에러가 있습니다: {e}")
        sys.exit(1)

@app.command()
def deploy(image: str):
    """
    EdgeFlow Deploy Tool
    사용법: edgeflow deploy --image my-repo/my-image:v1
    """
    user_app = load_user_app()
    
    # 1. Docker Build & Push
    print(f"🔨 Docker 이미지 빌드 및 푸시: {image}")
    
    # 템플릿 로더 설정
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Dockerfile 생성
    with open("Dockerfile", "w") as f:
        f.write(env.get_template("Dockerfile.j2").render())
        
    subprocess.run(f"docker build -t {image} .", shell=True, check=True)
    subprocess.run(f"docker push {image}", shell=True, check=True)
    
    # 2. YAML 생성 및 배포
    roles = ["producer", "consumer", "gateway"]
    
    for role in roles:
        print(f"📄 {role} 배포 중...")
        template = env.get_template(f"{role}.yaml.j2")
        
        replicas = user_app.replicas if role == "consumer" else 1
        
        yaml_content = template.render(
            image=image,
            replicas=replicas
        )
        
        filename = f"k8s_{role}.yaml"
        with open(filename, "w") as f:
            f.write(yaml_content)
            
        subprocess.run(f"kubectl apply -f {filename}", shell=True)
        
    print("✅ 모든 배포가 완료되었습니다!")

if __name__ == "__main__":
    app()