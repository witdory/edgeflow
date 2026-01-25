# edgeflow/qos.py
"""
Quality of Service policies for stream consumption
"""
from enum import Enum, auto


class QoS(Enum):
    """Quality of Service for link consumption"""
    
    REALTIME = auto()
    """
    Real-time consumption: Skip to latest message if behind.
    - Best for: AI inference, live video processing
    - Behavior: Uses XREAD $ (no consumer group, latest only)
    - Trade-off: May skip messages if consumer is slow
    """
    
    DURABLE = auto()
    """
    Durable consumption: Read all messages sequentially.
    - Best for: Logging, database writes, analytics
    - Behavior: Uses XREADGROUP (tracked consumer group)
    - Trade-off: May lag behind if consumer is slow
    """
    
    BALANCED = auto()
    """
    Balanced consumption: Skip if too far behind, otherwise sequential.
    - Best for: Moderate latency tolerance with some reliability
    - Behavior: XREADGROUP with skip threshold
    - Trade-off: Configurable lag tolerance
    """
