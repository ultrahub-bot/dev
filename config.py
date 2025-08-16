import yaml
from pathlib import Path
from dotenv import load_dotenv
import os
import json

load_dotenv()

# Carrega configurações do YAML
SETTINGS_PATH = Path("settings.yaml")
if SETTINGS_PATH.exists():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        bot_settings = yaml.safe_load(f)
else:
    bot_settings = {}

# Função auxiliar para buscar primeiro no YAML, depois no .env
def get_setting(key, default=None, cast_type=None):
    value = bot_settings.get(key)
    if value is None:
        value = os.getenv(key)
    if value is None:
        value = default
    if cast_type and value is not None:
        try:
            value = cast_type(value)
        except Exception:
            pass
    return value

# ==================================================================================================
# 🤖 BOT SETUP
# ==================================================================================================
TOKEN = os.getenv("BOT_TOKEN")  
BOT_OWNER = get_setting("BOT_OWNER")
BOT_CONTACT = get_setting("BOT_CONTACT")
BOT_TOS = get_setting("BOT_TOS")
BOT_PRIVACY = get_setting("BOT_PRIVACY")
BOT_SERVER_URL = get_setting("BOT_SERVER_URL")
BOT_WHATS = get_setting("BOT_WHATS")
BOT_SERVER = get_setting("BOT_SERVER", cast_type=int)
PREFIX = get_setting("PREFIX", "!")

# ==================================================================================================
# 🔐 BACKUP
# ==================================================================================================
BKP_DATA = get_setting("BKP_DATA", "./data")
BKP_DAYS = get_setting("BKP_DAYS", 30, int)

# ==================================================================================================
# ⚙️ CONFIGURAÇÕES GERAIS
# ==================================================================================================
# 🎭 CARGOS
MODERATOR_ROLE_ID = get_setting("MODERATOR_ROLE_ID", cast_type=int)
PENDING_ROLE_ID = get_setting("PENDING_ROLE_ID", cast_type=int)
NOTABOT_ROLE_ID = get_setting("NOTABOT_ROLE_ID", cast_type=int)
VERIFIED_ROLE_ID = get_setting("VERIFIED_ROLE_ID", cast_type=int)

# 💬 CANAIS
CALENDAR_CHANNEL_ID = get_setting("CALENDAR_CHANNEL_ID", cast_type=int)
NOTIFICATION_CHANNEL_ID = get_setting("NOTIFICATION_CHANNEL_ID", cast_type=int)
BOT_CHANNEL_ID = get_setting("BOT_CHANNEL_ID", cast_type=int)
RULES_CHANNEL_ID = get_setting("RULES_CHANNEL_ID", cast_type=int)
VERIFY_CHANNEL_ID = get_setting("VERIFY_CHANNEL_ID", cast_type=int)
WELCOME_CHANNEL_ID = get_setting("WELCOME_CHANNEL_ID", cast_type=int)

# 🛡 RAIDS
RAID_CHANNEL_ID = get_setting("RAID_CHANNEL_ID", cast_type=int)
RAID_DATA_DIR = get_setting("RAID_DATA_DIR", "./data")
RAID_LOGS_DIR = get_setting("RAID_LOGS_DIR", "./data/raid_logs")
RAID_COMPS_DIR = get_setting("RAID_COMPS_DIR", "./data/comps")

# 🛡 GUILDA
GUILD_LEADER_ROLE_ID = get_setting("GUILD_LEADER_ROLE_ID", cast_type=int)
GUILD_OFFICER_ROLE_ID = get_setting("GUILD_OFFICER_ROLE_ID", cast_type=int)
GUILD_RECRUITER_ROLE_ID = get_setting("GUILD_RECRUITER_ROLE_ID", cast_type=int)
GUILD_MEMBER_ROLE_ID = get_setting("GUILD_MEMBER_ROLE_ID", cast_type=int)
GUILD_DUFFER_ROLE_ID = get_setting("GUILD_DUFFER_ROLE_ID", cast_type=int)
GUILD_ROOKIE_ROLE_ID = get_setting("GUILD_ROOKIE_ROLE_ID", cast_type=int)

GUILD_CHAT_CHANNEL_ID = get_setting("GUILD_CHAT_CHANNEL_ID", cast_type=int)
GUILD_BAN_CHANNEL_ID = get_setting("GUILD_BAN_CHANNEL_ID", cast_type=int)
GUILD_LOG_CHANNEL_ID = get_setting("GUILD_LOG_CHANNEL_ID", cast_type=int)


# ==================================================================================================
# DIRETÓRIOS
# ==================================================================================================

VERIFY_STORAGE = Path("data/verification.json")  
INSIGNIAS_FILE = Path("data/insignias.json")
USERS_FILE = Path("data/users.json")
FEEDS_PATH = Path("data/feeds")
FEEDS_PATH.mkdir(parents=True, exist_ok=True)

# ==================================================================================================
# FUNÇÕES
# ==================================================================================================

def load_feeds(platform):
    try:
        with open(FEEDS_PATH / f"{platform}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_feeds(platform, data):
    with open(FEEDS_PATH / f"{platform}.json", "w") as f:
        json.dump(data, f, indent=2)
