-- 003_inventory.sql
-- Domain inventori: gudang, stok per varian per gudang, mutasi, jadwal restock.

create table if not exists warehouses (
    id         uuid primary key default gen_random_uuid(),
    code       text not null unique,
    name       text not null,
    city       text not null,
    is_active  boolean not null default true
);

-- Stok tersimpan per (varian, gudang). Stok yang bisa dijual adalah
-- quantity_on_hand - quantity_reserved, diagregasi lintas gudang aktif.
create table if not exists inventory (
    id                 uuid primary key default gen_random_uuid(),
    variant_id         uuid not null references product_variants(id) on delete cascade,
    warehouse_id       uuid not null references warehouses(id) on delete cascade,
    quantity_on_hand   int not null default 0 check (quantity_on_hand >= 0),
    quantity_reserved  int not null default 0 check (quantity_reserved >= 0),
    updated_at         timestamptz not null default now(),
    unique (variant_id, warehouse_id),
    constraint reserved_not_exceeding_on_hand check (quantity_reserved <= quantity_on_hand)
);

-- Jejak audit pergerakan stok. Tidak diekspos ke chatbot, dipakai rekonsiliasi.
create table if not exists inventory_movements (
    id             uuid primary key default gen_random_uuid(),
    variant_id     uuid not null references product_variants(id) on delete cascade,
    warehouse_id   uuid not null references warehouses(id) on delete cascade,
    movement_type  text not null check (movement_type in ('restock', 'sale', 'return', 'adjustment', 'transfer')),
    quantity       int not null,
    reference      text,
    created_at     timestamptz not null default now()
);

-- Jadwal restock: menjawab "kapan ready lagi?" tanpa mengarang tanggal.
create table if not exists restock_schedule (
    id                 uuid primary key default gen_random_uuid(),
    variant_id         uuid not null references product_variants(id) on delete cascade,
    expected_date      date not null,
    expected_quantity  int not null check (expected_quantity > 0),
    status             text not null default 'scheduled'
                       check (status in ('scheduled', 'delayed', 'arrived', 'cancelled')),
    note               text,
    created_at         timestamptz not null default now()
);
