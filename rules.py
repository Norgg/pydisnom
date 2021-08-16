import traceback
from datetime import datetime, timedelta

from pony.orm import db_session
from db import Rule, Vote

messages = []
initial_rules = []


def initial_rule(title=None):
    def decorator(func):
        if title is not None:
            func.__name__ = title
        initial_rules.append(func)
        return func
    return decorator


def message(to, message):
    '''Send a message to a channel or user'''
    messages.append((to, message))


async def run(rule, context):
    # Make an async function with the code and `exec` it
    exec_code = (
        'async def __ex(context): ' +
        ''.join(f'\n    {line}' for line in rule.code.split('\n'))
    )
    exec(exec_code)

    # Get `__ex` from local variables, call it and return the result
    return await locals()['__ex'](context)


@initial_rule()
async def run_rules(context):
    '''Runs all the other rules'''
    for rule in Rule.select(lambda rule: rule.status in ['initial', 'passed']).order_by(Rule.id):
        with db_session:
            try:
                await run(rule, context)
            except Exception as e:
                message(context.channel, f'Error running rule {rule.title}: {e}')
                traceback.print_exc()
    for to, msg in messages:
        await to.send(msg)
    messages.clear()


@initial_rule('list')
def list_rules(context):
    '''List all rules'''
    if context.command == 'list':
        rules_string = '\n'.join([f'**{rule.title}** ({rule.status}) - {rule.doc}' for rule in Rule.select()])
        message(context.channel, f'The current rules are:\n{rules_string}')


@initial_rule()
def show(context):
    '''Display details of a rule with !show [title]'''
    if context.command == 'show':
        rule = Rule.get(title=context.rest.strip().lower())
        if rule:
            message(context.channel, rule.markdown)


@initial_rule()
def propose(context):
    '''
    Propose a new rule with the title on the first line and code on subsequent lines, eg:
    !propose test rule
    message(context.channel, 'test')
    '''
    if context.command == 'propose':
        lines = context.rest.splitlines()
        if len(lines) < 2:
            message(context.channel, 'Rules must have at least two lines')
            return

        title = context.rest.splitlines()[0].strip().lower()
        code = '\n'.join(context.rest.splitlines()[1:])

        if Rule.get(title=title):
            message(context.channel, f'A rule already exists called "{title}"')
            return

        # Extract docstring from proposed rule
        doc_func = 'def __func(context): ' + ''.join(f'\n    {line}' for line in code.split('\n'))
        exec(doc_func)
        doc = locals()['__func'].__doc__

        rule = Rule(
            proposed_by=context.db_user,
            title=title,
            code=code,
            doc=doc,
            status='proposed'
        )
        message(context.channel, f'{rule.proposed_by.last_known_name} proposed rule {rule.title}')


@initial_rule()
def vote(context):
    '''Use !yay [title], !nay [title] or !abstain [title] to vote on a rule'''
    if context.command in ['yay', 'nay', 'abstain']:
        title = context.rest.strip().lower()
        rule = Rule.get(title=title)
        if rule:
            if rule.status == 'proposed':
                existing_vote = Vote.get(user=context.db_user, rule=rule)
                if existing_vote:
                    existing_vote.vote = context.command
                else:
                    Vote(user=context.db_user, rule=rule, vote=context.command)
                message(context.channel, f'{context.discord_user.name} voted {context.command} on {rule.title}')
            else:
                message(context.channel, 'Can only vote on rules that are still proposed')
        else:
            message(context.channel, f'Rule {title} not found')


@initial_rule()
def count(context):
    '''Tally up votes after [voting_duration] and pass or reject rules if they have more than [min_votes]'''
    voting_duration = timedelta(minutes=1)
    min_votes = 1
    for rule in Rule.select(status='proposed'):
        time_diff = datetime.now() - rule.proposed_at
        if time_diff > voting_duration:
            message(context.channel, f'Counting votes for {rule.title}')
            if rule.yays + rule.nays < min_votes:
                message(context.channel, f'{rule.title} did not receive enough total votes ({rule.yays} - {rule.nays})')
                rule.delete()
            elif rule.yays > rule.nays:
                if rule.replaces:
                    Rule.get(title=rule.replaces).delete()
                    rule.title = rule.replaces
                    rule.replaces = None
                    rule.status = 'passed'
                    message(context.channel, f'{rule.title} has been replaced ({rule.yays} - {rule.nays})!')
                else:
                    rule.status = 'passed'
                    message(context.channel, f'{rule.title} has passed ({rule.yays} - {rule.nays})!')
            else:
                message(context.channel, f'{rule.title} has been rejected ({rule.yays} - {rule.nays})!')
                rule.delete()


@initial_rule()
def replace(context):
    '''
    Propose replacing a rule with a new rule, eg:
    !replace test
    \'''new version of test\'''
    message(context.channel, 'hello')
    '''
    if context.command == 'replace':
        lines = context.rest.splitlines()
        if len(lines) < 2:
            message(context.channel, 'Rules must have at least two lines')
            return

        replaces_title = context.rest.splitlines()[0].strip().lower()
        title = f'replace {replaces_title}'
        code = '\n'.join(context.rest.splitlines()[1:])

        if not Rule.get(title=replaces_title):
            message(context.channel, f'Couldn\'t find rule to replace: {replaces_title}')
            return

        if Rule.get(title=title):
            message(context.channel, f'A vote to replace {replaces_title} is already in progress')
            return

        # Extract docstring from proposed rule
        doc_func = 'def __func(context): ' + ''.join(f'\n    {line}' for line in code.split('\n'))
        exec(doc_func)
        doc = locals()['__func'].__doc__

        rule = Rule(
            proposed_by=context.db_user,
            title=title,
            code=code,
            doc=doc,
            replaces=replaces_title,
            status='proposed'
        )
        message(context.channel, f'{rule.proposed_by.last_known_name} proposed to {rule.title}')
