#!/usr/bin/env python

import asyncio
from box import Box
import discord
import inspect
from pony.orm import db_session
from db import User, Rule, Vote
from rules import initial_rules, async_exec, message

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
    save_initial_rules()
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
async def on_message(msg):
    with db_session:
        if msg.content.startswith('!'):
            await _run_rules(msg)


async def rule_loop():
    while True:
        with db_session:
            await _run_rules()
            await asyncio.sleep(10)


async def _run_rules(msg=None):
    # Set up context object for rules
    context = Box()

    if msg:
        context.discord_user = msg.author
        context.db_user = User.get_or_create(str(msg.author.id))
        context.db_user.last_known_name = msg.author.name
        context.message = msg
        context.channel = msg.channel
        context.command = msg.content.split(' ')[0][1:].lower()
        context.rest = msg.content[1+len(context.command):]
    else:
        context.channel = game_channel
        context.command = None

    print('running rules')
    run_rules = Rule.get(title='run_rules')
    await async_exec(run_rules.code, context)


def save_initial_rules():
    with db_session:
        for rule in initial_rules:
            code = inspect.getsource(rule)
            code = '\n'.join(code.splitlines()[2:])
            status = 'fixed' if rule.__name__ == 'run_rules' else 'initial'

            existing_rule = Rule.get(title=rule.__name__)
            if (existing_rule):
                print(f'updating rule: {rule.__name__}')
                existing_rule.code = code
                existing_rule.doc = rule.__doc__
            else:
                print(f'adding initial rule: {rule.__name__}')
                Rule(title=rule.__name__, code=code, status=status, doc=rule.__doc__)


if __name__ == '__main__':
    main()
