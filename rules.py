import inspect
import traceback
from datetime import datetime, timedelta

from pony.orm import commit, db_session
from db import Rule, User, Vote

messages = []
initial_rules = []


# Global variables that are used as rule context
user = None
channel = None
command = None
rest = None


def save_initial_rules(channel):
    with db_session:
        if Rule.select().count() == 0:
            print(f'No rules found, sending intro text to {channel}')
            message(channel, '''
**+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++**
**Welcome to pydisnom, setting up initial rules to start a new game!**
As a first rule you could try out something like:
```python
!propose hello
if command == 'hello':
    message(channel, f'hiya {user.name}!')
```
You can then vote on it with `!yay hello` or `!nay hello`
In 10 minutes it will either pass or fail and become a new game rule
Game rules are run every 10 seconds and whenever someone types a command
`!list` will list all current rules and `!show [title]` will give more details
**+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++**
''')

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


async def run_rules():
    '''Runs all the rules'''
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
    '''List all rules with `!list`'''
    if command in ['list', 'help']:
        rules_string = '\n'.join([f'**{rule.title}** (status: {rule.status}): {rule.doc}' for rule in Rule.select()])
        message(channel, f'The current rules are:\n{rules_string}')


@initial_rule()
def show():
    '''Display details and code of a rule with `!show [title]`'''
    if command == 'show':
        rule = Rule.get(title=rest.strip().lower())
        if rule:
            message(channel, rule.markdown)


@initial_rule()
def propose():
    '''
        Propose a new rule written in python, eg this will reply with 'hiya!' whenever someone says `!hello`:
        !propose hello
        if command == 'hello': message(channel, 'hiya!')
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
            proposed_by=user,
            title=title,
            code=code,
            doc=doc,
            status='proposed'
        )
        message(channel, f'{rule.proposed_by.name} proposed rule {rule.title}')


@initial_rule()
def vote():
    '''Use `!yay [title]`, `!nay [title]` to vote on a rule'''
    if command in ['yay', 'nay']:
        title = rest.strip().lower()
        rule = Rule.get(title=title)
        if rule:
            if rule.status == 'proposed':
                existing_vote = Vote.get(user=user, rule=rule)
                if existing_vote:
                    existing_vote.vote = command
                else:
                    Vote(user=user, rule=rule, vote=command)
                message(channel, f'{user.name} voted {command} on {rule.title}')
            else:
                message(channel, 'Can only vote on rules that are still proposed')
        else:
            message(channel, f'Rule {title} not found')


@initial_rule()
def count():
    '''Runs automatically to count votes after a while and pass or reject rules'''
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
    '''Propose replacing a rule with a new rule with `!replace` in the same way as `!propose`'''
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
            proposed_by=user,
            title=title,
            code=code,
            doc=doc,
            replaces=replaces_title,
            status='proposed'
        )
        message(channel, f'{rule.proposed_by.name} proposed to {rule.title}')


@initial_rule()
def delete():
    '''Propose deletion of a rule: `!delete [title]`'''
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
            proposed_by=user,
            title=title,
            code='',
            doc=f'Delete {deletes_title}',
            deletes=deletes_title,
            status='proposed'
        )
        message(channel, f'{rule.proposed_by.name} proposed to {rule.title}')


# @initial_rule()
def victory():
    '''If a player has won then reset the game'''
    for user in User.select():
        if user.data.get('won'):
            message(channel, f'Congrats to {user.name} for winning the game!')
            message(channel, 'Resetting rules...')
            Rule.select().delete()  # Delete all the rules
            commit()
            save_initial_rules()
