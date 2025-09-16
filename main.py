import os
import asyncio
import requests
import discord

DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN"
WEBHOOK_CHANNEL_ID = 123456789012345678
PLAYFAB_TITLE_ID = "YOUR_PLAYFAB_TITLE_ID"
PLAYFAB_SECRET = "YOUR_PLAYFAB_SECRET"
SEARCH_LIMIT = 200

intents = discord.Intents.default()
intents.messages = True
client = discord.Client(intents=intents)

def find_code_in_messages(channel, code):
    msgs = []
    try:
        msgs = asyncio.run(channel.history(limit=SEARCH_LIMIT).flatten())
    except:
        msgs = asyncio.run(channel.history(limit=SEARCH_LIMIT).flatten())
    for m in msgs:
        if code in m.content:
            return m.content
    return None

def extract_field(content, field):
    for line in content.splitlines():
        if line.startswith(field):
            return line.split(":",1)[1].strip()
    return None

def update_playfab_user(playfab_id, discord_id):
    url = f"https://{PLAYFAB_TITLE_ID}.playfabapi.com/Admin/UpdateUserInternalData"
    headers = {"X-SecretKey": PLAYFAB_SECRET, "Content-Type": "application/json"}
    body = {"PlayFabId": playfab_id, "Data": {"discordId": str(discord_id), "discordLinked": "true"}}
    r = requests.post(url, json=body, headers=headers)
    return r.status_code == 200

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith("!link "):
        code = message.content.split(" ",1)[1].strip()
        channel = client.get_channel(WEBHOOK_CHANNEL_ID)
        found = None
        async for m in channel.history(limit=SEARCH_LIMIT):
            if code in m.content:
                found = m.content
                break
        if not found:
            await message.channel.send("Code not found")
            return
        playfab_id = extract_field(found, "PlayFabId")
        if not playfab_id:
            await message.channel.send("PlayFabId not found in webhook message")
            return
        ok = update_playfab_user(playfab_id, message.author.id)
        if ok:
            await message.channel.send("Linked")
            try:
                await message.author.send("Your game account is now linked")
            except:
                pass
        else:
            await message.channel.send("Failed to update PlayFab")

client.run(DISCORD_TOKEN)
