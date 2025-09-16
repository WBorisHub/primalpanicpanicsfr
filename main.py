import os
import json
import requests
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
import threading
import sys
import asyncio
from datetime import datetime
from playfab import PlayFabClientAPI
from playfab.ClientModels import UpdateUserDataRequest

# ------------------ Config ------------------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
PLAYFAB_TITLE_ID = os.environ.get("PLAYFAB_TITLE_ID")
DB_FILE = "link_codes.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")

if not DISCORD_TOKEN or not PLAYFAB_TITLE_ID or not LOG_WEBHOOK_URL:
    raise ValueError("DISCORD_TOKEN, PLAYFAB_TITLE_ID and LOG_WEBHOOK_URL must be set!")

# ------------------ Discord Bot ------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Load link codes DB
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

# ------------------ Discord Commands ------------------
@bot.tree.command(name="linkcode", description="Link your Discord account using Unity code")
@app_commands.describe(code="6-digit code from Unity")
async def linkcode(interaction: discord.Interaction, code: str):
    data = link_requests.get(code)
    if not data:
        await interaction.response.send_message("❌ Invalid or expired code.", ephemeral=True)
        return

    data["discord_id"] = str(interaction.user.id)
    data["linked_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    save_db()

    # Update PlayFab user data
    try:
        PlayFabClientAPI.UpdateUserData(UpdateUserDataRequest(
            PlayFabId=data["playfab_id"],
            Data={"discordLinked": "true", "discordId": str(interaction.user.id)}
        ))
    except Exception as e:
        print("PlayFab update error:", e)

    # Send log webhook
    message = f"✅ Player Linked!\nTime: {data['linked_at']}\nMaster PlayFab ID: {data['playfab_id']}\nHWID: {data['hwid']}\nIP: {data['ip']}\nLink Code: {code}\nDiscord ID: {interaction.user.id}"
    try:
        requests.post(LOG_WEBHOOK_URL, json={"content": message}, timeout=5)
    except:
        pass

    del link_requests[code]
    save_db()
    await interaction.response.send_message(f"✅ Successfully linked to PlayFab ID {data['playfab_id']}", ephemeral=True)

@bot.tree.command(name="unlink", description="Unlink your Discord account from PlayFab")
async def unlink(interaction: discord.Interaction):
    await interaction.response.send_message("⚠️ Unlinking is manual in this setup.", ephemeral=True)

@bot.tree.command(name="addlinkcode", description="Manually add a link code")
@app_commands.describe(playfab_id="PlayFab ID", code="6-digit code", hwid="HWID", ip="IP")
async def addlinkcode(interaction: discord.Interaction, playfab_id: str, code: str, hwid: str, ip: str):
    link_requests[code] = {"playfab_id": playfab_id, "hwid": hwid, "ip": ip, "discord_id": None}
    save_db()
    await interaction.response.send_message(f"✅ Code {code} registered.", ephemeral=True)

@bot.tree.command(name="restart", description="Restart the bot")
async def restart(interaction: discord.Interaction):
    await interaction.response.send_message("♻️ Restarting bot...", ephemeral=True)
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ------------------ Flask API for Unity ------------------
app = Flask(__name__)

@app.route("/register_linkcode", methods=["POST"])
def register_linkcode():
    data = request.json
    required = ["code", "playfab_id", "hwid", "ip"]
    if not data or any(x not in data for x in required):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    code = data["code"]
    link_requests[code] = {
        "playfab_id": data["playfab_id"],
        "hwid": data["hwid"],
        "ip": data["ip"],
        "discord_id": None,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }
    save_db()

    return jsonify({"success": True, "code": code})

@app.route("/check_linkcode/<code>", methods=["GET"])
def check_linkcode(code):
    data = link_requests.get(code)
    if not data:
        return jsonify({"valid": False})
    return jsonify({"valid": True, "data": data})

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ------------------ Start Flask + Bot ------------------
threading.Thread(target=run_flask, daemon=True).start()
bot.run(DISCORD_TOKEN)
