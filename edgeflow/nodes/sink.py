# edgeflow/nodes/sink.py
"""
SinkNode - Terminal consumer with no output (logging, DB, S3 upload, etc.)

Arduino Pattern:
- setup(): Initialization (DB connection, file handle, etc.)
- loop(data): Process data (no return value, no downstream)
"""
from .consumer import ConsumerNode
from ..comms import Frame
from ..qos import QoS


class SinkNode(ConsumerNode):
    """Terminal node that consumes data without producing output (always DURABLE)"""
    node_type = "sink"
    
    def __init__(self, broker, **kwargs):
        super().__init__(broker=broker, replicas=1, **kwargs)
        self.output_handlers = []  # Explicitly no outputs
    
    def loop(self, data):
        """
        [User Hook] Process incoming data (no return value)
        - data: Upstream image/data
        - No return value (terminal node)
        """
        raise NotImplementedError("SinkNode requires loop(data) implementation")
    
    def _run_loop(self):
        """[Internal] Consume from stream with DURABLE mode (read all messages)"""
        if not self.input_topics:
            print(f"⚠️ No input topics for {self.name}")
            return
        
        first_input = self.input_topics[0]
        if isinstance(first_input, dict):
            target_topic = first_input['topic']
        else:
            target_topic = first_input
        
        # SinkNode always uses DURABLE (consumer group, sequential reading)
        group_name = getattr(self, 'name', 'sink')
        consumer_id = self.hostname
        
        print(f"📥 Sink started (QoS: DURABLE), Input: {target_topic}, Group: {group_name}")

        while self.running:
            # Always use sequential reading for logging/durable use cases
            packet = self.broker.pop(target_topic, timeout=1, group=group_name, consumer=consumer_id)
            if not packet:
                continue

            frame = Frame.from_bytes(packet)
            if not frame:
                continue

            try:
                self.loop(frame.data)
            except Exception as e:
                print(f"⚠️ Sink Error: {e}")
