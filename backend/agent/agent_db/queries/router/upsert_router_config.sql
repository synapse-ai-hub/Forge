-- Upsert the single router-config row (id = 1).
INSERT INTO router_config (id, agentes, tools, skills, rag, updated_at)
VALUES (1, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    agentes = excluded.agentes,
    tools = excluded.tools,
    skills = excluded.skills,
    rag = excluded.rag,
    updated_at = excluded.updated_at;
