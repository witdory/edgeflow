#edgeflow/nodes/base.py
"""
Arduino-style Node Base Class
- setup(): 한 번만 실행되는 초기화 로직
- loop(): 반복 실행되는 메인 로직
"""
from abc import ABC, abstractmethod
import os
from ..comms import RedisBroker


class EdgeNode(ABC):
    """
    Base class for all edge nodes.
    
    Arduino Pattern:
    - setup(): Called once at startup (user override)
    - loop(): Called repeatedly (user override)
    """
    node_type = "generic"
    
    def __init__(self, broker=None, **kwargs):
        self.running = True
        self.__dict__.update(kwargs)
        if not hasattr(self, 'name'):
            self.name = self.__class__.__name__
        self.hostname = os.getenv("HOSTNAME", "localhost")
        host = os.getenv("REDIS_HOST", "localhost")
        self.broker = broker

        # I/O protocol and handlers
        self.input_protocol = "redis"
        self.input_topics = []
        self.output_handlers = []

        if not self.broker:
            self.broker = RedisBroker(host)
            
        # K8s Wiring Injection
        wiring_json = os.getenv("EDGEFLOW_WIRING")
        if wiring_json:
            import json
            try:
                wiring_data = json.loads(wiring_json)
                self._apply_wiring(wiring_data)
                print(f"🔌 [Wiring] Applied configuration from Environment")
            except Exception as e:
                print(f"⚠️ Failed to apply wiring env: {e}")

    def send_result(self, frame):
        """연결된 모든 핸들러에게 데이터 전송"""
        if not frame:
            return
        for handler in self.output_handlers:
            handler.send(frame)

    def _apply_wiring(self, wiring):
        """Apply wiring config from JSON (K8s Env Injection)"""
        from ..handlers import RedisHandler, TcpHandler
        from ..qos import QoS
        from ..config import settings
        
        # Inputs
        for inp in wiring.get('inputs', []):
            topic = inp['topic'] if isinstance(inp, dict) else inp
            qos_val = inp.get('qos', QoS.REALTIME) if isinstance(inp, dict) else QoS.REALTIME
            # QoS Enum restoration (if integer/string from JSON)
            if isinstance(qos_val, int): qos_val = QoS(qos_val)
            
            self.input_topics.append({'topic': topic, 'qos': qos_val})
                
        # Outputs
        redis_topics = set()
        for out in wiring.get('outputs', []):
            if out['protocol'] == 'tcp':
                source_id = out['channel'] if out['channel'] else self.name
                gw_host = settings.GATEWAY_HOST
                gw_port = settings.GATEWAY_TCP_PORT
                handler = TcpHandler(gw_host, gw_port, source_id)
                self.output_handlers.append(handler)
                print(f"🔗 [Direct] {self.name} ==(TCP)==> {out['target']}")
            else:
                topic = self.name
                if topic not in redis_topics:
                    handler = RedisHandler(self.broker, topic, queue_size=out['queue_size'])
                    self.output_handlers.append(handler)
                    redis_topics.add(topic)
                # print log...

    def execute(self):
        """노드 실행 전체 흐름 제어 (Template Method)"""
        self._setup()
        try:
            self._run_loop()
        except KeyboardInterrupt:
            print(f"🛑 {self.__class__.__name__} Stopped.")
        finally:
            self.teardown()

    def _setup(self):
        """[Internal] 프레임워크 초기화 + 사용자 setup() 호출"""
        self.setup()

    def setup(self):
        """[User Hook] 한 번만 실행되는 초기화 로직 (Arduino setup)"""
        pass

    @abstractmethod
    def _run_loop(self):
        """[Internal] 서브클래스에서 loop() 호출 방식 정의"""
        pass

    def loop(self):
        """[User Hook] 반복 실행되는 메인 로직 (Arduino loop)"""
        raise NotImplementedError("Subclass must implement loop()")

    def teardown(self):
        """[User Hook] 종료 시 정리 로직"""
        pass