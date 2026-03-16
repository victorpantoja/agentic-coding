-- Remove gen_random_uuid() default so Python supplies uuid7() values explicitly.
-- All task_history primary keys must be timestamp-ordered (uuid7), never random.
ALTER TABLE task_history ALTER COLUMN id DROP DEFAULT;
