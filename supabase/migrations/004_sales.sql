-- 004_sales.sql
-- Domain penjualan: pelanggan, alamat, pesanan, pengiriman, retur, promo.
-- Tabel customers & addresses berisi PII dan sengaja TIDAK dijangkau tool chatbot.

create table if not exists customers (
    id          uuid primary key default gen_random_uuid(),
    full_name   text not null,
    email       text not null unique,
    phone       text not null,
    created_at  timestamptz not null default now()
);

create table if not exists addresses (
    id           uuid primary key default gen_random_uuid(),
    customer_id  uuid not null references customers(id) on delete cascade,
    recipient    text not null,
    phone        text not null,
    line1        text not null,
    city         text not null,
    province     text not null,
    postal_code  text not null,
    is_default   boolean not null default false
);

create table if not exists promotions (
    id              uuid primary key default gen_random_uuid(),
    code            text not null unique,
    name            text not null,
    discount_type   text not null check (discount_type in ('percentage', 'fixed')),
    discount_value  numeric(12,2) not null check (discount_value > 0),
    min_purchase    numeric(12,2) not null default 0 check (min_purchase >= 0),
    start_at        timestamptz not null,
    end_at          timestamptz not null,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    constraint promo_period_valid check (end_at > start_at)
);

-- Promo tanpa baris di sini berlaku untuk seluruh katalog.
create table if not exists promotion_products (
    promotion_id  uuid not null references promotions(id) on delete cascade,
    product_id    uuid not null references products(id) on delete cascade,
    primary key (promotion_id, product_id)
);

create table if not exists orders (
    id               uuid primary key default gen_random_uuid(),
    order_number     text not null unique,
    customer_id      uuid not null references customers(id) on delete restrict,
    address_id       uuid references addresses(id) on delete set null,
    promotion_id     uuid references promotions(id) on delete set null,
    status           text not null default 'pending'
                     check (status in ('pending', 'paid', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded')),
    subtotal         numeric(12,2) not null default 0 check (subtotal >= 0),
    discount_amount  numeric(12,2) not null default 0 check (discount_amount >= 0),
    shipping_cost    numeric(12,2) not null default 0 check (shipping_cost >= 0),
    total            numeric(12,2) not null default 0 check (total >= 0),
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create table if not exists order_items (
    id          uuid primary key default gen_random_uuid(),
    order_id    uuid not null references orders(id) on delete cascade,
    variant_id  uuid not null references product_variants(id) on delete restrict,
    quantity    int not null check (quantity > 0),
    unit_price  numeric(12,2) not null check (unit_price >= 0)
);

create table if not exists shipments (
    id               uuid primary key default gen_random_uuid(),
    order_id         uuid not null references orders(id) on delete cascade,
    courier          text not null,
    tracking_number  text,
    status           text not null default 'preparing'
                     check (status in ('preparing', 'picked_up', 'in_transit', 'out_for_delivery', 'delivered', 'failed', 'returned')),
    shipped_at       timestamptz,
    delivered_at     timestamptz,
    created_at       timestamptz not null default now()
);

create table if not exists return_requests (
    id           uuid primary key default gen_random_uuid(),
    order_id     uuid not null references orders(id) on delete cascade,
    reason       text not null check (reason in ('size_mismatch', 'defective', 'wrong_item', 'changed_mind', 'other')),
    description  text,
    status       text not null default 'requested'
                 check (status in ('requested', 'approved', 'rejected', 'received', 'refunded')),
    created_at   timestamptz not null default now(),
    resolved_at  timestamptz
);
