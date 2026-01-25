# edgeflow/registry.py
"""
Global NodeSpec Registry for multi-System node sharing
"""
from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class NodeSpec:
    """Metadata holder for lazy node loading (Blueprint Pattern)"""
    path: str                          # e.g., "nodes/camera"
    config: Dict[str, Any] = field(default_factory=dict)
    name: str = ""
    
    def __post_init__(self):
        if not self.name:
            self.name = self.path.replace("/", "_").replace("nodes_", "")


class NodeRegistry:
    """Global registry for NodeSpecs, enabling cross-System sharing"""
    _specs: Dict[str, NodeSpec] = {}
    
    @classmethod
    def get_or_create(cls, path: str, **config) -> NodeSpec:
        """Get existing NodeSpec or create new one"""
        if path in cls._specs:
            # Merge config if existing
            existing = cls._specs[path]
            existing.config.update(config)
            return existing
        
        spec = NodeSpec(path=path, config=config)
        cls._specs[path] = spec
        return spec
    
    @classmethod
    def get(cls, path: str) -> NodeSpec:
        """Get existing NodeSpec by path"""
        return cls._specs.get(path)
    
    @classmethod
    def all_specs(cls) -> Dict[str, NodeSpec]:
        """Return all registered specs"""
        return cls._specs.copy()
    
    @classmethod
    def clear(cls):
        """Clear registry (for testing)"""
        cls._specs = {}
