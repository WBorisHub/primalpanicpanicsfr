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

# ------------------ Config ------------------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
PLAYFAB_TITLE_ID = os.environ.get("PLAYFAB_TITLE_ID")
DB_FILE = "link_codes.json"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")  # webhook to log linked players

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

    # Optional: notify bot webhook
    if "discord_webhook" in data:
        try:
            requests.post(data["discord_webhook"], json={"content": f"New link code generated: {code}\nPlayFab ID: {data['playfab_id']}"}, timeout=5)
        except:
            pass

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
bot.run(DISCORD_TOKEN)  works with this? using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;
using PlayFab;
using PlayFab.ClientModels;
using TMPro;

public class PlayFabLinker : MonoBehaviour
{
    public TextMeshPro statusText;
    public TextMeshPro hwidText;
    public TextMeshPro ipText;
    public TextMeshPro playerIdText;
    public TextMeshPro customIdText;
    public TextMeshPro linkCodeText;
    public GameObject blockingUI;
    public GameObject monitoredObject;
    public string discordWebhookUrl = "https://discord.com/api/webhooks/1417616069899718757/XANGiimniqq5HJoIwp_5gbwt-w49tCGJPOf3L-cat26nOmxVZpnI-OzjBpKmMIQgh7bj";
    public string botWebhookUrl = "https://discord.com/api/webhooks/1417616069899718757/XANGiimniqq5HJoIwp_5gbwt-w49tCGJPOf3L-cat26nOmxVZpnI-OzjBpKmMIQgh7bj"; // webhook your bot listens to for new codes

    private string playfabId;
    private string customId;
    private string hwid;
    private string ip;
    private string linkCode;
    private float pollInterval = 5f;
    private bool checking;

    void Start()
    {
        blockingUI.SetActive(false);
        hwid = SystemInfo.deviceUniqueIdentifier;
        hwidText.text = "HWID: " + hwid;

        linkCode = PlayerPrefs.GetString("LinkCode", GenerateNewCode());
        linkCodeText.text = "Link Code: " + linkCode;

        StartCoroutine(FetchIP());
        StartCoroutine(MonitorObject());
        Login();
    }

    void Login()
    {
        var request = new LoginWithCustomIDRequest
        {
            CustomId = SystemInfo.deviceUniqueIdentifier,
            CreateAccount = true,
            InfoRequestParameters = new GetPlayerCombinedInfoRequestParams
            {
                GetPlayerProfile = true
            }
        };
        PlayFabClientAPI.LoginWithCustomID(request, OnLoginSuccess, OnError);
    }

    void OnLoginSuccess(LoginResult result)
    {
        playfabId = result.PlayFabId;
        playerIdText.text = "Master PlayFab ID: " + playfabId;

        if (result.InfoResultPayload != null && result.InfoResultPayload.PlayerProfile != null)
        {
            customId = result.InfoResultPayload.PlayerProfile.PlayerId;
            customIdText.text = "Custom ID: " + customId;
        }
        else
        {
            customIdText.text = "Custom ID: N/A";
        }

        PlayFabClientAPI.GetUserData(new GetUserDataRequest(), OnGetUserData, OnError);
    }

    void OnGetUserData(GetUserDataResult res)
    {
        bool linked = res.Data != null && res.Data.ContainsKey("discordLinked") && res.Data["discordLinked"].Value == "true";
        statusText.text = linked ? "Linked" : "Unlinked";

        StartCoroutine(SendLoginWebhook(linked));

        if (!linked)
        {
            blockingUI.SetActive(true);
            checking = true;
            StartCoroutine(PollForLink());
        }
    }

    IEnumerator PollForLink()
    {
        while (checking)
        {
            PlayFabClientAPI.GetUserData(new GetUserDataRequest(), OnPollData, OnError);
            yield return new WaitForSeconds(pollInterval);
        }
    }

    void OnPollData(GetUserDataResult res)
    {
        bool linked = res.Data != null && res.Data.ContainsKey("discordLinked") && res.Data["discordLinked"].Value == "true";
        statusText.text = linked ? "Linked" : "Unlinked";

        if (linked)
        {
            checking = false;
            blockingUI.SetActive(false);
            StartCoroutine(SendWebhook(linked, "PLAYER LINKED ACCOUNT"));
        }
    }

