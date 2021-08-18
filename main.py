#!/usr/bin/env python

import asyncio
import discord
from pony.orm import db_session
from db import User, Rule
import rules

run_lock = asyncio.Lock()
client = discord.Client()
pdn_guild = None
game_channel = None


def main():
    print("""pydisnom
---o<--
|     |
|     |
-------
""")
    token = open('token').read()
    rules.save_initial_rules()
    client.run(token)


@client.event
async def on_ready():
    print('connected')
    # Find the pydisnom server
    for guild in client.guilds:
        if guild.name == 'pydisnom':
            global pdn_guild
            pdn_guild = guild
            print(f'found server: {pdn_guild.name}')
            break

    # Find the game channel
    for channel in pdn_guild.channels:
        if channel.name == 'testing':
            global game_channel
            game_channel = channel
            break

    client.loop.create_task(rule_loop())


@client.event
async def on_message(message):
    with db_session:
        if message.channel == game_channel and message.content.startswith('!'):
            print('running rules due to command')
            await _run_rules(message)


async def rule_loop():
    while True:
        with db_session:
            print('running rules tick')
            await _run_rules()
            await asyncio.sleep(10)


async def _run_rules(message=None):
    # Set up context object for rules
    if message:
        rules.user = User.get_or_create(str(message.author.id))
        rules.user.name = message.author.name
        rules.channel = message.channel
        rules.command = message.content.split(' ')[0][1:].lower()
        rules.rest = message.content[1+len(rules.command):]
    else:
        rules.user = None
        rules.channel = game_channel
        rules.command = None
        rules.rest = None

    async with run_lock:
        await rules.run_rules()


if __name__ == '__main__':
    main()
