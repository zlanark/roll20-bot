from enum import Enum


class MessageTag(Enum):
    CHARACTER = 1
    SYSTEM = 2          
    HIDDEN = 3
    DICE = 4
    EMOTE = 5
    DESCRIPTION = 6

    # combines a blacklist and a whitelist of MessageTags into just a blacklist
    @classmethod
    def to_blacklist(cls, blacklist, whitelist) -> set:
        combined_blacklist = set()
        if whitelist != None:
            combined_blacklist = {tag for tag in MessageTag if tag not in whitelist}
        if blacklist != None:
            return combined_blacklist.union(blacklist)
        return combined_blacklist

SYSTEM_TAGS = {MessageTag.SYSTEM, MessageTag.DICE, MessageTag.HIDDEN}


class Message():
    def __init__(self, content, character, id, tags):
        self._content = content
        self._character = character
        self._id = id
        self._tags = tags

    # should've used MutableMessage, but i'll just tack this here to allow for fixing orphaned messages when joining them to a messageLog
    def fix_character(self, character: str|None):
        assert(self._character == None)
        self._character = character

    def get_content(self) -> str:
        return self._content

    def get_character(self) -> str|None:
        return self._character

    def get_id(self) -> str:
        return self._id

    def get_tags(self) -> set[MessageTag]:
        return self._tags

    def has_tag(self, tag: MessageTag) -> bool:
        return tag in self.get_tags()

    def has_any_of_tags(self, tags: set[MessageTag]) -> bool:
        return not self.get_tags().isdisjoint(tags)

    def hide(self):
        if MessageTag.HIDDEN not in self.get_tags():
            self._tags.append(MessageTag.HIDDEN)

    def count_tokens(self, counter) -> int:
        #This is only an approximation
        return counter(len(self.get_content()))

def filter_tags(messages: list[Message], tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
    ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
    return [msg for msg in messages if not msg.has_any_of_tags(ignore_tags)]

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

    def _get_last_character(self, index=None) -> str|None:
        messages = self.get_log(tag_whitelist=[MessageTag.CHARACTER])
        # Latest index, or specified index if it exists
        index = (index if index != None and index >= 0 and index <= len(messages)-1 else len(messages)-1)
        character = None
        while(character == None and index >= 0):
            character = messages[index].get_character()
            index -= 1 
        return character
        


    def append_message(self, message: Message) -> Message:
        if(message.get_character() == None and message.has_tag(MessageTag.CHARACTER)):
            last = self._get_last_character()
            if(last == None):
                print('Warning: Message is tagged as character message, but has no character associated with it.')
            message.fix_character(last)
        self.log.append(message)
        return message
    
    def prepend_message(self, message: Message) -> None:
        self.log.insert(0, message)

    def append_messages(self, messages: list[Message]) -> list[Message]:
        for msg in messages:
            self.append_message(msg)
        # messages *should* be passed by reference, so any calls of Message.fix_character from 
        # Message.append_message should be refelected in the returned list
        return messages
    
    def prepend_messages(self, messages: list[Message]) -> None:
        self.log = messages + self.log

    def get_last_n_messages(self, n: int, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        return self.get_log(tag_blacklist=ignore_tags)[-n:]

    def get_log(self, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        return filter_tags(messages=self.log, tag_blacklist=ignore_tags)

    # Does not include the message with the given id, only those posted after it
    def get_messages_after_id(self, id: str, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        index = None
        log = self.get_log(tag_blacklist=ignore_tags)
        for i, message in enumerate(log):
            if(message.get_id() == id):
                index = i
                break
        if(index == None):
            return log
        else:
            # list slicing beyond the bounds of the list just returns an empty list, 
            # so this should still work if `index` points to the last element in the list
            return log[index+1:]

    def get_token_messages(self, counter, token_limit: int, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None, character_blacklist=None, character_whitelist=None) -> list[Message]:
        if(type(token_limit) != int):
            raise TypeError("'tokens' argument of Message.get_token_messages must be an integer")
        elif(token_limit < 0):
            raise ValueError("'tokens' argument of Message.get_token_messages must be >= 0")
        log = self.get_log(tag_blacklist=tag_blacklist, tag_whitelist=tag_whitelist)

        assert isinstance(character_blacklist, list|None) and isinstance(character_whitelist, list|None)
        if(character_whitelist !=None):
            log = [msg for msg in log if msg.get_character() in character_whitelist]
        if(character_blacklist !=None):
            log = [msg for msg in log if msg.get_character() not in character_blacklist]

        if(len(log) == 0):
            return []

        token_count = 0
        messages = []
        i = len(log)-1
        
        while token_count < token_limit and i >= 0:
            message = log[i]
            token_count += message.count_tokens(counter=counter) + 1
            if(token_count <= token_limit):
                messages.append(message)
            i -= 1
        messages.reverse()
        return messages
            