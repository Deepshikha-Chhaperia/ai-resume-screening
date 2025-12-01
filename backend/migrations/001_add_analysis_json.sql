-- Migration: add analysis_json JSONB column to screening_results
ALTER TABLE screening_results
ADD COLUMN IF NOT EXISTS analysis_json JSONB;

-- Backfill: if recruiter_comments contains JSON, attempt to parse and copy into analysis_json
-- Note: run manually in psql if desired (best-effort, safe to run repeatedly)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='screening_results' AND column_name='analysis_json') THEN
        UPDATE screening_results
        SET analysis_json = CASE
            WHEN (recruiter_comments IS NOT NULL AND recruiter_comments::text <> '') THEN
                (CASE WHEN jsonb_typeof(recruiter_comments::jsonb) IS NOT NULL THEN recruiter_comments::jsonb ELSE NULL END)
            ELSE NULL END
        WHERE analysis_json IS NULL;
    END IF;
END
$$;
