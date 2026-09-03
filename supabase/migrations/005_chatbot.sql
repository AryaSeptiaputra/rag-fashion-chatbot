-- 005_chatbot.sql
-- Domain operasional chatbot: percakapan, pesan, audit tool call, eskalasi,
-- dan pertanyaan yang tidak terjawab (umpan balik untuk memperbaiki FAQ).

create table if not exists conversations (
    id           uuid primary key default gen_random_uuid(),
    session_id   text not null unique,
    customer_id  uuid references customers(id) on delete set null,
    channel      text not null default 'web'
                 check (channel in ('web', 'whatsapp', 'instagram', 'shopee', 'tokopedia')),
    status       text not null default 'active'
                 check (status in ('active', 'escalated', 'closed')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create table if not exists messages (
    id               uuid primary key default gen_random_uuid(),
    conversation_id  uuid not null references conversations(id) on delete cascade,
    role             text not null check (role in ('user', 'assistant')),
    content          text not null,
    created_at       timestamptz not null default now()
);

-- Audit tiap panggilan tool. Inilah sumber kebenaran untuk eval harness:
-- membuktikan chatbot benar-benar query data, bukan mengarang.
create table if not exists message_tool_calls (
    id              uuid primary key default gen_random_uuid(),
    message_id      uuid not null references messages(id) on delete cascade,
    tool_name       text not null,
    arguments       jsonb not null default '{}'::jsonb,
    result_summary  text,
    is_error        boolean not null default false,
    latency_ms      int check (latency_ms >= 0),
    created_at      timestamptz not null default now()
);

create table if not exists escalations (
    id               uuid primary key default gen_random_uuid(),
    conversation_id  uuid not null references conversations(id) on delete cascade,
    reason           text not null,
    contact          text,
    status           text not null default 'open'
                     check (status in ('open', 'in_progress', 'resolved')),
    created_at       timestamptz not null default now(),
    resolved_at      timestamptz
);

create table if not exists unanswered_queries (
    id               uuid primary key default gen_random_uuid(),
    conversation_id  uuid references conversations(id) on delete set null,
    query            text not null,
    created_at       timestamptz not null default now()
);
