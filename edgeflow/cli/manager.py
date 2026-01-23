# edgeflow/cli/manager.py
"""CLI Manager for managing project dependencies and logs"""

import os
import re
import sys
import subprocess
from pathlib import Path


def add_dependency(package: str, node_path: str = None):
    """
    Add a python package to node.toml dependencies.
    If node_path is None, try to find node.toml in current dir or ask user.
    """
    target_file = None
    
    # 1. 경로 자동 추론
    if node_path:
        # 명시적 경로 (예: "nodes/camera")
        path = Path(node_path)
        if path.is_file() and path.name == "node.toml":
            target_file = path
        elif path.is_dir():
            target_file = path / "node.toml"
    else:
        # 현재 디렉토리
        cwd = Path.cwd()
        if (cwd / "node.toml").exists():
            target_file = cwd / "node.toml"
    
    if not target_file or not target_file.exists():
        print(f"❌ Error: Could not find node.toml in '{node_path or 'current directory'}'")
        print("Usage: edgeflow add <package> --node nodes/camera")
        sys.exit(1)

    # 2. 파일 읽기
    content = target_file.read_text(encoding="utf-8")
    
    # 3. 의존성 추가 (Regex 활용)
    # dependencies = ["numpy", "opencv-python"] 패턴 찾기
    dep_pattern = r'(dependencies\s*=\s*\[)(.*?)(\])'
    
    match = re.search(dep_pattern, content, re.DOTALL)
    if match:
        prefix, current_deps, suffix = match.groups()
        
        # 이미 존재하는지 확인
        if f'"{package}"' in current_deps or f"'{package}'" in current_deps:
            print(f"⚠️ Package '{package}' is already in {target_file}")
            return

        # 리스트 끝에 추가
        # 마지막 요소 뒤에 콤마가 있는지 확인하고 처리
        clean_deps = current_deps.strip()
        new_dep = f', "{package}"' if clean_deps and not clean_deps.endswith(',') else f'"{package}"'
        if not clean_deps:
            new_dep = f'"{package}"'
            
        new_content = content.replace(
            match.group(0), 
            f'{prefix}{current_deps}{new_dep}{suffix}'
        )
    else:
        # dependencies 키가 없는 경우 [build] 섹션 아래 추가 필요
        # (간단하게 구현하기 위해 이건 사용자가 직접 포맷을 맞췄다고 가정하거나, [build] 섹션을 찾아 추가)
        print(f"❌ Error: 'dependencies = []' list not found in [build] section.")
        print("Please ensure node.toml has a valid format.")
        sys.exit(1)

    # 4. 저장
    target_file.write_text(new_content, encoding="utf-8")
    print(f"✅ Added '{package}' to {target_file}")


def show_logs(node_name: str, namespace: str = "edgeflow", follow: bool = True):
    """
    Wrapper for kubectl logs
    """
    print(f"🔍 Fetching logs for node '{node_name}' in namespace '{namespace}'...")
    
    cmd = [
        "kubectl", "logs", 
        f"-lapp={node_name}",  # Label selector
        "-n", namespace,
        "--all-containers=true",
        "--prefix=true"
    ]
    
    if follow:
        cmd.append("-f")
        
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 Log stream stopped.")
    except FileNotFoundError:
        print("❌ Error: 'kubectl' not found. Please install Kubernetes CLI.")
