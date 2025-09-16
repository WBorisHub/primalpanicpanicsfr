import os
import requests
import discord
from discord import app_commands
from discord.ext import commands

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
PLAYFAB_TITLE_ID = os.environ["PLAYFAB_TITLE_ID"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)
link_requests = {}  # stores Unity codes temporarily

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online as {bot.user}")

# ------------------ /linkcode ------------------
@bot.tree.command(name="linkcode", description="Link your Discord account to the game using the Unity code")
@app_commands.describe(code="6-digit code from Unity")
async def linkcode(interaction: discord.Interaction, code: str):
    data = link_requests.get(code)
    if not data:
        await interaction.response.send_message("❌ Invalid or expired code.", ephemeral=True)
        return

    url = f"https://{PLAYFAB_TITLE_ID}.playfabapi.com/Client/ExecuteCloudScript"
    headers = {"Content-Type": "application/json"}
    body = {
        "FunctionName": "LinkDiscordAccount",
        "FunctionParameter": {
            "Code": code,
            "DiscordId": str(interaction.user.id),
            "HWID": data["hwid"],
            "IP": data["ip"]
        },
        "GeneratePlayStreamEvent": True
    }

    r = requests.post(url, json=body, headers=headers)
    if r.status_code == 200 and r.json().get("FunctionResult", {}).get("success"):
        await interaction.response.send_message(f"✅ Linked successfully to PlayFab ID {data['playfab_id']}", ephemeral=True)
        del link_requests[code]
    else:
        await interaction.response.send_message("❌ Failed to link account.", ephemeral=True)

# ------------------ /unlink ------------------
@bot.tree.command(name="unlink", description="Unlink your Discord account from your PlayFab account")
async def unlink(interaction: discord.Interaction):
    url = f"https://{PLAYFAB_TITLE_ID}.playfabapi.com/Client/ExecuteCloudScript"
    headers = {"Content-Type": "application/json"}
    body = {
        "FunctionName": "UnlinkDiscordAccount",
        "FunctionParameter": {"DiscordId": str(interaction.user.id)},
        "GeneratePlayStreamEvent": True
    }

    r = requests.post(url, json=body, headers=headers)
    if r.status_code == 200 and r.json().get("FunctionResult", {}).get("success"):
        await interaction.response.send_message("✅ Unlinked successfully.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Failed to unlink account.", ephemeral=True)

# ------------------ /addlinkcode ------------------
@bot.tree.command(name="addlinkcode", description="Register a new link code from Unity")
@app_commands.describe(playfab_id="PlayFab ID", code="6-digit code", hwid="HWID", ip="IP")
async def addlinkcode(interaction: discord.Interaction, playfab_id: str, code: str, hwid: str, ip: str):
    link_requests[code] = {"playfab_id": playfab_id, "hwid": hwid, "ip": ip}
    await interaction.response.send_message(f"Code {code} registered.", ephemeral=True)

bot.run(DISCORD_TOKEN)
