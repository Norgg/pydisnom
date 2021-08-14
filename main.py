#!/usr/bin/env python

from box import Box
import discord
import inspect
from pony.orm import db_session
from db import db, User, Rule

client = discord.Client()
pdn_guild = None
messages = []


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


def message(to, message):
    """Send a message to a channel or user"""
    messages.append((to, message))


@client.event
async def on_ready():
    print('connected')
    # Find the pydisnom server
    for guild in client.guilds:
        if guild.name == 'pydisnom':
            pdn_guild = guild
            print(f'found server: {pdn_guild.name}')
            break


@client.event
async def on_message(message):
    with db_session:
        if message.content.startswith('!'):

            # Set up context object for rules
            context = Box()
            context.discord_user = message.author
            context.db_user = User.get_or_create(str(message.author.id))
            context.db_user.last_known_name = message.author.name
            context.message = message
            context.channel = message.channel
            context.command = message.content.split(' ')[0][1:].lower()
            context.rest = message.content[1+len(context.command):]

            run_rules = Rule.get(title='run_rules')
            await async_exec(run_rules.code, context)


def save_initial_rules():
    rules = [run_rules, list_rules, show, propose]
    with db_session:
        for rule in rules:
            if (Rule.get(title=rule.__name__)):
                continue
            code = inspect.getsource(rule)
            code = '\n'.join(code.splitlines()[1:])
            print(code)
            status = 'fixed' if rule.__name__ == 'run_rules' else 'initial'
            Rule(title=rule.__name__, code=code, status=status)


async def async_exec(code, context):
    # Make an async function with the code and `exec` it
    print(code)

    exec_code = (
        'async def __ex(context): ' +
        ''.join(f'\n    {line}' for line in code.split('\n'))
    )

    print(exec_code)
    exec(exec_code)

    # Get `__ex` from local variables, call it and return the result
    return await locals()['__ex'](context)


async def run_rules(context):
    for rule in Rule.select(lambda rule: rule.status in ['initial', 'passed']).order_by(Rule.id):
        with db_session:
            await async_exec(rule.code, context)
    for to, message in messages:
        await to.send(message)
    messages.clear()


def list_rules(context):
    if context.command == 'list':
        message(context.channel, '\n'.join([f'**{rule.title}**: {rule.status}' for rule in Rule.select()]))


def show(context):
    if context.command == 'show':
        rule = Rule.get(title=context.rest.strip().lower())
        if rule:
            message(context.channel, rule.markdown)


def propose(context):
    if context.command == 'propose':
        lines = context.rest.splitlines()
        if len(lines) < 2:
            message(context.channel, 'Rules must have at least two lines.')
            return

        title = context.rest.splitlines()[0].strip().lower()

        if Rule.get(title=title):
            message(context.channel, f'A rule already exists called "{title}"')

        rule = Rule(
            proposed_by=context.db_user,
            title=title,
            code='\n'.join(context.rest.splitlines()[1:]),
            status='proposed'
        )
        message(context.channel, f'{rule.proposed_by.last_known_name} proposed rule {rule.title}')


if __name__ == '__main__':
    main()
