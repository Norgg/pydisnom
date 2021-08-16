import traceback
from datetime import datetime, timedelta

from pony.orm import db_session
from db import Rule, User, Vote

messages = []
initial_rules = []


# Global variables that are used as rule context
discord_user = None
db_user = None
discord_message = None
channel = None
command = None
rest = None


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


async def run(rule):
    # Make an async function with the code and exec it
    exec_code = 'async def __ex(): ' + ''.join(f'\n    {line}' for line in rule.code.split('\n'))
    exec(exec_code)

    # Get `__ex` from local variables, call it and return the result
    return await locals()['__ex']()


@initial_rule()
async def run_rules():
    '''Runs all the other rules'''
    for rule in Rule.select(lambda rule: rule.status in ['initial', 'passed']).order_by(Rule.id):
        with db_session:
            try:
                await run(rule)
            except Exception as e:
                message(channel, f'Error running rule {rule.title}: {e}')
                traceback.print_exc()
    for to, msg in messages:
        await to.send(msg)
    messages.clear()


@initial_rule('list')
def list_rules():
    '''List all rules'''
    if command == 'list':
        rules_string = '\n'.join([f'**{rule.title}** ({rule.status}) - {rule.doc}' for rule in Rule.select()])
        message(channel, f'The current rules are:\n{rules_string}')


@initial_rule()
def show():
    '''Display details and code of a rule with !show [title]'''
    if command == 'show':
        rule = Rule.get(title=rest.strip().lower())
        if rule:
            message(channel, rule.markdown)


@initial_rule()
def propose():
    '''
    Propose a new rule with the title on the first line and code on subsequent lines, eg:
    !propose test rule
    if command == 'test': message(channel, 'test')
    '''
    if command == 'propose':
        lines = rest.splitlines()
        if len(lines) < 2:
            message(channel, 'Rules must have at least two lines')
            return

        title = rest.splitlines()[0].strip().lower()
        code = '\n'.join(rest.splitlines()[1:])

        if Rule.get(title=title):
            message(channel, f'A rule already exists called "{title}"')
            return

        # Extract docstring from proposed rule
        doc_func = 'def __func(): ' + ''.join(f'\n    {line}' for line in code.split('\n'))
        exec(doc_func)
        doc = locals()['__func'].__doc__

        rule = Rule(
            proposed_by=db_user,
            title=title,
            code=code,
            doc=doc,
            status='proposed'
        )
        message(channel, f'{rule.proposed_by.name} proposed rule {rule.title}')


@initial_rule()
def vote():
    '''Use !yay [title], !nay [title] or !abstain [title] to vote on a rule'''
    if command in ['yay', 'nay', 'abstain']:
        title = rest.strip().lower()
        rule = Rule.get(title=title)
        if rule:
            if rule.status == 'proposed':
                existing_vote = Vote.get(user=db_user, rule=rule)
                if existing_vote:
                    existing_vote.vote = command
                else:
                    Vote(user=db_user, rule=rule, vote=command)
                message(channel, f'{discord_user.name} voted {command} on {rule.title}')
            else:
                message(channel, 'Can only vote on rules that are still proposed')
        else:
            message(channel, f'Rule {title} not found')


@initial_rule()
def count():
    '''Tally up votes after a while and pass or reject rules if they have more than a minimum number of votes'''
    voting_duration = timedelta(minutes=1)
    min_votes = 1
    for rule in Rule.select(status='proposed'):
        time_diff = datetime.now() - rule.proposed_at
        if time_diff > voting_duration:
            message(channel, f'Counting votes for {rule.title}')
            if rule.yays + rule.nays < min_votes:
                message(channel, f'{rule.title} did not receive enough total votes ({rule.yays} - {rule.nays})')
                rule.delete()
            elif rule.yays > rule.nays:
                if rule.replaces:
                    Rule.get(title=rule.replaces).delete()
                    rule.title = rule.replaces
                    rule.replaces = None
                    rule.status = 'passed'
                    rule.passed_at = datetime.now()
                    message(channel, f'{rule.title} has been replaced ({rule.yays} - {rule.nays})!')
                elif rule.deletes:
                    Rule.get(title=rule.deletes).delete()
                    rule.delete()
                    message(channel, f'{rule.deletes} has been deleted ({rule.yays} - {rule.nays})!')
                else:
                    rule.status = 'passed'
                    message(channel, f'{rule.title} has passed ({rule.yays} - {rule.nays})!')
            else:
                message(channel, f'{rule.title} has been rejected ({rule.yays} - {rule.nays})!')
                rule.delete()


@initial_rule()
def replace():
    '''
    Propose replacing a rule with a new rule, eg:
    !replace test
    \'''new version of test\'''
    if command == 'test': message(channel, 'hello!')
    '''
    if command == 'replace':
        lines = rest.splitlines()
        if len(lines) < 2:
            message(channel, 'Rules must have at least two lines')
            return

        replaces_title = rest.splitlines()[0].strip().lower()
        title = f'replace {replaces_title}'
        code = '\n'.join(rest.splitlines()[1:])

        if not Rule.get(title=replaces_title):
            message(channel, f'Couldn\'t find rule to replace: {replaces_title}')
            return

        if Rule.get(title=title):
            message(channel, f'A vote to replace {replaces_title} is already in progress')
            return

        # Extract docstring from proposed rule
        doc_func = 'def __func(): ' + ''.join(f'\n    {line}' for line in code.split('\n'))
        exec(doc_func)
        doc = locals()['__func'].__doc__

        rule = Rule(
            proposed_by=db_user,
            title=title,
            code=code,
            doc=doc,
            replaces=replaces_title,
            status='proposed'
        )
        message(channel, f'{rule.proposed_by.name} proposed to {rule.title}')


@initial_rule()
def delete():
    '''Propose deletion of a rule: !delete [title]'''
    if command == 'delete':
        deletes_title = rest.splitlines()[0].strip().lower()
        title = f'delete {deletes_title}'

        if not (deletes_title):
            message(channel, 'Delete which rule?')
            return

        if not Rule.get(title=deletes_title):
            message(channel, f'Couldn\'t find rule to delete: {deletes_title}')
            return

        if Rule.get(title=title):
            message(channel, f'A vote to delete {deletes_title} is already in progress')
            return

        rule = Rule(
            proposed_by=db_user,
            title=title,
            code='',
            doc=f'Delete {deletes_title}',
            deletes=deletes_title,
            status='proposed'
        )
        message(channel, f'{rule.proposed_by.name} proposed to {rule.title}')
