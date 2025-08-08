import datetime
from typing import Optional


class Message:
    """Represents a single IRC message with timestamp, nickname, and content"""
    
    def __init__(self, timestamp: datetime.datetime, nickname: str, text: str):
        """Initialize a Message instance
        
        Args:
            timestamp: When the message was sent
            nickname: IRC nickname of the sender
            text: The message content
        """
        self.timestamp = timestamp
        self.nickname = nickname
        self.text = text
    
    
    def __str__(self) -> str:
        """String representation of the message"""
        return f"[{self.timestamp}] <{self.nickname}> {self.text}"
    
    def __repr__(self) -> str:
        """Developer representation of the message"""
        return f"Message(timestamp={self.timestamp!r}, nickname={self.nickname!r}, text={self.text!r})"
    
    def __eq__(self, other) -> bool:
        """Check equality with another Message"""
        if not isinstance(other, Message):
            return False
        return (
            self.timestamp == other.timestamp
            and self.nickname == other.nickname
            and self.text == other.text
        )
