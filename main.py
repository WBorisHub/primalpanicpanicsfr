import os
import json
import requests
import random
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from flask import Flask, request, jsonify
from datetime import datetime
import threading
import sys

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DB_FILE = "link_codes.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")
BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", 0))
AUTHORIZE_URL = "https://discord.com/oauth2/authorize?client_id=1417616334631731310"

if not DISCORD_TOKEN or not LOG_WEBHOOK_URL:
    raise ValueError("DISCORD_TOKEN and LOG_WEBHOOK_URL must be set!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)
app = Flask(__name__)

if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        link_requests = json.load(f)
else:
    link_requests = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(link_requests, f, indent=4)

def log_webhook(embed):
    try:
        requests.post(LOG_WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except:
        pass

def log_all_linkcodes_embed():
    embed = {
        "title": "📄 All Registered Link Codes",
        "color": 0x00ff00,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": []
    }
    for code, data in link_requests.items():
        embed["fields"].append({
            "name": f"Code: {code}",
            "value": (
                f"PlayFab ID: {data.get('playfab_id','N/A')}\n"
                f"HWID: {data.get('hwid','N/A')}\n"
                f"IP: {data.get('ip','N/A')}\n"
                f"Discord Linked: {data.get('discordLinked', False)}"
            ),
            "inline": False
        })
    return embed

@app.route("/")
def home():
    return "Bot server is running!"

@app.route("/register_linkcode", methods=["POST"])
def register_linkcode():
    data = request.get_json()
    if not data or "playfab_id" not in data or "hwid" not in data or "ip" not in data:
        return jsonify({"success": False, "error": "Missing fields"}), 400

    code = str(random.randint(100000, 999999))
    link_requests[code] = {
        "playfab_id": data["playfab_id"],
        "hwid": data["hwid"],
        "ip": data["ip"],
        "discord_id": None,
        "discordLinked": False
    }
    save_db()
    log_webhook(log_all_linkcodes_embed())
    return jsonify({"success": True, "code": code})

@app.route("/check_linkcode/<code>", methods=["GET"])
def check_linkcode(code):
    data = link_requests.get(code)
    if not data:
        return jsonify({"success": False, "error": "Code not found"}), 404
    return jsonify(data)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online as {bot.user} | Commands synced globally")

async def require_linked(interaction: discord.Interaction):
    for data in link_requests.values():
        if data.get("discord_id") == str(interaction.user.id) and data.get("discordLinked"):
            return True
    embed = discord.Embed(
        title="❌ You need to authorize the bot",
        description="Click the button below to authorize.",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow()
    )
    button = Button(label="Authorize", url=AUTHORIZE_URL)
    view = View()
    view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    return False

# --- Discord Commands ---
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
    embed = discord.Embed(title="✅ Player Linked!", color=discord.Color.green(), timestamp=datetime.utcnow())
    embed.add_field(name="Master PlayFab ID", value=data.get("playfab_id","N/A"), inline=False)
    embed.add_field(name="HWID", value=data.get("hwid","N/A"), inline=False)
    embed.add_field(name="IP", value=data.get("ip","N/A"), inline=False)
    embed.add_field(name="Link Code", value=code, inline=False)
    embed.add_field(name="Discord ID", value=interaction.user.id, inline=False)
    embed.add_field(name="Status", value="🔗 Linked", inline=False)
    log_webhook(embed.to_dict())
    del link_requests[code]
    save_db()
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="linkstatus", description="Check your Discord link status")
async def linkstatus(interaction: discord.Interaction):
    if not await require_linked(interaction):
        return
    await interaction.response.send_message("✅ You are linked.", ephemeral=True)

@bot.tree.command(name="unlink", description="Unlink your Discord account")
async def unlink(interaction: discord.Interaction):
    removed = False
    for code, data in list(link_requests.items()):
        if data.get("discord_id") == str(interaction.user.id):
            link_requests[code]["discordLinked"] = False
            link_requests[code]["discord_id"] = None
            removed = True
    save_db()
    msg = "✅ Your account has been unlinked." if removed else "❌ You were not linked."
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="restart", description="Owner-only: restart the bot")
async def restart(interaction: discord.Interaction):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can restart.", ephemeral=True)
        return
    await interaction.response.send_message("♻️ Restarting bot and syncing commands globally...", ephemeral=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)

@bot.tree.command(name="addlinkedcodes", description="Owner-only: add linked codes manually")
@app_commands.describe(playfab_id="PlayFab ID", hwid="HWID", ip="IP", code="6-digit code")
async def addlinkedcodes(interaction: discord.Interaction, playfab_id: str, hwid: str, ip: str, code: str):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can add codes.", ephemeral=True)
        return
    link_requests[code] = {
        "playfab_id": playfab_id,
        "hwid": hwid,
        "ip": ip,
        "discord_id": None,
        "discordLinked": False
    }
    save_db()
    await interaction.response.send_message(f"✅ Code {code} added.", ephemeral=True)

@bot.tree.command(name="linkedlogs", description="Owner-only: show all linked codes")
async def linkedlogs(interaction: discord.Interaction):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can view logs.", ephemeral=True)
        return
    embed = log_all_linkcodes_embed()
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Flask Web Server ---
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()
bot.run(DISCORD_TOKEN)
