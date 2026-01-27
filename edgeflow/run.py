import sys
import importlib
import inspect
import os
from edgeflow.nodes import EdgeNode

def run_node(module_name):
    # 1. Import module
    try:
        mod = importlib.import_module(module_name)
    except ImportError as e:
        print(f"❌ Could not import module '{module_name}': {e}")
        sys.exit(1)

    # 2. Find EdgeNode subclass
    node_class = None
    for name, obj in inspect.getmembers(mod):
        if inspect.isclass(obj) and issubclass(obj, EdgeNode) and obj is not EdgeNode:
            # Only pick class defined in this module (ignore imported base classes)
            if obj.__module__ == mod.__name__:
                node_class = obj
                break
    
    if not node_class:
        print(f"❌ No EdgeNode subclass found in '{module_name}'")
        print(f"   (Did you inherit from ProducerNode, ConsumerNode, etc.?)")
        sys.exit(1)

    # 3. Instantiate and Run
    print(f"🚀 Running Node: {node_class.__name__}")
    
    # Note: EdgeNode.__init__ will create default RedisBroker if broker is None.
    try:
        node = node_class()
        node.execute()
    except Exception as e:
        print(f"❌ Node Execution Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m edgeflow.run <module_path>")
        sys.exit(1)
    
    # Add /app to sys.path to find nodes package
    sys.path.append("/app")
    
    run_node(sys.argv[1])
