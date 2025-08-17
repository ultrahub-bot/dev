# models.py
class UserInfo:
    """Class to hold user information with attributes that can be dynamically set"""
    def __init__(self, **kwargs):
        # Initialize default attributes with None
        self.id:                    int = None
        self.name:                  str = None
        self.admin:                 int = None
        self.discord_id:            int = None
        self.discord_username:      str = None
        self.discord_mention:       str = None
        self.discord_isbot:         int = None
        self.discord_createdat:     str = None
        self.aqw_id:                int = None
        self.aqw_username:          str = None
        
        # Override defaults with any provided keyword arguments
        for key, value in kwargs.items():
            setattr(self, key, value)

class BossInfo:
    """Class to hold user information with attributes that can be dynamically set"""
    def __init__(self, **kwargs):
        # Initialize default attributes with None
        self.id:                    int = None
        self.name:                  str = None
        self.admin:                 int = None
        self.discord_id:            int = None
        self.discord_username:      str = None
        self.discord_mention:       str = None
        self.discord_isbot:         int = None
        self.discord_createdat:     str = None
        self.aqw_id:                int = None
        self.aqw_username:          str = None
        
        # Override defaults with any provided keyword arguments
        for key, value in kwargs.items():
            setattr(self, key, value)
