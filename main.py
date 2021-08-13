#!/usr/bin/env python

import discord

client = discord.Client()
pdn_guild = None


def main():
    print("""pydisnom
---o<--
|     |
|     |
-------
""")
    token = open('token').read()
    client.run(token)


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
    if message.content.startswith('!'):
        await message.channel.send('heya')


if __name__ == '__main__':
    main()