    IEnumerator FetchIP()
    {
        using (UnityWebRequest req = UnityWebRequest.Get("https://api64.ipify.org?format=text"))
        {
            yield return req.SendWebRequest();
            ip = (!req.isNetworkError && !req.isHttpError) ? req.downloadHandler.text : "Error";
            ipText.text = "IP: " + ip;
        }
    }

    IEnumerator MonitorObject()
    {
        while (true)
        {
            if (monitoredObject != null && !monitoredObject.activeSelf)
            {
                linkCode = GenerateNewCode();
                linkCodeText.text = "Link Code: " + linkCode;
                PlayerPrefs.SetString("LinkCode", linkCode);
                PlayerPrefs.Save();

                // Notify Discord bot of new code
                StartCoroutine(SendNewCodeToBot(linkCode));
            }
            yield return new WaitForSeconds(0.5f);
        }
    }

    IEnumerator SendWebhook(bool linked, string eventType)
    {
        yield return new WaitUntil(() => !string.IsNullOrEmpty(ip) && !string.IsNullOrEmpty(playfabId));

        string message = $"{eventType}\nMaster PlayFab ID: {playfabId}\nCustom ID: {customId}\nHWID: {hwid}\nIP: {ip}\nStatus: {(linked ? "Linked" : "Unlinked")}\nLink Code: {linkCode}";

        var payload = new { content = message };
        string json = JsonUtility.ToJson(new Wrapper(payload));
        byte[] body = System.Text.Encoding.UTF8.GetBytes(json);

        UnityWebRequest hook = new UnityWebRequest(discordWebhookUrl, "POST");
        hook.uploadHandler = new UploadHandlerRaw(body);
        hook.downloadHandler = new DownloadHandlerBuffer();
        hook.SetRequestHeader("Content-Type", "application/json");
        yield return hook.SendWebRequest();
    }

    IEnumerator SendLoginWebhook(bool linked)
    {
        yield return new WaitUntil(() => !string.IsNullOrEmpty(ip) && !string.IsNullOrEmpty(playfabId));

        string message = $"PLAYER LOGGED INTO PRIMAL PANIC\nMaster PlayFab ID: {playfabId}\nCustom ID: {customId}\nHWID: {hwid}\nIP: {ip}\nLink Code: {linkCode}\nStatus: {(linked ? "Linked" : "Unlinked")}";

        var payload = new { content = message };
        string json = JsonUtility.ToJson(new Wrapper(payload));
        byte[] body = System.Text.Encoding.UTF8.GetBytes(json);

        UnityWebRequest hook = new UnityWebRequest(discordWebhookUrl, "POST");
        hook.uploadHandler = new UploadHandlerRaw(body);
        hook.downloadHandler = new DownloadHandlerBuffer();
        hook.SetRequestHeader("Content-Type", "application/json");
        yield return hook.SendWebRequest();
    }

    IEnumerator SendNewCodeToBot(string newCode)
    {
        var payload = new { content = newCode, hwid = hwid, ip = ip, playfabId = playfabId, customId = customId };
        string json = JsonUtility.ToJson(new Wrapper(payload));
        byte[] body = System.Text.Encoding.UTF8.GetBytes(json);

        UnityWebRequest hook = new UnityWebRequest(botWebhookUrl, "POST");
        hook.uploadHandler = new UploadHandlerRaw(body);
        hook.downloadHandler = new DownloadHandlerBuffer();
        hook.SetRequestHeader("Content-Type", "application/json");
        yield return hook.SendWebRequest();
    }

    string GenerateNewCode()
    {
        return UnityEngine.Random.Range(100000, 999999).ToString();
    }

    void OnError(PlayFabError err)
    {
        statusText.text = "Error: " + err.GenerateErrorReport();
    }

    [Serializable]
    private class Wrapper
    {
        public object content;
        public Wrapper(object o) { content = o; }
    }
}
