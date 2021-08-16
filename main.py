#!/usr/bin/env python

import asyncio
from box import Box
import discord
import inspect
from pony.orm import db_session
from db import User, Rule, Vote
from rules import async_exec, run_rules, list_rules, show, propose, approve, reject, abstain, count

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
async def on_message(message):
    with db_session:
        if message.content.startswith('!'):
            await _run_rules(message)


async def rule_loop():
    while True:
        with db_session:
            await _run_rules()
            await asyncio.sleep(10)


async def _run_rules(message=None):
    # Set up context object for rules
    context = Box()

    if message:
        context.discord_user = message.author
        context.db_user = User.get_or_create(str(message.author.id))
        context.db_user.last_known_name = message.author.name
        context.message = message
        context.channel = message.channel
        context.command = message.content.split(' ')[0][1:].lower()
        context.rest = message.content[1+len(context.command):]
    else:
        context.channel = game_channel
        context.command = None

    print('running rules')
    run_rules = Rule.get(title='run_rules')
    await async_exec(run_rules.code, context)


def save_initial_rules():
    rules = [run_rules, list_rules, show, propose, approve, reject, abstain, count]
    with db_session:
        for rule in rules:
            if (Rule.get(title=rule.__name__)):
                continue
            code = inspect.getsource(rule)
            code = '\n'.join(code.splitlines()[1:])
            status = 'fixed' if rule.__name__ == 'run_rules' else 'initial'
            Rule(title=rule.__name__, code=code, status=status)


if __name__ == '__main__':
    main()
