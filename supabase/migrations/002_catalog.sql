-- 002_catalog.sql
-- Domain katalog: kategori, koleksi, atribut varian, produk, gambar, tag.

-- Kategori hierarkis (mis. Atasan > Kaos > Oversize).
create table if not exists categories (
    id          uuid primary key default gen_random_uuid(),
    parent_id   uuid references categories(id) on delete set null,
    name        text not null,
    slug        text not null unique,
    sort_order  int  not null default 0,
    created_at  timestamptz not null default now()
);

-- Koleksi / seasonal drop.
create table if not exists collections (
    id           uuid primary key default gen_random_uuid(),
    name         text not null,
    slug         text not null unique,
    season       text not null check (season in ('spring', 'summer', 'fall', 'winter', 'all-season')),
    year         int  not null check (year between 2000 and 2100),
    launch_date  date,
    is_active    boolean not null default true,
    created_at   timestamptz not null default now()
);

create table if not exists colors (
    id        uuid primary key default gen_random_uuid(),
    name      text not null unique,
    hex_code  text not null check (hex_code ~ '^#[0-9A-Fa-f]{6}$')
);

create table if not exists sizes (
    id          uuid primary key default gen_random_uuid(),
    label       text not null unique,
    sort_order  int  not null
);

-- Size chart dipisah per potongan & gender karena "L" pada regular fit
-- tidak sama dengan "L" pada oversize fit.
create table if not exists size_charts (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    fit_type   text not null check (fit_type in ('regular', 'slim', 'oversize', 'boxy')),
    gender     text not null check (gender in ('men', 'women', 'unisex')),
    unique (fit_type, gender)
);

create table if not exists size_chart_entries (
    id             uuid primary key default gen_random_uuid(),
    size_chart_id  uuid not null references size_charts(id) on delete cascade,
    size_id        uuid not null references sizes(id) on delete cascade,
    chest_cm       numeric(5,1) not null,
    waist_cm       numeric(5,1) not null,
    length_cm      numeric(5,1) not null,
    shoulder_cm    numeric(5,1),
    unique (size_chart_id, size_id)
);

create table if not exists products (
    id                 uuid primary key default gen_random_uuid(),
    sku                text not null unique,
    name               text not null,
    description        text not null default '',
    category_id        uuid references categories(id) on delete set null,
    collection_id      uuid references collections(id) on delete set null,
    size_chart_id      uuid references size_charts(id) on delete set null,
    base_price         numeric(12,2) not null check (base_price >= 0),
    material           text not null default '',
    care_instructions  text not null default '',
    fit_type           text not null default 'regular'
                       check (fit_type in ('regular', 'slim', 'oversize', 'boxy')),
    gender             text not null default 'unisex'
                       check (gender in ('men', 'women', 'unisex')),
    is_active          boolean not null default true,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

-- Kolom tsvector di-generate otomatis supaya index FTS tidak pernah basi.
-- Nama produk diberi bobot tertinggi, lalu bahan, lalu deskripsi.
alter table products
    add column if not exists search_vector tsvector
    generated always as (
        setweight(to_tsvector('indonesian', coalesce(name, '')), 'A') ||
        setweight(to_tsvector('indonesian', coalesce(material, '')), 'B') ||
        setweight(to_tsvector('indonesian', coalesce(description, '')), 'C')
    ) stored;

create table if not exists product_variants (
    id              uuid primary key default gen_random_uuid(),
    product_id      uuid not null references products(id) on delete cascade,
    size_id         uuid not null references sizes(id) on delete restrict,
    color_id        uuid not null references colors(id) on delete restrict,
    variant_sku     text not null unique,
    price_override  numeric(12,2) check (price_override >= 0),
    weight_grams    int check (weight_grams > 0),
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    unique (product_id, size_id, color_id)
);

create table if not exists product_images (
    id          uuid primary key default gen_random_uuid(),
    product_id  uuid not null references products(id) on delete cascade,
    variant_id  uuid references product_variants(id) on delete cascade,
    url         text not null,
    is_primary  boolean not null default false,
    sort_order  int not null default 0
);

create table if not exists tags (
    id    uuid primary key default gen_random_uuid(),
    name  text not null unique,
    slug  text not null unique
);

create table if not exists product_tags (
    product_id  uuid not null references products(id) on delete cascade,
    tag_id      uuid not null references tags(id) on delete cascade,
    primary key (product_id, tag_id)
);
