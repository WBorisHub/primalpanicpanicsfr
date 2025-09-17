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
BAN_DB_FILE = "ban_history.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")
BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", 0))
AUTHORIZE_URL = "https://discord.com/oauth2/authorize?client_id=1417616334631731310"

if not DISCORD_TOKEN or not LOG_WEBHOOK_URL:
    raise ValueError("DISCORD_TOKEN and LOG_WEBHOOK_URL must be set!")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)
app = Flask(__name__)

AUTHORIZED_USERS = set()
SUPPORT_USERS = set()

if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        link_requests = json.load(f)
else:
    link_requests = {}

if os.path.exists(BAN_DB_FILE):
    with open(BAN_DB_FILE, "r") as f:
        ban_history = json.load(f)
else:
    ban_history = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(link_requests, f, indent=4)

def save_ban_db():
    with open(BAN_DB_FILE, "w") as f:
        json.dump(ban_history, f, indent=4)

def log_webhook(embed):
    try:
        requests.post(LOG_WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except:
        pass

def log_all_linkcodes_embed():
    embed = discord.Embed(title="📄 Linked Codes Log", color=0x00ff00, timestamp=datetime.utcnow())
    for code, data in link_requests.items():
        status = "🔗 Linked" if data.get("discordLinked") else "❌ Unlinked"
        embed.add_field(
            name=f"Code: {code}",
            value=(
                f"PlayFab ID: {data.get('playfab_id','N/A')}\n"
                f"HWID: {data.get('hwid','N/A')}\n"
                f"IP: {data.get('ip','N/A')}\n"
                f"Discord ID: {data.get('discord_id','N/A')}\n"
                f"Status: {status}\n"
                f"Linked At: {data.get('linked_at','N/A')}"
            ),
            inline=False
        )
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

    login_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    webhook_message = {
        "content": (
            f"PLAYER LOGGED INTO PRIMAL PANIC\n"
            f"PlayFab ID: {data['playfab_id']}\n"
            f"HWID: {data['hwid']}\n"
            f"IP: {data['ip']}\n"
            f"Link Code: {code}\n"
            f"Status: Unlinked ❌\n"
            f"Time: {login_time}"
        )
    }
    try:
        requests.post(LOG_WEBHOOK_URL, json=webhook_message, timeout=5)
    except:
        pass

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

async def require_authorized(interaction: discord.Interaction):
    for data in link_requests.values():
        if data.get("discord_id") == str(interaction.user.id) and data.get("discordLinked"):
            return True
    if interaction.user.id in AUTHORIZED_USERS:
        return True
    try:
        user = await bot.fetch_user(interaction.user.id)
        if user:
            AUTHORIZED_USERS.add(interaction.user.id)
            return True
    except:
        pass
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

async def require_support(interaction: discord.Interaction):
    return interaction.user.id in SUPPORT_USERS or interaction.user.id == BOT_OWNER_ID

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
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="banhistory", description="Show total bans and reasons")
async def banhistory(interaction: discord.Interaction):
    if not await require_support(interaction):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    total_bans = len(ban_history)
    embed = discord.Embed(
        title=f"📋 Total Bans: {total_bans}",
        description="Click the button below to view all reasons.",
        color=discord.Color.red(),
        timestamp=datetime.utcnow()
    )
    view = View()
    button = Button(label="View Ban Reasons", style=discord.ButtonStyle.primary)

    async def button_callback(interaction: discord.Interaction):
        reasons = ""
        for player, data in ban_history.items():
            reasons += f"**{player}**:\n"
            for reason in data.get("reasons", []):
                reasons += f"- {reason}\n"
        await interaction.response.send_message(f"📝 Ban Reasons:\n{reasons}", ephemeral=True)

    button.callback = button_callback
    view.add_item(button)

    log_webhook(embed.to_dict())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="linkstatus", description="Check your Discord link status")
async def linkstatus(interaction: discord.Interaction):
    if not await require_authorized(interaction):
        return
    await interaction.response.send_message("✅ You are linked or authorized.", ephemeral=True)

@bot.tree.command(name="unlink", description="Unlink your Discord account")
async def unlink(interaction: discord.Interaction):
    removed = False
    for code, data in list(link_requests.items()):
        if data.get("discord_id") == str(interaction.user.id):
            data["discordLinked"] = False
            data["discord_id"] = None
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

@bot.tree.command(name="addlinkedcodes", description="Add linked codes manually")
@app_commands.describe(playfab_id="PlayFab ID", hwid="HWID", ip="IP", code="6-digit code")
async def addlinkedcodes(interaction: discord.Interaction, playfab_id: str, hwid: str, ip: str, code: str):
    if not await require_support(interaction):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
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

@bot.tree.command(name="linkedlogs", description="Show all linked codes logs")
async def linkedlogs(interaction: discord.Interaction):
    if not await require_support(interaction):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    embed = log_all_linkcodes_embed()
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="deletelinkedcode", description="Delete a linked code")
@app_commands.describe(code="6-digit code to delete")
async def deletelinkedcode(interaction: discord.Interaction, code: str):
    if not await require_support(interaction):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    data = link_requests.get(code)
    if not data:
        await interaction.response.send_message("❌ Code not found.", ephemeral=True)
        return
    del link_requests[code]
    save_db()
    embed = discord.Embed(title="🗑️ Linked Code Deleted", color=discord.Color.red(), timestamp=datetime.utcnow())
    embed.add_field(name="Code", value=code, inline=False)
    embed.add_field(name="PlayFab ID", value=data.get("playfab_id","N/A"), inline=False)
    embed.add_field(name="HWID", value=data.get("hwid","N/A"), inline=False)
    embed.add_field(name="IP", value=data.get("ip","N/A"), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="addsupport", description="Owner-only: add support staff")
@app_commands.describe(user="User to give support permissions")
async def addsupport(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can add support.", ephemeral=True)
        return
    SUPPORT_USERS.add(user.id)
    await interaction.response.send_message(f"✅ {user.mention} added as support.", ephemeral=True)

@bot.tree.command(name="removesupport", description="Owner-only: remove support staff")
@app_commands.describe(user="User to remove support permissions")
async def removesupport(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can remove support.", ephemeral=True)
        return
    SUPPORT_USERS.discard(user.id)
    await interaction.response.send_message(f"✅ {user.mention} removed from support.", ephemeral=True)

# --- NEW: Join Servers Command ---
@bot.tree.command(name="joinservers", description="Owner-only: notify linked users about a server invite")
@app_commands.describe(invite_link="Discord invite link")
async def joinservers(interaction: discord.Interaction, invite_link: str):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can do this.", ephemeral=True)
        return
    try:
        invite = await bot.fetch_invite(invite_link)
    except discord.NotFound:
        await interaction.response.send_message("❌ Invalid invite link.", ephemeral=True)
        return
    except discord.HTTPException:
        await interaction.response.send_message("❌ Failed to fetch invite, try again.", ephemeral=True)
        return

    count = 0
    for code, data in link_requests.items():
        if data.get("discordLinked"):
            try:
                user = await bot.fetch_user(int(data["discord_id"]))
                if user:
                    await user.send(f"📢 Owner added a new server! Join here: {invite_link}")
                    count += 1
            except:
                continue

    await interaction.response.send_message(f"✅ Notified {count} linked users about the server invite.", ephemeral=True)

# --- Flask Web Server ---
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()
bot.run(DISCORD_TOKEN)
