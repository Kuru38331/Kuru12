"""Interactive startup; token is kept only in this process environment."""
import getpass
import os
from pathlib import Path
import runpy

os.chdir(Path(__file__).resolve().parent)
if not os.getenv('DISCORD_BOT_TOKEN'):
    token = getpass.getpass('Paste Discord Bot Token (hidden): ').strip()
    if not token:
        raise SystemExit('A Bot Token is required.')
    os.environ['DISCORD_BOT_TOKEN'] = token
if not os.getenv('DISCORD_GUILD_ID'):
    guild = input('Test server ID (Enter to skip): ').strip()
    if guild:
        if not guild.isascii() or not guild.isdecimal():
            raise SystemExit('Server ID must contain only digits.')
        os.environ['DISCORD_GUILD_ID'] = guild
runpy.run_path('bot.py', run_name='__main__')
