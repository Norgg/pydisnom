import traceback

from pony.orm import db_session
from db import Rule
messages = []


async def async_exec(code, context):
    # Make an async function with the code and `exec` it
    exec_code = (
        'async def __ex(context): ' +
        ''.join(f'\n    {line}' for line in code.split('\n'))
    )
    exec(exec_code)

    # Get `__ex` from local variables, call it and return the result
    return await locals()['__ex'](context)


def message(to, message):
    """Send a message to a channel or user"""
    messages.append((to, message))


async def run_rules(context):
    for rule in Rule.select(lambda rule: rule.status in ['initial', 'passed']).order_by(Rule.id):
        with db_session:
            try:
                await async_exec(rule.code, context)
            except Exception as e:
                message(context.channel, f'Error running rule {rule.title}: {e}')
                traceback.print_exc()
    for to, msg in messages:
        await to.send(msg)
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
