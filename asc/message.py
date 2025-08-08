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
    
    def format(self, prev_message: Optional['Message'] = None, nicknames: set[str] = set(), verbose: bool = False) -> str:
        """Format the message with the previous message"""
        msg = self.text
        context = f"\n{self.nickname} said:\n"

        if verbose:
            timestamp = f"\n{self.timestamp}"
        else:
            timestamp = ""

        if prev_message and prev_message.nickname == self.nickname:
            context = ""
            timestamp = ""

        # Check if this is a reply to someone
        replied = None
        for nickname in nicknames:
            if msg.startswith(nickname):
                msg = msg[len(nickname):].strip()
                replied = nickname
                if msg.startswith(":"):
                    msg = msg[1:].strip()
                break

        if replied:
            context = f"\n{self.nickname} replied to {replied}:\n"
        return f"{timestamp}{context}{msg}"
    
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

def parse_message_from_tr(tr_element) -> Optional[Message]:
    """Parse a Message from a BeautifulSoup <tr> element
    
    Args:
        tr_element: BeautifulSoup <tr> element from IRC log table
        
    Returns:
        Message instance if parsing successful, None otherwise
    """
    # Get timestamp from tr id attribute
    timestamp_str = tr_element.get('id')
    if not timestamp_str:
        return None
    # Parse timestamp (assuming format like "t2024-01-15T14:30:25")
    if timestamp_str.startswith('t'):
        timestamp_str = timestamp_str[1:20]  # Remove 't' prefix and anything after seconds
    timestamp = datetime.datetime.fromisoformat(timestamp_str)
    
    # Get nickname from td with class="nick"
    nick_td = tr_element.find('th', class_='nick')
    if not nick_td:
        return None
    nickname = nick_td.get_text(strip=True)

    # Get message from td with class="text"
    message_td = tr_element.find('td', class_='text')
    if not message_td:
        return None
    text = message_td.get_text(strip=True)
    
    return Message(timestamp, nickname, text)
        