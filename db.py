from datetime import datetime

from pony.orm import Database, Optional, Json, PrimaryKey, Required, Set, sql_debug


db = Database('sqlite', 'pydisnom.db', create_db=True)


class User(db.Entity):
    discord_id = PrimaryKey(str)
    name = Optional(str)
    data = Required(Json, default=dict)
    proposed_rules = Set("Rule")
    votes = Set("Vote")

    @classmethod
    def get_or_create(cls, id):
        user = cls.get(discord_id=id)
        if user is None:
            user = cls(discord_id=id)
            print(f'created user {id}')
        return user


class Rule(db.Entity):
    title = Required(str, unique=True)
    code = Optional(str, autostrip=False)
    status = Required(str)
    doc = Optional(str, nullable=True)
    replaces = Optional(str, nullable=True)
    deletes = Optional(str, nullable=True)
    proposed_by = Optional(User)
    proposed_at = Optional(datetime, default=datetime.now)
    passed_at = Optional(datetime)
    data = Required(Json, default=dict)
    votes = Set("Vote")

    @property
    def markdown(self):
        if self.status == 'proposed':
            status_string = f'{self.status} at {self.proposed_at:%c} by {self.proposed_by.name}'
        elif self.status == 'passed':
            status_string = f'{self.status} at {self.passed_at:%c}'
        else:
            status_string = f'{self.status}'

        vote_string = f'{self.yays} yay - {self.nays} nay'
        return f'**{self.title}** ({status_string}):\n{vote_string}\n{self.doc}```python\n{self.code}\n```'

    @property
    def yays(self):
        return Vote.select(rule=self, vote='yay').count()

    @property
    def nays(self):
        return Vote.select(rule=self, vote='nay').count()


class Vote(db.Entity):
    user = Required(User)
    rule = Required(Rule)
    vote = Required(str)
    at = Optional(datetime, default=datetime.now)


class Store(db.Entity):
    data = Required(Json, default=dict)

    @classmethod
    def instance(cls):
        store = cls.get()
        if not store:
            store = Store()
        return store


# sql_debug(True)
db.generate_mapping(create_tables=True)
