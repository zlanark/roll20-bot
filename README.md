# roll20-bot
Now you can be out-roleplayed by the machines too!

A cludge of a program that uses the OpenAI API and a webdriver to play an AI character in a Roll20 game.
Features:
- A bot interface which can be accessed in-game with the command prefix `%`. See [In-Game Commands](#in-game-commands).
- Per-game, per-character system prompts (i.e. character + setting descriptions)

If you want to modify this program to use something other than the OpenAI API, override the `get_response()` method in `generator.py`.

## Requirements
- Python 3.11.x
- Firefox
- A Roll20 account
- An OpenAI API Key

## Setup
1. Have:
  - [python](https://www.python.org/downloads/release/python-3115/) installed (I've only tested this in Python 3.11.5. Other versions may work) and in your $PATH
  - [Firefox](https://www.mozilla.org/en-US/firefox/) installed and in your $PATH
  - [git](https://git-scm.com/) installed and in your $PATH
3. Open a terminal, `cd` into the directory you want to install into, and clone this repository into it:
  ```bash
  cd '[replace with your install directory]'
  git clone https://github.com/zlanark/roll20-bot.git
  cd roll20-bot
  ```
4. Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```
5. Run `main.py` to start the program:
  ```bash
  python main.py -k [OpenAI API Key] -u [Roll20 username] -p [Roll20 password] -g [Roll20 game ID] -x
  ```

## Environment Variables
roll20-bot uses the following environment variables:
- `$R20_CF_CLEARANCE` to store a [cf_clearance token](#cf_clearance).
- `$OPENAI_API_KEY` to store an OpenAI API key.
- `$R20_EMAIL` to store the email associated with the account through which the bot acts.
- `$R20_PASSWORD`to store the password of the account through which the bot acts.


These environment variables can be initialised:
- Through the associated [command-line arguments](#command-line-arguments).
- With a [.env file](https://pypi.org/project/python-dotenv/) placed in the same directory as `main.py`. To enable the use of the `.env` file start the program with the `--env` argument.
- Elsewhere before running the program.

\
Command-line arguments overide the `.env` file, which in turn overrides pre-existing environment variable values.

## Command Line Arguments
```
usage: python main.py [-h] [-c CF_CLEARANCE] [-k APIKEY] [-g GAMEID] [-u USERNAME] [-p PASSWORD] [-e] [-x]

An AI controlled Roll20 character

options:
  -h, --help            show this help message and exit
  -c CF_CLEARANCE, --cf_clearance CF_CLEARANCE
                        cloudflare clearance token. See README.md for more information. Alternatively, put this in the environment variable $R20_CF_CLEARANCE
  -k APIKEY, --apikey APIKEY
                        openAI API key. Alternatively, put this in the environment variable $OPENAI_API_KEY
  -g GAMEID, --gameID GAMEID
                        ID of the game to be joined
  -u USERNAME, --username USERNAME
                        Roll20 email. Alternatively, put this in the environment variable $R20_EMAIL)
  -p PASSWORD, --password PASSWORD
                        Roll20 password. Alternatively, put this in the environment variable $R20_PASSWORD
  -e, --env             enable the use of a .env file for initialising environment variables
  -x, --headless        Start the webdriver in headless mode
```
Note: command-line arguments will override environment variables 

## Game ID
The `--gameID` argument takes the ID of the Roll20 game you want the bot to connect to. You can find this ID by opening you campaign/game's page and copying it out of the URL. The URL should be of the form `http(s)://app.roll20.net/campaigns/details/[Your game's ID]/[Your game's name]`.

## cf_clearance
This program does not use the Roll20 API. Instead, it uses browser automation ([selenium webdriver](https://www.selenium.dev/)) to interact with the Roll20 GUI. Roll20 uses [Cloudflare challenges](https://developers.cloudflare.com/firewall/cf-firewall-rules/cloudflare-challenges/) to keep out automated accounts. When a challenge is passed, that user is given [a cookie named `cf_clearance`](https://developers.cloudflare.com/waf/tools/challenge-passage/#how-it-works) containing a token which allows them to continue using the site without having to solve future challenges. After about 30 minutes, this cookie expires and the challenge will have to be completed again (though the account won't be interupted in-game).

Selenium can't pass Cloudflare challenges (though there exist forks which can - install one of those if you want to). To circumvent this, a `cf_clearance` token can be taken from another browser that *can* pass Cloudflare challenges and then that token can be used in the automated browser. This token is the value passed into roll20-bot's `--cf_clearance` argument or put in the `$R20_CF_CLEARANCE` environment variable (note: command-line arguments will override environment variables). To get a token:
1. Open a browser (not Internet Explorer ffs)
2. Open a new private/incognito window
3. Connect to [app.roll20.net](https://app.roll20.net)
4. Open 'Developer Tools' (or whatever it's called in your browser)
5. Open the 'Storage' tab (or wherever you can view the contents of cookies in your browser)
6. Open the 'Cookies' dropdown on the left sidebar and select the `https://app.roll20.net` option
7. Search for `cf_clearance` and copy its `value` field
8. Use this value for the `--cf_clearance` argument or the `$R20_CF_CLEARANCE` environment variable

## settings.yaml
This file is filled with example values. Replace them with your own.
### is_character
Roll20's websource does not differentiate between the originators of messages except by image (which can often change mid-game) and name. Thus roll20-bot cannot differentiate between the originators of messages except by their displayed names. It also cannot differentiate between player accounts and characters - this information needs to be specified explicitly on a per-game basis.

Each game is identified by its ID. If `enable_character_whitelist` is True, then any messages from names in `character_whitelist` will be considered as in-character, and all others as out-of-character. If `enable_character_blacklist` is True, then any messages from names in `character_blacklist` will be considered as out-of-character, and all others as in-character. If both `enable_character_whitelist` and `enable_character_blacklist` are True, then the whitelist will be applied minus any names in the blacklist.

### is_operator
The bot can be issued [commands](#in-game-commands) through Roll20 chat. You must specify who is allowed to issue commands for each game by adding the names of operators/non-operators to your game's operator whitelist/blacklist under `is_operator`. This works in the same way as [`is_character`](#is_character).

Important note: Roll20's websource does not differentiate between the originators of messages except by image and name. So this program only uses names to tell apart different accounts and different characters. Thus if more than one person or character shares the same in-chat name, then roll20-bot will treat them as the same account/character. If a non-operator changes the name of their account or character to that of an operator, they can then issue commands. So if you were counting on being able to keep the power of operator out of the hands of your co-players, it would be best to just disable it (`enable_operator_whitelist : True` and `operator_whitelist : []`).

### model
Which GPT model to use. See https://platform.openai.com/docs/models/overview for a list of models strings. Note: Currently, only chat-completions models work.
### character_descriptions:
Per-game, per-character system prompts. The system prompt is a good place to describe how you want the bot to behave, as well as a character and setting description. Games are identified by their ID and characters by their name.

### default_character_descriptions:
If the bot is playing a character whose name is not found under that game's section in [`character_descriptions`](#character_descriptions), then it will fall back to this. Each game has it's own default, identified by game ID. If the game's ID is not listed here then `default_character_descriptions.game_independent_default` will be used instead. Use `{name}` to refer to the character; it will be substituted with the character's name at runtime.

### bot_character_names
Defines which character the bot will play by default in each game. This can be changed during the game with the in-game `%character` command. Make sure the bot's Roll20 account has permission to play as the specified character.

## In-Game Commands
The bot can be operated through Roll20 chat. You must specify who is allowed to issue commands for each game in the `is_operator` section of the `settings.yaml` file.
Commands must be prefixed with `%`.
Use a command with the `--help` argument to see its help message.
The escape character is `\`.

### help:
USAGE: %help \
View command help

### poke:
USAGE: %poke \
Force the bot to respond.

### character: 
USAGE: %character [character's display name] \
Change which character the bot is controlling.

### system:
USAGE: %system [new system prompt] \
Change the system prompt. Omit the argument to view the current system prompt.\
System prompts changed in this manner will be lost when you change character. Use settings.yaml for a permanent system prompt.

### pause:
USAGE: %pause \
Stop posting in-character until the %resume command is given.

### resume:
USAGE: %resume \
Continue posting in-character.

### stop:
USAGE: %stop \
Terminate the program.
