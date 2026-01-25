# examples/my-robot/nodes/logger/__init__.py
"""
Example Logger SinkNode - Logs incoming frames to console/file
"""
from edgeflow.nodes import SinkNode


class LoggerNode(SinkNode):
    """Simple logging sink - no output"""
    
    def setup(self):
        print(f"📝 [Logger] Initialized on host: {self.hostname}")
        self.frame_count = 0
    
    def loop(self, data):
        """Log incoming frame metadata"""
        self.frame_count += 1
        if self.frame_count % 30 == 0:  # Log every 30 frames
            print(f"📝 [Logger] Received {self.frame_count} frames")
