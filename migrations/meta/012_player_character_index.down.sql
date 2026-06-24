-- 012_player_character_index.down.sql
-- WARNING: drops PC index. Only legitimate in dev teardown.
DROP TABLE IF EXISTS player_character_index CASCADE;
DROP FUNCTION IF EXISTS player_character_index_touch_updated_at() CASCADE;
