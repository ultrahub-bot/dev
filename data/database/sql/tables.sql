-- Tabela users
CREATE TABLE IF NOT EXISTS
  users (
    id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE ,
    name TEXT NOT NULL DEFAULT 'Discord_Name',
    is_admin BOOLEAN NOT NULL DEFAULT 0,
    discord_id INTEGER NOT NULL DEFAULT 0 UNIQUE,
    discord_username TEXT NOT NULL DEFAULT 'Discord Name',
    discord_mention TEXT NOT NULL DEFAULT 'Discord Mention',
    discord_avatar_url TEXT NOT NULL DEFAULT 'Discord Avatar Url',
    discord_is_bot BOOLEAN NOT NULL DEFAULT 0,
    discord_created_at TEXT NOT NULL DEFAULT 'Discord_Created_At',
    aqw_id INTEGER NOT NULL DEFAULT 0,
    aqw_username TEXT NOT NULL DEFAULT 'AQW_Username'
  );

-- Tabela bosses
CREATE TABLE IF NOT EXISTS
  bosses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Boss_Name',
    party_size INTEGER NOT NULL DEFAULT 1,
    map TEXT NOT NULL DEFAULT 'otto',
    difficulty INTEGER NOT NULL DEFAULT 0,
    hp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 0,
    tips TEXT NOT NULL DEFAULT 'None',
    wiki_url TEXT NOT NULL DEFAULT 'Wiki_URL',
    guide_url TEXT NOT NULL DEFAULT 'Guide_URL',
    thumbnail_url TEXT NOT NULL DEFAULT 'Thumbnail_URL',
    icon_url TEXT NOT NULL DEFAULT 'Icon_URL',
    is_hidden BOOLEAN NOT NULL DEFAULT 0,
    notify_role_id INTEGER NOT NULL DEFAULT 0
  );

-- Tabela badges
CREATE TABLE IF NOT EXISTS
  badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Badge_Name',
    description TEXT NOT NULL DEFAULT 'badge_description',
    type_id INTEGER NOT NULL DEFAULT 0,
    is_hidden BOOLEAN NOT NULL DEFAULT 0,
    is_available BOOLEAN NOT NULL DEFAULT 1,
    thumbnail_url TEXT NOT NULL DEFAULT 'Thumbnail_URL',
    icon_url TEXT NOT NULL DEFAULT 'Icon_URL',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela badge_types
CREATE TABLE IF NOT EXISTS
  badge_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Type Name',
    description TEXT NOT NULL DEFAULT 'Description of the type',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela user_badges
CREATE TABLE IF NOT EXISTS
  user_badges (
    user_id INTEGER NOT NULL DEFAULT 0,
    badge_id INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, badge_id),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (badge_id) REFERENCES badges (id)
  );

-- Tabela guild_roles
CREATE TABLE IF NOT EXISTS
  guild_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE DEFAULT 'Role Name',
    description TEXT NOT NULL DEFAULT 'Role Description',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela guilds
CREATE TABLE IF NOT EXISTS
  guilds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leader_id INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL UNIQUE DEFAULT 'Guild Name',
    motd TEXT NOT NULL DEFAULT 'Guild Message of the Day',
    tag TEXT NOT NULL DEFAULT 'Guild Tag',
    level INTEGER NOT NULL DEFAULT 1,
    EXP INTEGER NOT NULL DEFAULT 0,
    capacity INTEGER NOT NULL DEFAULT 1,
    max_capacity INTEGER NOT NULL DEFAULT 55,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela guild_users
CREATE TABLE IF NOT EXISTS
  guild_users (
    guild_id INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER NOT NULL DEFAULT 0,
    role_id INTEGER NOT NULL DEFAULT 0,
    contribution_xp INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (guild_id, user_id),
    FOREIGN KEY (guild_id) REFERENCES guilds (id),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (role_id) REFERENCES guild_roles (id)
  );

-- Tabela requirements
CREATE TABLE IF NOT EXISTS
  requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL DEFAULT 'Requirement Description',
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela badge_requirements
CREATE TABLE IF NOT EXISTS
  badge_requirements (
    badge_id INTEGER NOT NULL DEFAULT 0,
    requirement_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (badge_id, requirement_id),
    FOREIGN KEY (badge_id) REFERENCES badges (id),
    FOREIGN KEY (requirement_id) REFERENCES requirements (id)
  );

-- Tabela shop
CREATE TABLE IF NOT EXISTS
  shop (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Shop Name',
    description TEXT NOT NULL DEFAULT 'Shop Description',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela items
CREATE TABLE IF NOT EXISTS
  items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Item Name',
    description TEXT NOT NULL DEFAULT 'Item Description',
    is_consumable BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

-- Tabela shop_items
CREATE TABLE IF NOT EXISTS
  shop_items (
    item_id INTEGER NOT NULL DEFAULT 0,
    shop_id INTEGER NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 1,
    price REAL NOT NULL DEFAULT 0,
    is_available BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, shop_id),
    FOREIGN KEY (item_id) REFERENCES items (id),
    FOREIGN KEY (shop_id) REFERENCES shop (id)
  );

-- Tabela user_inventory
CREATE TABLE IF NOT EXISTS
  user_inventory (
    item_id INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 1,
    equiped BOOLEAN NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, item_id),
    FOREIGN KEY (item_id) REFERENCES items (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
  );

-- Tabela raid_status
CREATE TABLE IF NOT EXISTS
  raid_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Status Name',
    description TEXT NOT NULL DEFAULT 'Status Description'
  );

-- Tabela raid_type
CREATE TABLE IF NOT EXISTS
  raid_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Raid Type'
  );

-- Tabela raids
CREATE TABLE IF NOT EXISTS
  raids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_id INTEGER NOT NULL DEFAULT 0,
    status_id INTEGER NOT NULL DEFAULT 0,
    type_id INTEGER NOT NULL DEFAULT 0,
    discord_message_id INTEGER NOT NULL DEFAULT 0,
    voice_channel_id INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (boss_id) REFERENCES bosses (id),
    FOREIGN KEY (status_id) REFERENCES raid_status (id),
    FOREIGN KEY (type_id) REFERENCES raid_type (id)
  );

-- Tabela raid_users
CREATE TABLE IF NOT EXISTS
  raid_users (
    user_id INTEGER NOT NULL DEFAULT 0,
    raid_id INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (raid_id) REFERENCES raids (id)
  );

-- Tabela audit
CREATE TABLE IF NOT EXISTS
  audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    ACTION TEXT NOT NULL DEFAULT 'Action Performed',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL DEFAULT 'No Description',
    FOREIGN KEY (user_id) REFERENCES users (id)
  );