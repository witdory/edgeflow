#edgeflow/cli/inspector.py
import importlib.util
import sys
import os

def inspect_app(file_path):
    # main.py 경로를 절대 경로로 변환
    file_path = os.path.abspath(file_path)
    dir_name = os.path.dirname(file_path)
    sys.path.insert(0, dir_name) # import 가능하게 경로 추가

    module_name = os.path.basename(file_path).replace(".py", "")
    
    # 동적 임포트
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # app 객체 찾기
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        # 클래스 이름 체크 등으로 EdgeApp 인스턴스인지 확인
        if hasattr(attr, 'nodes') and hasattr(attr, 'run'):
            return attr
            
    raise ValueError("Could not find 'app' instance in main.py")