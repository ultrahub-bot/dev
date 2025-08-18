BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "audit" (
	"id"	INTEGER NOT NULL UNIQUE,
	"user_id"	INTEGER NOT NULL DEFAULT 0,
	"action"	TEXT NOT NULL DEFAULT 'Action Performed',
	"created_at"	TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"description"	TEXT NOT NULL DEFAULT 'No Description',
	PRIMARY KEY("id" AUTOINCREMENT),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "badge_requirements" (
	"badge_id"	INTEGER NOT NULL DEFAULT 0,
	"requirement_id"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("badge_id","requirement_id"),
	FOREIGN KEY("badge_id") REFERENCES "badges"("id"),
	FOREIGN KEY("requirement_id") REFERENCES "requirements"("id")
);
CREATE TABLE IF NOT EXISTS "badge_types" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Type Name',
	"description"	TEXT NOT NULL DEFAULT 'Description of the type',
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "badges" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Badge_Name',
	"description"	TEXT NOT NULL DEFAULT 'badge_description',
	"type_id"	INTEGER NOT NULL DEFAULT 0,
	"is_hidden"	BOOLEAN NOT NULL DEFAULT 0,
	"is_available"	BOOLEAN NOT NULL DEFAULT 1,
	"thumbnail_url"	TEXT NOT NULL DEFAULT 'Thumbnail_URL',
	"icon_url"	TEXT NOT NULL DEFAULT 'Icon_URL',
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "bosses" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Boss_Name',
	"party_size"	INTEGER NOT NULL DEFAULT 0,
	"map"	TEXT NOT NULL DEFAULT 'otto',
	"difficulty"	INTEGER NOT NULL DEFAULT 0,
	"hp"	INTEGER NOT NULL DEFAULT 0,
	"level"	INTEGER NOT NULL DEFAULT 0,
	"tips"	TEXT NOT NULL DEFAULT 'None',
	"wiki_url"	TEXT NOT NULL DEFAULT 'Wiki_URL',
	"guide_url"	TEXT NOT NULL DEFAULT 'Guide_URL',
	"thumbnail_url"	TEXT NOT NULL DEFAULT 'Thumbnail_URL',
	"icon_url"	TEXT NOT NULL DEFAULT 'Icon_URL',
	"is_hidden"	BOOLEAN NOT NULL DEFAULT 0,
	"notify_role_id"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "guild_roles" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Role Name' UNIQUE,
	"description"	TEXT NOT NULL DEFAULT 'Role Description',
	"can_invite"	INTEGER NOT NULL DEFAULT 0,
	"can_remove"	INTEGER NOT NULL DEFAULT 0,
	"can_demote"	INTEGER NOT NULL DEFAULT 0,
	"can_promote"	INTEGER NOT NULL DEFAULT 0,
	"can_motd"	INTEGER NOT NULL DEFAULT 0,
	"can_chat"	INTEGER NOT NULL DEFAULT 1,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "guild_users" (
	"guild_id"	INTEGER NOT NULL DEFAULT 0,
	"user_id"	INTEGER NOT NULL DEFAULT 0,
	"role_id"	INTEGER NOT NULL DEFAULT 0,
	"contribution_xp"	INTEGER NOT NULL DEFAULT 0,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	UNIQUE("guild_id","user_id"),
	FOREIGN KEY("guild_id") REFERENCES "guilds"("id"),
	FOREIGN KEY("role_id") REFERENCES "guild_roles"("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "guilds" (
	"id"	INTEGER NOT NULL UNIQUE,
	"leader_id"	INTEGER NOT NULL DEFAULT 0 UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Guild Name' UNIQUE,
	"motd"	TEXT NOT NULL DEFAULT 'Guild Message of the Day',
	"tag"	TEXT NOT NULL DEFAULT 'Guild Tag' UNIQUE,
	"level"	INTEGER NOT NULL DEFAULT 1,
	"exp"	INTEGER NOT NULL DEFAULT 0,
	"gold"	INTEGER NOT NULL,
	"capacity"	INTEGER NOT NULL DEFAULT 1,
	"max_capacity"	INTEGER NOT NULL DEFAULT 55,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "items" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Item Name',
	"description"	TEXT NOT NULL DEFAULT 'Item Description',
	"is_consumable"	BOOLEAN NOT NULL DEFAULT 0,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "raid_status" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Status Name',
	"description"	TEXT NOT NULL DEFAULT 'Status Description',
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "raid_type" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Raid Type',
	"description"	TEXT NOT NULL DEFAULT 'Description',
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "raid_users" (
	"user_id"	INTEGER NOT NULL DEFAULT 0,
	"raid_id"	INTEGER NOT NULL DEFAULT 0,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("raid_id") REFERENCES "raids"("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "raids" (
	"id"	INTEGER NOT NULL UNIQUE,
	"boss_id"	INTEGER NOT NULL DEFAULT 0,
	"status_id"	INTEGER NOT NULL DEFAULT 0,
	"type_id"	INTEGER NOT NULL DEFAULT 0,
	"discord_message_id"	INTEGER NOT NULL DEFAULT 0,
	"voice_channel_id"	INTEGER NOT NULL DEFAULT 0,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT),
	FOREIGN KEY("boss_id") REFERENCES "bosses"("id"),
	FOREIGN KEY("status_id") REFERENCES "raid_status"("id"),
	FOREIGN KEY("type_id") REFERENCES "raid_type"("id")
);
CREATE TABLE IF NOT EXISTS "requirements" (
	"id"	INTEGER NOT NULL UNIQUE,
	"description"	TEXT NOT NULL DEFAULT 'Requirement Description',
	"quantity"	INTEGER NOT NULL DEFAULT 0,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "shop" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Shop Name',
	"description"	TEXT NOT NULL DEFAULT 'Shop Description',
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "shop_items" (
	"item_id"	INTEGER NOT NULL DEFAULT 0,
	"shop_id"	INTEGER NOT NULL DEFAULT 0,
	"quantity"	INTEGER NOT NULL DEFAULT 1,
	"price"	REAL NOT NULL DEFAULT 0,
	"is_available"	BOOLEAN NOT NULL DEFAULT 1,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	"updated_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("item_id","shop_id"),
	FOREIGN KEY("item_id") REFERENCES "items"("id"),
	FOREIGN KEY("shop_id") REFERENCES "shop"("id")
);
CREATE TABLE IF NOT EXISTS "user_badges" (
	"user_id"	INTEGER NOT NULL DEFAULT 0,
	"badge_id"	INTEGER NOT NULL DEFAULT 0,
	"created_at"	DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY("user_id","badge_id"),
	FOREIGN KEY("badge_id") REFERENCES "badges"("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "user_inventory" (
	"item_id"	INTEGER NOT NULL DEFAULT 0,
	"user_id"	INTEGER NOT NULL DEFAULT 0,
	"quantity"	INTEGER NOT NULL DEFAULT 1,
	"equiped"	BOOLEAN NOT NULL DEFAULT 0,
	PRIMARY KEY("user_id","item_id"),
	FOREIGN KEY("item_id") REFERENCES "items"("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "users" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL DEFAULT 'Discord_Name',
	"is_admin"	INTEGER NOT NULL DEFAULT 0,
	"discord_id"	INTEGER NOT NULL DEFAULT 0 UNIQUE,
	"discord_username"	TEXT NOT NULL DEFAULT 'Discord Name',
	"discord_mention"	TEXT NOT NULL DEFAULT 'Discord Mention',
	"discord_avatar_url"	TEXT NOT NULL DEFAULT 'Discord Avatar Url',
	"discord_is_bot"	BOOLEAN NOT NULL DEFAULT 0,
	"discord_created_at"	TEXT NOT NULL DEFAULT 'Discord_Created_At',
	"aqw_id"	INTEGER NOT NULL DEFAULT 0,
	"aqw_level"	INTEGER NOT NULL DEFAULT 0,
	"aqw_username"	TEXT NOT NULL DEFAULT 'AQW_Username',
	"exp"	INTEGER NOT NULL DEFAULT 0,
	"gold"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id" AUTOINCREMENT)
);
INSERT INTO "bosses" VALUES (1,'Ultra Warden',4,'ultrawarden',1,0,0,'Lembrar do AP/LOO Curar em Conjunto e o LR Taunt na Virada dos 500k Vida','https://aqwwiki.wikidot.com/ultra-warden-monster','https://www.aqwhub.com/ultra-guides/ultra-warden/','https://jix-aqw.github.io/site/ultrahub/assets/ultra-warden.png','',0,1361376110662652034);
INSERT INTO "bosses" VALUES (2,'Ultra Engineer',4,'ultraengineer',1,0,0,'Ap Começa a Fight, focar no drone Defensivo e depois no Ataque \n','https://aqwwiki.wikidot.com/ultra-engineer','https://www.aqwhub.com/ultra-guides/ultra-engineer/','https://jix-aqw.github.io/site/ultrahub/assets/ultra-engineer.png','',0,1361376117436448970);
INSERT INTO "bosses" VALUES (3,'Ultra Test',2,'ultrahub',3,0,0,'Elimine o Bowmaster e o Executioner antes de focar em Drago. Use Quixotic para mitigar os ataques de alto dano.','https://aqwwiki.wikidot.com/ultra-drago','https://www.aqwhub.com/ultra-guides/ultra-drago/','https://jix-aqw.github.io/site/ultrahub/assets/ultra-drago.png','',1,1361222701259296778);
INSERT INTO "bosses" VALUES (4,'Ultra Drago',4,'ultradrago',2,0,0,'Elimine o Arqueiro Primeiro , LR prestar atenção no Taunt / Tauntando o Guerreiro antes que o Arqueiro Morra','https://aqwwiki.wikidot.com/ultra-drago','https://www.aqwhub.com/ultra-guides/ultra-drago/','https://jix-aqw.github.io/site/ultrahub/assets/ultra-drago.png','',0,1361375585288323113);
INSERT INTO "bosses" VALUES (5,'Champion Drakath',4,'championdrakath',1,0,0,'Tauntar nos 18 / 15 / 13 / 11 Milhões e Voltar o Taunt em 8 / 5 / 3 , Importante que as Classes de Cura garantão a Sobrevivência da Equipe, Caso não conseguim podem usar Sage Tonic ou Divine Elixir','https://aqwwiki.wikidot.com/champion-drakath','https://ultimateaqw.webador.com/ultra-boss-fight-strategies/champion-drakath','https://jix-aqw.github.io/site/ultrahub/assets/champion-drakath.png','',0,1361375557505253396);
INSERT INTO "bosses" VALUES (6,'Ultra Darkon',4,'ultradarkon',3,0,0,'Evite que Darkon mate jogadores, pois ele recupera 750k de HP a cada abate. Coordene os taunts para evitar habilidades como ''Captive Audience'' e ''Seed Planted''.','https://aqwwiki.wikidot.com/darkon-the-conductor','https://pastebin.com/z3DWAU1W','https://jix-aqw.github.io/site/ultrahub/assets/ultra-darkon.png','',0,1361375054394298461);
INSERT INTO "bosses" VALUES (7,'Ultra Speaker',4,'ultraspeaker',3,0,0,'Coordene os taunts após as zonas vermelhas para evitar habilidades letais. Cada classe tem um papel específico durante as fases do combate.','https://aqwwiki.wikidot.com/the-first-speaker','https://www.aqwhub.com/ultra-guides/ultra-speaker/','https://jix-aqw.github.io/site/ultrahub/assets/ultra-speaker.png','',0,1361375926671376535);
INSERT INTO "bosses" VALUES (8,'Ultra Ezrajal',4,'ultraezrajal',1,0,0,'Parar de bater no Counter e evite de Bloquear a Skill Importante da Class em Geral ','http://aqwwiki.wikidot.com/ultra-ezrajal-monster','https://jix-site.github.io/site/guia/ultra-bosses/ultra-ezrajal','https://jix-aqw.github.io/site/ultrahub/assets/ultra-ezrajal.png','',0,1361376113582018702);
INSERT INTO "bosses" VALUES (9,'Ultra Dage',4,'ultradage',2,0,0,'Prestar Atenção nas Zonas, Acerta o Decay / Taunt ','http://aqwwiki.wikidot.com/dage-the-dark-lord','https://jix-aqw.github.io/site/guias/ultra-bosses/ultra-dage.html','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',0,1361375485115760920);
INSERT INTO "bosses" VALUES (10,'Ultra Tyndarius',4,'ultratyndarius',1,0,0,'LR Taunt a Orb Esquerda, DPS Taunt a Direita, Loo junto com o AP no Tyndarius e somente o Ap Taunta. AP Sempre entra Primeiro','https://aqwwiki.wikidot.com/ultra-avatar-tyndarius-monster---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',0,1361375756206346283);
INSERT INTO "bosses" VALUES (11,'Batara Kala',4,'ultrakala',1,0,0,'Nesse Fight Importante Classes de Redução de Dano Devido ao alto DOT','https://aqwwiki.wikidot.com/batara-kala---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,1361376372974424287);
INSERT INTO "bosses" VALUES (12,'Binky',6,'doomvault',1,0,0,'Prestar Atenção no Counter, Evitar extender a Luta se não ativa o HK, Lembrando que ele Bloqueia uma Skill','https://aqwwiki.wikidot.com/binky-monster---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (13,'Raxgore',6,'doomvaultb',1,0,0,'Prestar Atenção no Counter, Lembrando que ele Bloqueia uma Skill','https://aqwwiki.wikidot.com/undead-raxgore---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (14,'DoomKitten',6,'doomkitten',1,0,0,'Usar Classes que batem em DOT ou Classes que não crita','https://aqwwiki.wikidot.com/doomkitten-monster-1---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (15,'Flibbi',7,'voidflibbi',1,0,0,'Usar Classes com Redução de Desvio / Acerto inevitável / Redução de Dano','https://aqwwiki.wikidot.com/flibbitiestgibbet---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (16,'Key of Sholemoh',1,'infernalarena',1,0,0,'Manter a Vida Sempre na Metade do HP e Possuir um Total de Vida Maior que 3000 de Vida','https://aqwwiki.wikidot.com/key-of-sholemoh---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (17,'Cervus Malus',1,'infernalarena',1,0,0,'Usar Classes que Possui roubo de Vida','https://aqwwiki.wikidot.com/cervus-malus---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (18,'Deadly Duo',1,'infernalarena',1,0,0,'Usar Classes de DPS/Decay evitando a Cura Constante do Boss','https://aqwwiki.wikidot.com/deadly-duo---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (19,'Training Golem',10,'chchallenge',1,0,0,'Usar Classes que Não Crita e que Possui Redução de Dano','https://aqwwiki.wikidot.com/training-golem---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (20,'Salek Sprayer',7,'voidsalek',1,0,0,'Usar Classes com Alto Regen de HP','https://aqwwiki.wikidot.com/salek-sprayer---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (21,'Deimos',7,'deimos',1,0,0,'Evitar de Iniciar a Fight Sozinho se não Ativa a Segunda Fase do Boss, Lembrando que ele ativa o decay em certos Momentos','https://aqwwiki.wikidot.com/devastator-deimos---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (22,'Ultra Nulgath',4,'ultranulgath',2,0,0,'Derrotar a Espada antes do Nuke. Toda vez que derrotar a espada, o dano do Nulgath é acrescido.','https://aqwwiki.wikidot.com/nulgath-the-archfiend---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',0,1361376015137378415);
INSERT INTO "bosses" VALUES (23,'Ultra Iara',4,'ultraiara',2,0,0,'Evitar que A Luta se Extenda devido a Redução de Velocidade Extrema','https://aqwwiki.wikidot.com/ultra-iara-monster---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,1361376120708010004);
INSERT INTO "bosses" VALUES (24,'Kasuko',7,'lavarockshore',2,0,100,'Derrotar Whirlpool Primeiro sempre que ele Renascer para depois Focar o Boss','https://aqwwiki.wikidot.com/kasuko---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (25,'Moon',4,'templeshrine',1,0,0,'Preferir usar Classes Físicas','https://aqwwiki.wikidot.com/ascended-midnight---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,1364015684379738233);
INSERT INTO "bosses" VALUES (26,'Sun',4,'templeshrine',1,0,0,'Preferir usar Classes Mágicas','https://aqwwiki.wikidot.com/ascended-solstice---aqw','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',0,1364015684379738233);
INSERT INTO "bosses" VALUES (27,'Kathool Dephts',7,'kathooldepths',1,0,0,'Usar o Vigil quando aparecer "You cannot resist" , Focar os Tentaculos Primeiro','https://aqwwiki.wikidot.com/httpaqwwikiwikidotcomgod-of-the-depths','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (28,'Apex Azalith',7,'apexazalith',2,0,0,'Usar o Decay na Mensagem "I WILL BURN THIS REALM TO THE GROUND" , e curar sempre que o Pessoal ficar com 1% HP , Evitar de Curar na Mensagem "Azalith inverts your healing!"','https://aqwwiki.wikidot.com/httpaqwwikiwikidotcomazalith-morningstar','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (29,'Dungeon Grimskull',1,'gaolcell',2,0,0,'','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (30,'Nerfkitten',7,'voidnerfkitten',1,0,0,'O LR deve usar o Taunt na Mensagem "Meow"','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (31,'Nightbane',7,'voidnightbane',1,0,0,'Evitar de Iniciar a Fight Sozinho e manter o Decay / Cura Sempre Ativa','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (32,'Na''al',1,'infernalarena',2,0,0,'Usar Classes de Explosão de Dano matando antes das Mecânicas ou Usar Classes de Regen / Redução de Dano','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (33,'Azalith''s Scythe',1,'infernalarena',2,0,0,'Usar Classes com 100% de Acerto / Regen HP/ Redução de Dano','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (34,'Xyfrag',7,'voidxyfrag',1,0,0,'O LR deve usar o Taunt na Mensagem "BLEEEEEEEEEEEECCH"','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (35,'Moon & Sun',4,'templeshrine',3,0,0,'Prestar Atenção na Gerencia de dano no Sun e Moon evitando o Cancelamento da Run','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',0,1364015684379738233);
INSERT INTO "bosses" VALUES (36,'Mecha Binky',7,'grimchallenge',3,0,0,'se errar morre.','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,1364016022369075201);
INSERT INTO "bosses" VALUES (37,'Astral Empyrean',7,'astralshrine',2,0,0,'Prestar Atenção nas Zonas evitando de ficar nelas, Lembrando que a cada Morte o Boss Fica mais Forte','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "bosses" VALUES (38,'Dark Carnax',7,'darkcarnax',1,0,0,'Não ficar nas Zonas Vermelhas','','','https://jix-aqw.github.io/site/ultrahub/assets/ultra-hub.gif','',1,0);
INSERT INTO "guild_roles" VALUES (1,'Duffer','Membro no mais baixo status.',0,0,0,0,0,0,'2025-08-18 03:13:37','2025-08-18 03:13:37');
INSERT INTO "guild_roles" VALUES (2,'Membro','Membro normal da guilda.',0,0,0,0,0,1,'2025-08-18 03:14:19','2025-08-18 03:14:19');
INSERT INTO "guild_roles" VALUES (3,'Recrutador','Responsável por conduzir processos de recrutamento de novos membros.',1,0,0,0,0,1,'2025-08-18 03:14:27','2025-08-18 03:14:27');
INSERT INTO "guild_roles" VALUES (4,'Oficial','Responsável direto pelos recrutadores e pela gestão da guilda em nível micro.',1,1,1,1,1,1,'2025-08-18 03:14:34','2025-08-18 03:14:34');
INSERT INTO "guild_roles" VALUES (5,'Lider','Responsável direto pela administração da guilda em nível macro.',1,1,1,1,1,1,'2025-08-18 03:14:40','2025-08-18 03:14:40');
INSERT INTO "raid_status" VALUES (1,'Recruta','A raid está aberta e ainda precisa de jogadores. Os interessados podem entrar para completar a equipe.');
INSERT INTO "raid_status" VALUES (2,'Pronta','Todos os membros necessários já se juntaram e a raid está pronta para começar');
INSERT INTO "raid_status" VALUES (3,'Em Andamento','A raid começou e os jogadores estão enfrentando o boss.');
INSERT INTO "raid_status" VALUES (4,'Finalizada','A raid terminou com sucesso, o boss foi derrotado ou o objetivo foi alcançado.');
INSERT INTO "raid_status" VALUES (5,'Cancelada','A raid foi cancelada antes de começar, seja por falta de membros ou decisão do líder.');
INSERT INTO "raid_type" VALUES (1,'Livre','O modo LIVRE permite com que os jogadores encontrem outros jogadores com apenas uma única restrição: ser nível 100.');
INSERT INTO "raid_type" VALUES (2,'Meta','O modo META permite com que os usuários façam filtros de classes necessárias para lutar contra um boss.');
COMMIT;
