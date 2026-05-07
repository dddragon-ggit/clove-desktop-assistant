-- Supabase todos table for desktop-mobile sync
CREATE TABLE IF NOT EXISTS todos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    priority TEXT DEFAULT 'normal',
    task_type TEXT DEFAULT 'temporary',
    important BOOLEAN DEFAULT FALSE,
    needs_computer BOOLEAN DEFAULT FALSE,
    due_at TEXT,
    reminder_at TEXT,
    snoozed_until TEXT,
    daily_completed_on TEXT,
    daily_skipped_on TEXT,
    created_at TEXT DEFAULT (now() AT TIME ZONE 'utc')::text,
    updated_at TEXT DEFAULT (now() AT TIME ZONE 'utc')::text,
    completed_at TEXT,
    device_id TEXT DEFAULT 'desktop'
);

-- Enable Row Level Security (required for Supabase)
ALTER TABLE todos ENABLE ROW LEVEL SECURITY;

-- Allow all operations for now (tighten later with auth)
CREATE POLICY "allow_all" ON todos FOR ALL USING (true) WITH CHECK (true);

-- Enable realtime for live sync
ALTER PUBLICATION supabase_realtime ADD TABLE todos;
