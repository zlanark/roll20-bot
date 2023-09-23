from enum import Enum
from generator import Generator

class MessageTag(Enum):
    CHARACTER = 1
    SYSTEM = 2          
    HIDDEN = 3
    DICE = 4
    EMOTE = 5
    DESCRIPTION = 6

    @classmethod
    def to_blacklist(cls, blacklist, whitelist) -> set:
        combined_blacklist = set()
        if whitelist != None:
            combined_blacklist = {tag for tag in MessageTag if tag not in whitelist}
        if blacklist != None:
            combined_blacklist.union(blacklist)
        return combined_blacklist

SYSTEM_TAGS = {MessageTag.SYSTEM, MessageTag.DICE, MessageTag.HIDDEN}

class Message():
    def __init__(self, content, character, id, tags):
        self._content = content
        self._character = character
        self._id = id
        self._tags = tags

    def get_content(self) -> str:
        return self._content

    def get_character(self) -> str:
        return self._character

    def get_id(self) -> str:
        return self._id

    def get_tags(self) -> set[MessageTag]:
        return self._tags

    def has_tag(self, tag: MessageTag) -> bool:
        return tag in self.get_tags()

    def has_any_of_tags(self, tags: set[MessageTag]) -> bool:
        return any(tag in self.get_tags() for tag in tags)

    def hide(self):
        if MessageTag.HIDDEN not in self.get_tags():
            self._tags.append(MessageTag.HIDDEN)

    def count_gpt_tokens(self) -> int:
        #This is only an approximation
        return Generator.count_tokens(len(self.get_content()) + (len(self.get_character()) if self.get_character() != None else 0) + 2)

class MutableMessage(Message):
    def set_character(self, character: str|None):
        self._character = character

    def set_id(self, id):
        assert(type(id) in (str, None))
        self._id = id

    def set_content(self, content):
        assert(type(content) == str)
        self._content = content

    def set_tag(self, tag: MessageTag):
        assert(type(tag) == MessageTag)
        if tag not in self.get_tags():
            self._tags.append(tag)

    def set_tags(self, tags: list[MessageTag]):
        for tag in tags:
            self.set_tag(tag)

class MessageLog():
    def __init__(self):
        self.log = list()

    def append_message(self, message: Message) -> None:
        self.log.append(message)
    
    def prepend_message(self, message: Message) -> None:
        self.log.insert(0, message)

    def append_messages(self, messages: list[Message]) -> None:
        self.log.extend(messages)
    
    def prepend_messages(self, messages: list[Message]) -> None:
        self.log = messages + self.log

    def get_last_n_messages(self, n: int, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        return self.get_log(ignore_tags)[-n:]

    def get_log(self, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        return [msg for msg in self.log if not msg.has_any_of_tags(ignore_tags)]

    def get_messages_up_to_id(self, id: str, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        index = None
        log = self.get_log(ignore_tags)
        for i, message in enumerate(log):
            if(message.get_id() == id):
                index = i
        if(index == None):
            return log
        else:
            return log[index:]

    def get_token_messages(self, token_limit: int, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        if(type(token_limit) != int):
            raise TypeError("'tokens' argument of Message.get_token_messages must be an integer")
        elif(token_limit < 0):
            raise ValueError("'tokens' argument of Message.get_token_messages must be >= 0")
        log = self.get_log(tag_blacklist=tag_blacklist, tag_whitelist=tag_whitelist)
        if(len(log) == 0):
            return []

        token_count = 0
        messages = []
        i = len(self.log)-1
        
        while token_count < token_limit:
            message = log[i]
            token_count += message.count_gpt_tokens() + 1
            if(token_count <= token_limit):
                messages.append(message)
        messages.reverse()
        return messages
            
