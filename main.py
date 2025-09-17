import os
import json
import requests
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import random

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DB_FILE = "link_codes.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")

if not DISCORD_TOKEN or not LOG_WEBHOOK_URL:
    raise ValueError("DISCORD_TOKEN and LOG_WEBHOOK_URL must be set!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        link_requests = json.load(f)
else:
    link_requests = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(link_requests, f, indent=4)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online as {bot.user}")

@bot.tree.command(name="linkcode", description="Link your Discord account using Unity code")
@app_commands.describe(code="6-digit code from Unity")
async def linkcode(interaction: discord.Interaction, code: str):
    data = link_requests.get(code)
    if not data:
        await interaction.response.send_message("❌ Invalid or expired code.", ephemeral=True)
        return

    data["discord_id"] = str(interaction.user.id)
    data["linked_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    data["discordLinked"] = True
    save_db()

    embed = discord.Embed(
        title="✅ Player Linked!",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Master PlayFab ID", value=data.get("playfab_id","N/A"), inline=False)
    embed.add_field(name="HWID", value=data.get("hwid","N/A"), inline=False)
    embed.add_field(name="IP", value=data.get("ip","N/A"), inline=False)
    embed.add_field(name="Link Code", value=code, inline=False)
    embed.add_field(name="Discord ID", value=interaction.user.id, inline=False)
    embed.add_field(name="Status", value="🔗 Linked", inline=False)

    try:
        requests.post(LOG_WEBHOOK_URL, json={"embeds": [embed.to_dict()]}, timeout=5)
    except:
        pass

    del link_requests[code]
    save_db()
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="addlinkcode", description="Manually add a link code")
@app_commands.describe(playfab_id="PlayFab ID", code="6-digit code", hwid="HWID", ip="IP")
async def addlinkcode(interaction: discord.Interaction, playfab_id: str, code: str, hwid: str, ip: str):
    link_requests[code] = {"playfab_id": playfab_id, "hwid": hwid, "ip": ip, "discord_id": None, "discordLinked": False}
    save_db()
    embed = discord.Embed(
        title="✅ Code Registered",
        description=f"Code `{code}` registered for PlayFab ID `{playfab_id}`",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="status", description="Check if your Discord is linked")
async def status(interaction: discord.Interaction):
    for code, data in link_requests.items():
        if data.get("discord_id") == str(interaction.user.id):
            status = "🔗 Linked" if data.get("discordLinked") else "❌ Unlinked"
            embed = discord.Embed(
                title="📌 Link Status",
                color=discord.Color.orange()
            )
            embed.add_field(name="PlayFab ID", value=data.get("playfab_id","N/A"), inline=False)
            embed.add_field(name="HWID", value=data.get("hwid","N/A"), inline=False)
            embed.add_field(name="IP", value=data.get("ip","N/A"), inline=False)
            embed.add_field(name="Status", value=status, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    await interaction.response.send_message("⚠️ No link record found.", ephemeral=True)

bot.run(DISCORD_TOKEN)
