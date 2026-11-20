from dataclasses import dataclass
from typing import Literal


"""
@dataclass automatically generates essential methods, such as a constructor.

frozen=True prevents the fields of an object from being modified after initialization.

slots=True helps optimize memory usage.

str | None indicates that a field can be either a string or None.

Literal specifies the expected, permitted values.
"""

@dataclass(frozen = True, slots = True)
class SourceChunk:
    chunk_id : str
    source_type : Literal["code","documentation"]
    file_path : str
    content : str
    start_line : int
    end_line : int
    class_name : str | None = None
    method_name : str | None = None
    
    
    def __post_init__(self) -> None:
        
        if not self.chunk_id.strip():
            raise ValueError("chunk_id cannot be empty")
        
        if self.source_type not in ("code","documentation"):
            raise ValueError("Invalid source_type")
        
        if not self.file_path.strip():
            raise ValueError("file_path cannot be empty")
            
        if not self.content.strip():
            raise ValueError("content cannot be empty")
        
        if self.start_line < 1:
            raise ValueError("start_line must be positive")
        
        if self.end_line < self.start_line:
            raise ValueError("end_line cannot be smaller than start_line")
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            