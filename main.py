import os

from r20 import Roll20
from controller import Controller
from globals import *

import argparse
from dotenv import load_dotenv, find_dotenv

parser = argparse.ArgumentParser(
    prog='r20-bot',
    description='An AI Roll20 character')

parser.add_argument('-c', '--cf_clearance', help=f'cloudflare clearance token. See README.md for more information. Alternatively, put this in the environment variable ${ENV_CF_CLEARANCE}')
parser.add_argument('-k', '--apikey', help=f'openAI API key. Alternatively, put this in the environment variable ${ENV_API_KEY}')
parser.add_argument('-g', '--gameID', help='ID of the game to be joined')
parser.add_argument('-u', '--username', help=f"Roll20 email. Alternatively, put this in the environment variable ${ENV_R20_EMAIL})")
parser.add_argument('-p', '--password', help=f"Roll20 password. Alternatively, put this in a environment variable ${ENV_R20_PASSWORD}")
parser.add_argument('-e', '--env', action='store_true', help="enable the use of a .env file for initialising environment variables")
parser.add_argument('-x', '--headless', action='store_true', help='Start the webdriver in headless mode')

def main():
    args = parser.parse_args()
    

    if(args.env):
        load_dotenv(find_dotenv())

    for v in [ENV_R20_EMAIL, ENV_R20_PASSWORD, ENV_API_KEY, ENV_CF_CLEARANCE]:
        if(os.getenv(v) == None):
            os.environ[v] = ''

    driver_args = []
    if(args.headless):
        driver_args.append('--headless')

    r20 = Roll20(driver_args=driver_args)
    os.environ[ENV_R20_EMAIL] = (args.username if args.username != None else os.environ[ENV_R20_EMAIL])
    os.environ[ENV_R20_PASSWORD] = (args.password if args.password != None else os.environ[ENV_R20_PASSWORD])
    os.environ[ENV_API_KEY] = (args.apikey if args.apikey != None else os.environ[ENV_API_KEY])
    os.environ[ENV_CF_CLEARANCE] = (args.cf_clearance if args.cf_clearance != None else os.environ[ENV_CF_CLEARANCE])
    r20.login(use_env=True)

    if(args.gameID == None):
        gameID = input('Provide the game ID of the game you want to join: ')
    else:
        gameID = args.gameID.strip()
    r20.join_game(gameID=gameID)
    # login complete
    print('Initialising...')
    controller = Controller(r20=r20, gameID=gameID) # type: ignore
    controller.backend()
    del r20

if __name__ == '__main__':
    main()
