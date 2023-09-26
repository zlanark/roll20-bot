from selenium import webdriver;
from selenium.webdriver.common.keys import Keys;
from selenium.webdriver.common.by import By;
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC;
from selenium.common import exceptions as WebDriverExceptions;
from selenium.common.exceptions import TimeoutException; 
from selenium.webdriver.support.select import Select
from selenium.webdriver.remote.webelement import WebElement

import threading
import os;
import re
from time import sleep

from messages import MessageTag
from messages import SYSTEM_TAGS

from globals import *

ROLL20_URL = "https://app.roll20.net"
ROLL20_LOGIN_URL = ROLL20_URL + "/login"
ROLL20_CAMPAIGN_URL = ROLL20_URL + "/editor/setcampaign/" # game ID is appended to this

LOGIN_TIMEOUT = 20
CF_CLEARANCE_TIMEOUT = 5
CF_CLEARANCE_RETRY_TIMEOUT = 10
GAME_CONNECT_TIMEOUT = 10

# This class is a mess. It's also the most liable to break, so sorry about that.
# To use this class, make sure $R20_CF_CLEARANCE, $R20_PASSWORD, and $R20_EMAIL are set
class Roll20():
    def __init__(self, driver_args: list[str]) -> None:
        # chat interaction elements
        self._char_select = None
        self._chat_input = None
        self._chat_send = None
        self._chat_history = None
        self._chat_window = None

        options = webdriver.FirefoxOptions()
        for arg in driver_args:
            options.add_argument(arg)
        self.driver = webdriver.Firefox(options=options)
        
        self.driver.get(ROLL20_URL)
        self.update_cf_clearance(os.environ[ENV_CF_CLEARANCE])

    def __del__(self):
        self.driver.quit()

    def controls_character(self, character: str|None) -> bool:
        if(character == None):
            return False
        assert self._char_select is not None
        for option in self._char_select.options:
            if(option.text == character):
                return True
        return False
    
    def get_player_name(self) -> str|None:
        assert self._char_select is not None
        for option in self._char_select.options:
            value = option.get_attribute('value')
            if(value != None and 'PLAYER' in value.upper()):
                return option.text
        return None

    '''Message posting methods'''

    # precondition: must already be on app.roll20.net
    def update_cf_clearance(self, token: str) -> None:
        os.environ[ENV_CF_CLEARANCE] = token
        self._update_cf_cookie()

    def _update_cf_cookie(self) -> None:
        self._cf_clearance_cookie = {
            "name" : "cf_clearance",
            "value" : os.environ[ENV_CF_CLEARANCE],
            "path" : "/",
            "secure" : True,
            "httpOnly" : True
        }
        self.driver.add_cookie(self._cf_clearance_cookie)

    def post_with_id(self, text: str, id: str):
        try:
            assert self._char_select is not None
            self._char_select.select_by_value(id)
            self._post(text)
        except WebDriverExceptions.NoSuchElementException as e:
            print(f"Failed to post as character with ID \"{id}\". Check that the ID is correct and that this account has permission to post as this character")

    def post_with_name(self, text: str, character: str):
        try:
            assert self._char_select is not None
            self._char_select.select_by_visible_text(character)
            self._post(text)
        except WebDriverExceptions.NoSuchElementException as e:
            print(f"Failed to post as \"{character}\". Check that the name is correct and that this account has permission to post as this character")

    def _post(self, text: str) -> None:
        assert self._chat_input is not None
        assert self._chat_send is not None
        self._chat_input.clear()
        self._chat_input.send_keys(text)
        self._chat_send.click()

    def idle(self, as_character: str, stop_event : threading.Event):
        assert self._chat_input is not None
        assert self._char_select is not None
        try:
            self._char_select.select_by_visible_text(as_character)
        except:
            pass
        self._chat_input.send_keys('a')
        while(not stop_event.is_set()):
            self._chat_input.send_keys('a')
            sleep(0.3)
            self._chat_input.send_keys(Keys.BACKSPACE)
            sleep(0.3)
        self._chat_input.send_keys(Keys.BACKSPACE)

    '''Message reading methods'''

    # get the last n messages. Will only scan messages up to the top of the editor (won't scan through chat archive)
    # If n is greater than the number of visible messages, will only return visible messages. Messages with ignored tags won't be counted.
    def get_last_n_messages(self, n: int, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[list]:
        assert self._chat_window is not None

        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        locator = "div[contains(@class,'message')]" 
        total_msgs = len(self._chat_window.find_elements(By.XPATH, locator))
        position = total_msgs
        message_count = 0
        messages = []
        while position > 0 and message_count < n:
            # I don't know how find_elements orders results, so I access their positions with an XPath query
            elem = self._chat_window.find_element(By.XPATH, f"{locator}[position() = {position}]")
            msg = Roll20._extract_message_info(elem)
            # append message if it doesn't have an ignored tag
            if(not Roll20._has_unwanted_tags(msg, ignore_tags)):
                message_count += 1
            position -= 1

        elems = self._chat_window.find_elements(By.XPATH, f"{locator}[position() > {position} and position() <= {total_msgs}]")
        messages = Roll20._extract_message_info_list(elems, ignore_tags)
        return messages

    # get a list of messages posted after the message with the provided ID. Will only scan messages up to the top of the editor (won't scan through chat archive)
    # If the ID can't be found, will return every visible message
    def get_messages_after_id(self, id: str, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[list]:
        assert self._chat_window is not None

        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        limiting_msg_elem = self._chat_window.find_elements(By.XPATH, f"div[@data-messageid='{id}']")

        if len(limiting_msg_elem) == 0:
            position = 0
        else:
            limiting_msg_elem = limiting_msg_elem[0]
            position = self._chat_window.find_elements(By.XPATH, "div[contains(@class,'message')]").index(limiting_msg_elem) + 1 #add one because XPATH indexes elements from 1, not 0

        msg_elems = self._chat_window.find_elements(By.XPATH, f"div[contains(@class,'message')][position() > {position}]")
        return Roll20._extract_message_info_list(msg_elems, ignore_tags)

    # returns a list of lists of the form (content: str, character: str, id: str, tags: list[MessageTag])
    # Will ignore hidden messages, system messages and dice results (unless you change the ignore_tags)
    def get_all_messages(self, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[list]:
        assert self._chat_history is not None

        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)          
        original_window = self.driver.current_window_handle
        assert len(self.driver.window_handles) == 1

        # open chat archive
        self._chat_history.click()
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.number_of_windows_to_be(2))

        # switch to chat archive
        for window_handle in self.driver.window_handles:
            if window_handle != original_window:
                self.driver.switch_to.window(window_handle)
                break
        
        # display all messages on one page if not already
        wait.until(EC.visibility_of_element_located((By.ID, 'paginateToggle')))
        if(self.driver.find_element(By.ID, 'paginateToggle').text == 'Show on One Page'):
            self.driver.find_element(By.ID, "paginateToggle").click()

        wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@id='textchat']/div/div[contains(@class,'message')]")))
        msg_elems = self.driver.find_element(By.ID, 'textchat').find_elements(By.XPATH, "div/div[contains(@class,'message')]")
        
        messages = Roll20._extract_message_info_list(msg_elems, ignore_tags)

        self.driver.close()
        self.driver.switch_to.window(original_window)
        wait.until(EC.url_to_be("https://app.roll20.net/editor/"))
        return(messages)

    '''Static methods for extracting information from messages'''

    # Extracts message information from a list of message WebElements
    # returns a list of lists of the form (content: str, character: str, id: str, tags: set[MessageTag])
    @staticmethod
    def _extract_message_info_list(message_elems: list[WebElement], tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[list]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        last_character = None
        messages = []


        for message_elem in message_elems:
            message = Roll20._extract_message_info(message_elem)
            if (MessageTag.CHARACTER in message[3]):

                # If no associated name, inherit from last character message
                if(message[1] == None):
                    message[1] = last_character # type: ignore
                last_character = message[1]

                # With this section, these warnings would occur when consecutive messages by one character are split over >1 calls of this method. 
                # This is dealt with in MessageLog.append_message(), so no need for this
                # # If still no associated name, but a character message, log warning
                # if(message[1] == None):
                #     print("Warning: A character message has no character name associated with it")

            messages.append(message)

        # filter out messages with unwanted tags
        messages = Roll20._filter_unwanted_tags(messages, ignore_tags)
        return messages
    
    @staticmethod
    def _extract_message_info(message_elem: WebElement) -> list:
        tags = set()
        by = None
        content = message_elem.get_property("innerText")

        if(Roll20._is_character_message(message_elem)):
            by_elem = message_elem.find_elements(By.CLASS_NAME, "by")
            if(len(by_elem) > 0):
                # Has character name attatched
                by = by_elem[0].get_property("innerText")
            if(by != None):
                assert isinstance(content, str)
                assert isinstance(by, str)
                content = content.removeprefix(by).strip()
                by = by.removesuffix(':').removesuffix(' (GM)')
            
        id = message_elem.get_attribute("data-messageid")

        tags = Roll20._get_message_tags(message_elem)
        return [content, by, id, tags]

    @staticmethod
    def _filter_unwanted_tags(messages: list[list], tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> list[list]:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        return [msg for msg in messages if not Roll20._has_unwanted_tags(msg, ignore_tags)]

    @staticmethod
    def _has_unwanted_tags(message: list, tag_blacklist=SYSTEM_TAGS, tag_whitelist=None) -> bool:
        ignore_tags = MessageTag.to_blacklist(blacklist=tag_blacklist, whitelist=tag_whitelist)
        return any(tag in message[3] for tag in ignore_tags)

    @staticmethod
    def _get_message_tags(message_elem: WebElement) -> set[MessageTag]:
        tags = set()
        if(Roll20._is_character_message(message_elem)):
            tags.add(MessageTag.CHARACTER)
        if(Roll20._is_system_message(message_elem)):
            tags.add(MessageTag.SYSTEM)
        if(Roll20._is_emote_message(message_elem)):
            tags.add(MessageTag.EMOTE)
        if(Roll20._is_dice_message(message_elem)):
            tags.add(MessageTag.DICE)
        if(Roll20._is_hidden_message(message_elem)):
            tags.add(MessageTag.HIDDEN)
        if(Roll20._is_desc_message(message_elem)):
            tags.add(MessageTag.DESCRIPTION)
        return tags

    @staticmethod
    def _is_character_message(elem: WebElement):
        assert isinstance(elem, WebElement)
        classes = elem.get_attribute('class').split() # type: ignore
        return 'general' in classes

    @staticmethod
    def _is_system_message(elem: WebElement):
        assert isinstance(elem, WebElement)
        classes = elem.get_attribute('class').split() # type: ignore
        return 'system' in classes or 'news' in classes

    @staticmethod
    def _is_emote_message(elem: WebElement):
        assert isinstance(elem, WebElement)
        classes = elem.get_attribute('class').split() # type: ignore
        return 'emote' in classes

    @staticmethod
    def _is_dice_message(elem: WebElement):
        assert isinstance(elem, WebElement)
        classes = elem.get_attribute('class').split() # type: ignore
        return 'rollresult' in classes
    
    @staticmethod
    def _is_desc_message(elem: WebElement):
        assert isinstance(elem, WebElement)
        classes = elem.get_attribute('class').split() # type: ignore
        return 'desc' in classes
    
    @staticmethod
    def _is_hidden_message(elem: WebElement):
        assert isinstance(elem, WebElement)
        classes = elem.get_attribute('class').split() # type: ignore
        return 'hidden-message' in classes

    '''
    Logs the webdriver into Roll20.
    This method passes the Cloudflare automation check with a clearance token taken from another browser which has already been allowed through.
    This token must be supplied by the user, either in the $R20_CF_CLEARANCE environment variable, or when prompted.
    Tokens expire regularly, so you'll have to update it frequently. Alternatively you could use a fork of selenium which can pass Cloudflare checks.
    '''
    def login(self, email=None, password=None, use_env=True) -> None:
        try:
            # Confirm that the cloudflare test has been passed by checking the title of the page. 
            # This could change, so if the program says that it "Passed Cloudflare check" when it hasn't, see if the title needs updating
            TITLE = "Just a moment"

            cf_retry = False
            while True:
                try:
                    # Make sure current $R20_CF_CLEARNCE value is being used
                    self._update_cf_cookie()

                    self.driver.get(ROLL20_LOGIN_URL)
                    WebDriverWait(self.driver, (CF_CLEARANCE_RETRY_TIMEOUT if cf_retry else CF_CLEARANCE_TIMEOUT)).until(EC.none_of(EC.title_contains(TITLE)))
                    break
                except TimeoutException as e:
                    cf_input = input("The Cloudflare clearance token has probably expired. Enter a new one (enter nothing to retry with existing token): ")
                    if(cf_input != ""):
                        self.update_cf_clearance(cf_input)

                # Will retry with a longer wait time
                cf_retry = True

            print("Passed Cloudflare check")

            while True:
                if(use_env):
                    email = os.environ[ENV_R20_EMAIL]
                    password = os.environ[ENV_R20_PASSWORD]

                self.driver.find_element(By.ID, "email").send_keys(email)
                self.driver.find_element(By.ID, "password").send_keys(password)
                self.driver.find_element(By.ID, "login").click()
                try:
                    WebDriverWait(self.driver, LOGIN_TIMEOUT).until(EC.any_of(EC.url_changes(ROLL20_LOGIN_URL)), EC.visibility_of_element_located((By.ID, "login-error"))) # type: ignore
                except TimeoutException as e:
                    print(f"login timed out ({LOGIN_TIMEOUT}s)")
                    raise e
                if(len(self.driver.find_elements(By.ID, "login-error")) == 0):
                    break
                else:
                    email = input("Incorrect email or password. Enter new email: ")
                    password = input("Incorrect email or password. Enter new password: ")
            
            print("Logged in")
                
        except WebDriverExceptions.WebDriverException as e:
            print("The webdriver failed to interface with Roll20. Site structure or GUI may have changed. Check Roll20._login()")
            raise e

    # Precondition: must be logged in
    def join_game(self, gameID: str) -> None:
        try:
            try:
                while True:
                    print('Joining game...')
                    self.driver.get(ROLL20_CAMPAIGN_URL + gameID)
                    WebDriverWait(self.driver, 10).until(EC.any_of(\
                        EC.presence_of_element_located((By.XPATH, "//h1[contains(text(), 'Not Authorized') or contains(text(), 'Not Authorised')] or contains(text(), 'Not Found')]")),\
                        EC.visibility_of_element_located((By.ID, "rightsidebar"))))
                    # If not connected to the game (by checking for rightsidebar), prompt for new gameID and retry
                    if(len(self.driver.find_elements(By.ID, "rightsidebar")) == 0):
                        new_gameID = input("The game with this ID either doesn't exist, or you are not authorised to access it. Enter a new game ID (leave blank to retry with the current ID): ").strip()
                        gameID = (gameID if new_gameID == "" else new_gameID)
                    else:
                        title = self.driver.find_element(By.TAG_NAME, "title").get_property("innerHTML")
                        title = re.sub(r"\s\|\sRoll20", "", title).strip() # type: ignore

                        self._initialise_chat()

                        print(f"Joined game \"{title}\" (game ID: {gameID})")
                        return
            except TimeoutException as e:
                input(f"Timed out connecting to game ({GAME_CONNECT_TIMEOUT}s). Press enter to retry.")
                self.join_game(gameID)
        except WebDriverExceptions.WebDriverException as e:
            print("The webdriver failed to interface with Roll20. Site structure or GUI may have changed. Check Roll20.join_game()")
            raise e

    def _initialise_chat(self) -> None:
        input_area = self.driver.find_element(By.ID, "textchat-input")
        self._chat_input = input_area.find_element(By.TAG_NAME, "textarea")
        self._char_select = Select(input_area.find_element(By.ID, "speakingas"))
        self._chat_send = input_area.find_element(By.ID, "chatSendBtn")
        self._chat_history = self.driver.find_element(By.ID, "openchatarchive")
        self._chat_window = self.driver.find_element(By.ID, "textchat").find_element(By.XPATH, "./div[@class='content']")

