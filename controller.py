from r20 import Roll20
from messages import MessageLog, Message, MessageTag, SYSTEM_TAGS
from generator import Generator
from exceptions import APIError, FileFormatError, Roll20InterfaceError

from time import sleep
from random import random
import yaml
import shlex
import threading

MESSAGE_POLLING_SLEEP_INTERVAL = 0.5
NON_SYSTEM_TOKEN_LIMIT = 2000
OPERATOR_STRING = '%'

class Controller():
    # Precondition: Roll20 object must be logged in and ready to go
    def __init__(self, r20: Roll20, gameID: str):
        self.gen = Generator()
        self.r20 = r20
        self.msg_log = MessageLog()
        self._tokens_used = 0
        self._gameID = gameID

        self._help_strings = {
            'help' : f'USAGE: {OPERATOR_STRING}help\nView command help',
            'poke' : f'USAGE: {OPERATOR_STRING}poke\nForce the bot to respond.',
            'character' : f'USAGE: {OPERATOR_STRING}character \'[character\'s display name]\'\nChange which character the bot is controlling.',
            'system' : f'USAGE: {OPERATOR_STRING}system \'[new system prompt]\'\nChange the system prompt.',
            'pause' : f'USAGE: {OPERATOR_STRING}pause\nStop posting in-character until the {OPERATOR_STRING}resume command is given.',
            'resume' : f'USAGE: {OPERATOR_STRING}resume\nContinue posting in-character.',
            'stop' : f'USAGE: {OPERATOR_STRING}stop\nTerminate the program'
        }

        # Store all character messages, emotes, narrations
        self._log_messages(r20.get_all_messages())
        # This Message id marks the last message before the latest set of new messages was added.
        self._last_id = None

        self.interface = r20.get_player_name()
        if(self.interface == None):
            print('Could not find the player name of the bot.')
            raise Roll20InterfaceError()

        settings = Controller._get_settings_from_file()
        try:
            if(self._gameID in settings['bot_character_names']):
                self.character = settings['bot_character_names'][self._gameID]
                assert isinstance(self.character, str)
            else:
                self.character = input(f'settings.yaml specifies no character for this game (gameID={self._gameID}). Enter the name of the character you want the bot to play: ')

            self.system_prompt = self._get_system_prompt(character=self.character, settings=settings)
            
            self.model = settings['model']

            self.use_whitelist = False
            self.use_blacklist = False
            self.blacklist = []
            self.whitelist = []

            if(self._gameID in settings['is_character']):
                game = settings['is_character'][self._gameID]
                self.use_whitelist = (game['enable_character_whitelist'] if 'enable_character_whitelist' in game else self.use_whitelist)
                self.use_blacklist = (game['enable_character_blacklist'] if 'enable_character_blacklist' in game else self.use_blacklist)
                self.whitelist = (game['character_whitelist'] if 'character_whitelist' in game else self.whitelist)
                self.blacklist = (game['character_blacklist'] if 'character_blacklist' in game else self.blacklist)
                del game

            self.use_operator_whitelist = False
            self.use_operator_blacklist = False
            self.operator_blacklist = []
            self.operator_whitelist = []

            if(self._gameID in settings['is_operator']):
                game = settings['is_operator'][self._gameID]
                self.use_operator_whitelist = (game['enable_operator_whitelist'] if 'enable_operator_whitelist' in game else self.use_operator_whitelist)
                self.use_operator_blacklist = (game['enable_operator_blacklist'] if 'enable_operator_blacklist' in game else self.use_operator_blacklist)
                self.operator_whitelist = (game['operator_whitelist'] if 'operator_whitelist' in game else self.operator_whitelist)
                self.operator_blacklist = (game['operator_blacklist'] if 'operator_blacklist' in game else self.operator_blacklist)
                del game
            
                
        except KeyError as e:
            print('settings.yaml file formatted incorrectly')
            raise e

        # command flags
        self._poked = False
        self._stopped = False
        self._paused = False

    @staticmethod
    def _get_settings_from_file() -> dict:
        try:
            with open('settings.yaml', 'r') as file:
                settings = yaml.safe_load(file)
        except OSError as error:
            try:
                with open('settings.yml', 'r') as file:
                    settings = yaml.safe_load(file)
            except OSError as error:
                print('Missing settings.yaml file')
                raise FileNotFoundError
        return settings
    
    def _get_system_prompt(self, character: str, settings: dict) -> str:
            if(self._gameID in settings['character_descriptions'] and character in settings['character_descriptions'][self._gameID]):
                system_prompt = settings['character_descriptions'][self._gameID][character]
            elif(self._gameID in settings['default_character_descriptions']):
                system_prompt = (settings['default_character_descriptions'][self._gameID]).format(name=character)
            elif('game_independent_default' in settings['default_character_descriptions']):
                system_prompt = (settings['default_character_descriptions']['game_independent_default']).format(name=character)
            else:
                print('settings.yaml is missing the `game_independent_default` field under `default_character_descriptions`.')
                raise FileFormatError
            return system_prompt
    
    def _log_message(self, message: list) -> Message:
        return self.msg_log.append_message(Message(message[0], message[1], message[2], message[3]))

    def _log_messages(self, messages: list[list]) -> list[Message]:
        msg_objects = []
        for message in messages:
            msg_objects.append(self._log_message(message))
        return msg_objects

    # Adds new messages to the message log. Returns True iff there are new messages
    def _update_messages(self, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[Message]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)

        last_msg = self.msg_log.get_last_n_messages(1)
        if (len(last_msg) > 0):
            last_msg = last_msg[0]
            new_msgs = self.r20.get_messages_after_id(last_msg.get_id(), tag_blacklist=ignore_tags)

            logged_messages = self._log_messages(new_msgs)
            self._last_id = last_msg.get_id()
            if(len(logged_messages) > 0):
                return logged_messages
        return []

    def is_visible(self, msg: Message):
        if(self.use_blacklist and msg.get_character() in self.blacklist):
            return False
        if(self.use_whitelist and msg.get_character() not in self.whitelist):
            return False
        return True

    # Defines conditions under which the bot should generate a response
    def _should_respond(self, new_messages) -> bool:
        # Will never generate a response if the last in-character message was posted by the bot.
        # Will always generate a response if the bot's name is a substring of one of the new non-bot messages.
        # Has a {CHANCE} probability of responding otherwise (you could modify this to get the generator to predict if it should respond, 
        # but that would significantly increase the number of requests)
        CHANCE = 0.5

        if(self._paused):
            return False
        if(self._poked):
            return True
        if(self._last_id == None):
            # i.e. There are no messages yet
            return False
        if(len(new_messages) <= 0):
            return False
        
        response_condition = False
        for msg in new_messages:
            if(self.is_visible(msg) and msg.get_character() != self.character):
                response_condition = True
                if(self.character in msg.get_content()):
                    # The bot's character was mentioned in this message
                    return True
        if(response_condition):
            return (True if random() <= CHANCE else False)
        return False

    # The following method would respond after every non-bot message. Useful for testing. 

    # def _should_respond(self) -> bool:
    #     if(self._last_id == None):
    #         return False
    #     new_msgs = self.msg_log.get_messages_after_id(self._last_id, tag_blacklist=SYSTEM_TAGS)
    #     assert(len(new_msgs) > 0)
    #     if(new_msgs[-1].get_character() != self.character):
    #         return True
    #     return False

    @staticmethod
    def _counter(chars: int) -> int:
        return int(chars/4)

    def is_operator(self, name: str|None) -> bool:
        if(name == None):
            return False
        assert isinstance(name, str)
        if(self.use_operator_blacklist and name in self.operator_blacklist):
            return False
        if(self.use_operator_whitelist and name not in self.operator_whitelist):
            return False
        return True

    def exec_commands(self, new_messages: list[Message]) -> None:
        if(new_messages == None or len(new_messages) <= 0):
            return
        
        for msg in new_messages:
            if(self.is_operator(msg.get_character()) and msg.get_content()[0:len(OPERATOR_STRING)] == OPERATOR_STRING):
                try:
                    args = shlex.split(s=msg.get_content().removeprefix(OPERATOR_STRING), posix=True)
                except ValueError as e:
                    self.notify('Error parsing command: ' + repr(e))
                    continue

                if('--help' in args and args[0] in self._help_strings):
                    self.notify(f'{args[0]}: {self._help_strings[args[0]]}')
                    continue
                match args[0]:
                    case "help":
                        help = ''
                        for command in self._help_strings:
                            help += f'{command}: {self._help_strings[command]}\n'
                        help += '\nTo get help for an idividual command, type `[command] --help`.'
                        self.notify(help)

                    case "character":
                        if(len(args)>1):
                            self.command_character(name=args[1])
                        else:
                            self.notify(f'Missing argument. Use `{OPERATOR_STRING}{args[0]} --help` for help with this command.')
                        if(len(args)>2):
                            self.notify(f'{len(args)-2} more arguments than expected were supplied. Make sure any quote marks in the supplied system prompt are properly escaped using `\\`.')
                    case "poke":
                        self.command_poke()
                        
                    case "stop":
                        self.command_stop()
                        
                    case "system":
                        if(len(args)>1):
                            self.command_system(args[1])
                        else:
                            #self.notify(f'Missing argument. Use `{OPERATOR_STRING}{args[0]} --help` for help with this command.')
                            self.notify(f'Current system prompt: "{self.system_prompt}"')
                        if(len(args)>2):
                            self.notify(f'{len(args)-2} more arguments than expected were supplied. Make sure any quote marks in the supplied system prompt are properly escaped using `\\`.')

                    case "pause":
                        self.command_pause()
                        
                    case "resume":
                        self.command_resume()
                    case _:
                        self.notify(f'Unrecognised command `{args[0]}`')

    def command_poke(self) -> None:
        if(not self._paused):
            self._poked = True

    def command_stop(self) -> None:
        self._stopped = True

    def command_pause(self) -> None:
        self._paused = True
        self.notify('Paused')
 
    def command_resume(self) -> None:
        self._paused = False
        self.notify('Resumed')

    def command_character(self, name: str) -> None:
        if(self.r20.controls_character(name)):    
            self.character = name
            settings = Controller._get_settings_from_file()
            try:
                self.system_prompt = self._get_system_prompt(character=self.character, settings=settings)
            except:
                self.notify(f'Failed to load system prompt from settings.yaml. Set it with the `{OPERATOR_STRING}system` command.')
        else:
            self.notify(f'This account does not control a character named "{name}".')

    def command_system(self, text: str) -> None:
        assert isinstance(text, str)
        self.system_prompt = text

    def notify(self, text: str):
        assert self.r20.controls_character(self.interface) # type: ignore
        self.r20.post_with_name(text=text, character=self.interface) # type: ignore


    def backend(self):
        stop_idling_event = threading.Event()
        print('Ready')
        self.notify('Ready')
        while True:
            new_msgs = self._update_messages()
            if(len(new_msgs) > 0 or self._poked):
                # There are new messages
                if(len(new_msgs) > 0):
                    self.exec_commands(new_msgs)

                if(self._stopped):
                    return 

                if(self._should_respond(new_msgs)):
                    # Conditions met for new query
                    history = self.msg_log.get_token_messages(counter=__class__._counter, token_limit=NON_SYSTEM_TOKEN_LIMIT, \
                                                              character_whitelist=(self.whitelist if self.use_whitelist else None), \
                                                                character_blacklist=(self.blacklist if self.use_blacklist else None))
                    try:
                        stop_idling_event.clear()
                        idler = threading.Thread(name='idler', daemon=True, target=self.r20.idle, kwargs={'as_character' : self.character, 'stop_event' : stop_idling_event})
                        idler.start()
                        response = self.gen.get_response(as_character=self.character, history=history, system_prompt=self.system_prompt, model=self.model)

                        tokenage = response["usage"]["total_tokens"] # type: ignore
                        self._tokens_used += tokenage
                        print('Tokens Used - Last Query: ' + str(tokenage) + ' - Total: ' + str(self._tokens_used))
                        text = response['choices'][0]['message']['content'].strip().removeprefix(f'{self.character}: ').strip('"') # type: ignore

                        stop_idling_event.set()
                        while(idler.is_alive()):
                            pass

                        self.r20.post_with_name(text=f'"{text}"', character=self.character)
                    except APIError as error:
                        print('API error occurred')
                        raise error
                    self._poked = False
            else:
                sleep(MESSAGE_POLLING_SLEEP_INTERVAL)



                    


