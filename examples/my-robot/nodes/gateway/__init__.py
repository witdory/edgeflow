# examples/my-robot/nodes/gateway/__init__.py
"""Gateway node - GatewayNode example (Arduino Pattern)"""

from edgeflow.nodes import GatewayNode
from edgeflow.nodes.gateway.interfaces.web import WebInterface
from edgeflow.config import settings


class VideoGateway(GatewayNode):
    """Web streaming gateway"""
    
    def setup(self):
        """한 번만 실행: 인터페이스 등록"""
        web = WebInterface(port=settings.GATEWAY_HTTP_PORT, buffer_delay=0.5)
        self.add_interface(web)
