import traceback
from datetime import datetime, timedelta

from pony.orm import db_session
from db import Rule, Vote
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
        rules_string = '\n'.join([f'**{rule.title}**: {rule.status}' for rule in Rule.select()])
        message(context.channel, f'The current rules are:\n{rules_string}')


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


def approve(context):
    if context.command == 'approve':
        title = context.rest.strip().lower()
        rule = Rule.get(title=title)
        if rule:
            if rule.status == 'proposed':
                Vote(user=context.db_user, rule=rule, vote='yay')
                message(context.channel, f'Rule {title} approved by {context.discord_user.name}')
            else:
                message(context.channel, 'Can only vote on rules that are still proposed')
        else:
            message(context.channel, f'Rule {title} not found')


def reject(context):
    if context.command == 'reject':
        title = context.rest.strip().lower()
        rule = Rule.get(title=title)
        if rule:
            if rule.status == 'proposed':
                Vote(user=context.db_user, rule=rule, vote='nay')
                message(context.channel, f'Rule {title} rejected by {context.discord_user.name}')
            else:
                message(context.channel, 'Can only vote on rules that are still proposed')
        else:
            message(context.channel, f'Rule {title} not found')


def abstain(context):
    if context.command == 'abstain':
        title = context.rest.strip().lower()
        rule = Rule.get(title=title)
        if rule:
            if rule.status == 'proposed':
                Vote(user=context.db_user, rule=rule, vote='abstain')
                message(context.channel, f'{context.discord_user.name} abstained on {rule.title}')
            else:
                message(context.channel, 'Can only vote on rules that are still proposed')
        else:
            message(context.channel, f'Rule {title} not found')


def count(context):
    for rule in Rule.select(status='proposed'):
        time_diff = datetime.now() - rule.proposed_at
        if time_diff > timedelta(minutes=1):
            message(context.channel, f'Counting votes for {rule.title}')
            yay_votes = Vote.select(rule=rule, vote='yay').count()
            nay_votes = Vote.select(rule=rule, vote='nay').count()
            min_votes = 1
            if yay_votes + nay_votes < min_votes:
                rule.status = 'rejected'
                message(context.channel, f'{rule.title} did not receive enough total votes ({yay_votes} - {nay_votes})')
            elif yay_votes > nay_votes:
                rule.status = 'passed'
                message(context.channel, f'{rule.title} has passed ({yay_votes} - {nay_votes})!')
            else:
                rule.status = 'rejected'
                message(context.channel, f'{rule.title} has been rejected ({yay_votes} - {nay_votes})!')
