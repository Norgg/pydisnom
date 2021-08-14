from datetime import datetime

from pony.orm import Database, Optional, PrimaryKey, Required, Set, sql_debug


db = Database('sqlite', 'pydisnom.db', create_db=True)


class User(db.Entity):
    discord_id = PrimaryKey(str)
    last_known_name = Optional(str)
    proposed_rules = Set("Rule")
    votes = Set("Vote")

    @classmethod
    def get_or_create(cls, id):
        user = cls.get(discord_id=id)
        if user is None:
            user = cls(discord_id=id)
            print(f'Created user {id}')
        return user


class Rule(db.Entity):
    title = Required(str)
    code = Required(str, autostrip=False)
    status = Required(str)
    proposed_by = Optional(User)
    proposed_at = Optional(datetime, default=datetime.now)
    passed_at = Optional(datetime)
    votes = Set("Vote")

    @property
    def markdown(self):
        return f'**{self.title}** ({self.status}):\n```python\n{self.code}\n```'


class Vote(db.Entity):
    user = Required(User)
    rule = Required(Rule)
    at = Optional(datetime)


sql_debug(True)
db.generate_mapping(create_tables=True)
