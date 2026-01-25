#edgeflow/comms/brokers/redis.py
"""
Redis Stream-based Broker for fan-out and consumer group support
"""
import redis
import time
import os
from typing import Dict, Optional
from .base import BrokerInterface


class RedisBroker(BrokerInterface):
    """Redis Stream-based message broker"""
    
    def __init__(self, host=None, port=None, maxlen=100):
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.maxlen = maxlen  # Stream max length (approximate)
        self._redis = None
        self._consumer_groups = set()  # Track created groups
        self._topic_last_id = {}  # Track last seen ID per topic

    def _ensure_connected(self):
        if self._redis is None:
            self._redis = self._connect()
    
    def _connect(self):
        wait_time = 1
        while True:
            try:
                r = redis.Redis(host=self.host, port=self.port, socket_timeout=5)
                r.ping()
                print(f"✅ Redis Connected: {self.host}:{self.port}")
                return r
            except redis.ConnectionError:
                print(f"⚠️ Redis Connection Failed ({self.host}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 30)

    def _ensure_consumer_group(self, stream: str, group: str):
        """Create consumer group if not exists"""
        key = f"{stream}:{group}"
        if key in self._consumer_groups:
            return
        
        self._ensure_connected()
        try:
            # Start from 0 to read all existing messages (important for late joiners)
            self._redis.xgroup_create(stream, group, id='0', mkstream=True)
            self._consumer_groups.add(key)
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists
                self._consumer_groups.add(key)
            else:
                raise

    def push(self, topic: str, data: bytes):
        """Add message to stream (XADD with MAXLEN)"""
        if not data:
            return
        self._ensure_connected()
        try:
            # XADD with approximate maxlen for auto-trimming
            self._redis.xadd(topic, {'data': data}, maxlen=self.maxlen, approximate=True)
        except Exception as e:
            print(f"Redis Push Error: {e}")

    def pop(self, topic: str, timeout: int = 1, group: str = "default", consumer: str = "worker"):
        """
        Read message from stream using consumer group (XREADGROUP)
        - group: consumer group name (e.g., node name)
        - consumer: consumer instance name (e.g., replica id)
        """
        self._ensure_connected()
        self._ensure_consumer_group(topic, group)
        
        try:
            # XREADGROUP: read new messages for this group
            # '>' means only new messages not yet delivered
            result = self._redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={topic: '>'},
                count=1,
                block=timeout * 1000  # milliseconds
            )
            
            if not result:
                return None
            
            # result format: [(stream_name, [(msg_id, {field: value})])]
            stream_name, messages = result[0]
            if not messages:
                return None
            
            msg_id, fields = messages[0]
            data = fields.get(b'data')
            
            # Auto-acknowledge the message
            self._redis.xack(topic, group, msg_id)
            
            return data
            
        except Exception as e:
            print(f"Redis Pop Error: {e}")
            return None

    def trim(self, topic: str, size: int = 1):
        """Trim stream to approximate size (for backward compatibility)"""
        self._ensure_connected()
        try:
            self._redis.xtrim(topic, maxlen=size, approximate=True)
            self._redis.set(f"edgeflow:meta:limit:{topic}", size)
        except Exception:
            pass

    def queue_size(self, topic: str) -> int:
        """Return stream length"""
        self._ensure_connected()
        try:
            return self._redis.xlen(topic)
        except Exception:
            return 0

    def get_queue_stats(self) -> Dict[str, Dict[str, int]]:
        """Return stats for all tracked streams"""
        self._ensure_connected()
        stats = {}
        try:
            meta_keys = self._redis.keys("edgeflow:meta:limit:*")
            
            for key in meta_keys:
                key_str = key.decode('utf-8')
                topic = key_str.replace("edgeflow:meta:limit:", "")
                
                limit_bytes = self._redis.get(key)
                limit = int(limit_bytes) if limit_bytes else self.maxlen
                current = self._redis.xlen(topic)
                
                stats[topic] = {"current": current, "max": limit}
        except Exception as e:
            print(f"Redis Stats Error: {e}")
        return stats


    def pop_latest(self, topic: str, timeout: int = 1) -> Optional[bytes]:
        """
        Read the LATEST UNIQUE message (REALTIME mode).
        - Dedplicates frames: Returns None if no NEW frame exists
        - Efficient waiting: Blocks until new data arrives
        """
        self._ensure_connected()
        try:
            start_time = time.time()
            
            while True:
                # 1. Get current tip
                entries = self._redis.xrevrange(topic, count=1)
                
                if entries:
                    msg_id, fields = entries[0]
                    last_seen = self._topic_last_id.get(topic)
                    
                    if msg_id != last_seen:
                        # New frame found!
                        self._topic_last_id[topic] = msg_id
                        data = fields.get(b'data')
                        return data
                
                # Check timeout
                elapsed = time.time() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    return None
                
                # 2. Wait for NEW data using XREAD with '$'
                try:
                    block_ms = int(remaining * 1000)
                    self._redis.xread({topic: '$'}, count=1, block=block_ms)
                except redis.exceptions.ResponseError:
                    time.sleep(0.1)
            
        except Exception as e:
            print(f"Redis PopLatest Error: {e}")
            return None

    # ========== Serialization Protocol ==========
    
    def to_config(self) -> dict:
        return {
            "__class_path__": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "host": self.host,
            "port": self.port,
            "maxlen": self.maxlen
        }
    
    @classmethod
    def from_config(cls, config: dict) -> 'RedisBroker':
        return cls(
            host=config.get("host"),
            port=config.get("port"),
            maxlen=config.get("maxlen", 100)
        )