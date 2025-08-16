# models.py
class UserInfo:
    """Class to hold user information with attributes that can be dynamically set"""
    def __init__(self, **kwargs):
        # Initialize default attributes with None
        self.ID:                    int = None
        self.Name:                  str = None
        self.Admin:                 int = None
        self.Discord_ID:            int = None
        self.Discord_Username:      str = None
        self.Discord_Mention:       str = None
        self.Discord_IsBot:         int = None
        self.Discord_CreatedAt:     str = None
        self.AQW_ID:                int = None
        self.AQW_Username:          str = None
        
        # Override defaults with any provided keyword arguments
        for key, value in kwargs.items():
            setattr(self, key, value)

