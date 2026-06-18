-- 001_reality_registry.down.sql
DROP TRIGGER  IF EXISTS reality_registry_touch_updated_at_trg ON reality_registry;
DROP FUNCTION IF EXISTS reality_registry_touch_updated_at();
DROP TABLE    IF EXISTS reality_registry CASCADE;
