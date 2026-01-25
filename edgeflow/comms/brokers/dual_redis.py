# edgeflow/comms/brokers/dual_redis.py
"""
Dual Redis Stream-based Broker
- Control Redis: Stream for message ordering
- Data Redis: Blob storage for large payloads
"""
import redis.exceptions
import struct
import time
import os
from typing import Dict
from .base import BrokerInterface
from ...config import settings


class DualRedisBroker(BrokerInterface):
    """
    Dual Redis Stream Broker:
    - ctrl_redis: Lightweight stream (message IDs)
    - data_redis: Heavy data storage (actual frames)
    """
    
    
    def __init__(self, ctrl_host=None, ctrl_port=None, 
                       data_host=None, data_port=None, maxlen=100):
        
        ctrl_host = ctrl_host or settings.REDIS_HOST
        ctrl_port = ctrl_port or settings.REDIS_PORT
        data_host = data_host or settings.DATA_REDIS_HOST
        data_port = data_port or settings.DATA_REDIS_PORT

        self.maxlen = maxlen
        self.ctrl_redis = redis.Redis(host=ctrl_host, port=ctrl_port)
        self.data_redis = self._connect_data_redis(data_host, data_port, ctrl_port)
        self._consumer_groups = set()

    def reset(self):
        """
        Reset Broker State (FLUSHALL)
        - Called ONLY by the main system process on startup
        """
        try:
            self.ctrl_redis.flushall()
            if self.ctrl_redis != self.data_redis:
                self.data_redis.flushall()
            print("🧹 [DualRedis] System Reset: FLUSHALL executed")
        except Exception as e:
            print(f"⚠️ [DualRedis] Failed to reset: {e}")

    def _connect_data_redis(self, host, port, fallback_port):
        r = redis.Redis(host=host, port=port, socket_connect_timeout=0.5)
        
        if host not in ("localhost", "127.0.0.1"):
            return r

        try:
            r.ping()
            return r
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
            print(f"⚠️ [DualRedis] Failed to connect to Data Redis at {host}:{port}.")
            print(f"🔄 [DualRedis] Falling back to Control Redis port ({fallback_port}) for local testing.")
            return redis.Redis(host=host, port=fallback_port)

    def _ensure_consumer_group(self, stream: str, group: str):
        """Create consumer group if not exists"""
        key = f"{stream}:{group}"
        if key in self._consumer_groups:
            return
        
        try:
            # Start from 0 to read all existing messages (important for late joiners)
            self.ctrl_redis.xgroup_create(stream, group, id='0', mkstream=True)
            self._consumer_groups.add(key)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                self._consumer_groups.add(key)
            else:
                raise

    def push(self, topic, frame_bytes):
        """
        Store data in Data Redis, push ID to Control Redis Stream
        """
        if len(frame_bytes) < 4:
            return

        # Extract frame_id from header
        frame_id = struct.unpack('!I', frame_bytes[:4])[0]
        
        # 1. [Data Plane] Store heavy data
        data_key = f"{topic}:data:{frame_id}"
        self.data_redis.set(data_key, frame_bytes, ex=60)  # 60s TTL for slow consumers
        
        # 2. [Control Plane] Add frame_id to stream
        self.ctrl_redis.xadd(
            topic, 
            {'frame_id': str(frame_id)}, 
            maxlen=self.maxlen, 
            approximate=True
        )

    def pop(self, topic, timeout=1, group="default", consumer="worker"):
        """
        Read frame_id from stream, fetch data from Data Redis
        """
        self._ensure_consumer_group(topic, group)
        
        try:
            result = self.ctrl_redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={topic: '>'},
                count=1,
                block=int(timeout * 1000)
            )
            
            if not result:
                return None
            
            stream_name, messages = result[0]
            if not messages:
                return None
            
            msg_id, fields = messages[0]
            frame_id = fields.get(b'frame_id', b'').decode('utf-8')
            
            # Acknowledge message
            self.ctrl_redis.xack(topic, group, msg_id)
            
            # Fetch actual data
            data_key = f"{topic}:data:{frame_id}"
            raw_data = self.data_redis.get(data_key)
            
            if raw_data:
                return raw_data
            else:
                # Data expired or missing
                return None
                
        except Exception as e:
            print(f"DualRedis Pop Error: {e}")
            return None

    def pop_latest(self, topic, timeout=1):
        """
        Read the LATEST message only (REALTIME mode).
        Skips all older messages - best for real-time processing.
        """
        try:
            # Get the latest entry from stream
            entries = self.ctrl_redis.xrevrange(topic, count=1)
            if not entries:
                # No entries, wait for new one
                import time
                time.sleep(timeout)
                entries = self.ctrl_redis.xrevrange(topic, count=1)
                if not entries:
                    return None
            
            msg_id, fields = entries[0]
            frame_id = fields.get(b'frame_id', b'').decode('utf-8')
            
            # Fetch actual data
            data_key = f"{topic}:data:{frame_id}"
            raw_data = self.data_redis.get(data_key)
            
            return raw_data if raw_data else None
            
        except Exception as e:
            print(f"DualRedis PopLatest Error: {e}")
            return None

    def trim(self, topic, size):
        """Trim stream (for backward compatibility)"""
        try:
            self.ctrl_redis.xtrim(topic, maxlen=size, approximate=True)
            self.ctrl_redis.set(f"edgeflow:meta:limit:{topic}", size)
        except Exception:
            pass

    def queue_size(self, topic: str) -> int:
        """Return stream length"""
        try:
            return self.ctrl_redis.xlen(topic)
        except Exception:
            return 0

    def get_queue_stats(self) -> Dict[str, Dict[str, int]]:
        """Return stats for all tracked streams"""
        stats = {}
        try:
            meta_keys = self.ctrl_redis.keys("edgeflow:meta:limit:*")
            
            for key in meta_keys:
                key_str = key.decode('utf-8')
                topic = key_str.replace("edgeflow:meta:limit:", "")
                
                limit_bytes = self.ctrl_redis.get(key)
                limit = int(limit_bytes) if limit_bytes else self.maxlen
                current = self.ctrl_redis.xlen(topic)
                
                stats[topic] = {"current": current, "max": limit}
        except Exception as e:
            print(f"DualRedis Stats Error: {e}")
        return stats

    # ========== Serialization Protocol ==========
    
    def to_config(self) -> dict:
        return {
            "__class_path__": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "ctrl_host": self.ctrl_redis.connection_pool.connection_kwargs.get('host'),
            "ctrl_port": self.ctrl_redis.connection_pool.connection_kwargs.get('port'),
            "data_host": self.data_redis.connection_pool.connection_kwargs.get('host'),
            "data_port": self.data_redis.connection_pool.connection_kwargs.get('port'),
            "maxlen": self.maxlen
        }
    
    @classmethod
    def from_config(cls, config: dict) -> 'DualRedisBroker':
        return cls(
            ctrl_host=config.get("ctrl_host"),
            ctrl_port=config.get("ctrl_port"),
            data_host=config.get("data_host"),
            data_port=config.get("data_port"),
            maxlen=config.get("maxlen", 100)
        )