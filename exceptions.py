class APIError(Exception):
    def __init__(self):
        super().__init__(self)

    def __str__(self):
        return "APIError"
    
class FileFormatError(Exception):
    def __init__(self):
        super().__init__(self)

    def __str__(self):
        return "FileFormatError"
    
class Roll20InterfaceError(Exception):
    def __init__(self):
        super().__init__(self)

    def __str__(self):
        return "FileFormatError"