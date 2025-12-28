import sys
import argparse

class EdgeApp:
    def __init__(self, name="edgeflow-app"):
        self.name = name
        self.nodes = {} # 등록된 노드 저장소

    def node(self, name, type, **kwargs):
        """[변경] 데코레이터가 이제 클래스를 등록합니다."""
        def decorator(cls):
            self.nodes[name] = {"cls": cls, "type": type, "kwargs": kwargs}
            return cls
        return decorator

    def run(self):
        # CLI 인자 파싱 (예: python main.py --node camera)
        parser = argparse.ArgumentParser()
        parser.add_argument("--node", help="Name of the node to run")
        args = parser.parse_args()

        target = args.node
        # 인자 없으면 첫 번째 인자를 타겟으로 (호환성 유지)
        if not target and len(sys.argv) > 1:
            if not sys.argv[1].startswith("-"): # --flag가 아니면
                target = sys.argv[1]

        if target in self.nodes:
            info = self.nodes[target]
            print(f"▶️ Launching {target} ({info['type']})...")
            
            # 클래스 인스턴스화 및 실행
            # kwargs로 fps 등을 넘김
            instance = info["cls"](**info["kwargs"])
            instance.execute()
        else:
            print(f"Usage: python main.py --node [name]")
            print(f"Available Nodes: {list(self.nodes.keys())}")