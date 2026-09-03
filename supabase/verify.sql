-- verify.sql
-- Jalankan SETELAH migrasi 001-008 selesai, untuk memastikan semuanya terbentuk.
-- File ini hanya membaca; tidak mengubah apa pun.

-- 1. Harus 28 tabel, 4 view, 4 fungsi RPC.
select
    (select count(*) from information_schema.tables
      where table_schema = 'public' and table_type = 'BASE TABLE')            as tabel,
    (select count(*) from information_schema.views
      where table_schema = 'public' and table_name like 'v\_%')               as view,
    (select count(*) from information_schema.routines
      where routine_schema = 'public'
        and routine_name in ('search_products', 'check_availability',
                             'recommend_size', 'track_order'))                as rpc_chatbot,
    (select count(*) from pg_indexes where schemaname = 'public')             as index_terpasang;

-- 2. Daftar tabel yang seharusnya ada. Kolom 'ada' harus true semua.
with harus_ada(nama) as (
    values
        ('categories'), ('collections'), ('colors'), ('sizes'),
        ('size_charts'), ('size_chart_entries'), ('products'),
        ('product_variants'), ('product_images'), ('tags'), ('product_tags'),
        ('warehouses'), ('inventory'), ('inventory_movements'), ('restock_schedule'),
        ('customers'), ('addresses'), ('promotions'), ('promotion_products'),
        ('orders'), ('order_items'), ('shipments'), ('return_requests'),
        ('conversations'), ('messages'), ('message_tool_calls'),
        ('escalations'), ('unanswered_queries')
)
select
    h.nama,
    (t.table_name is not null) as ada
from harus_ada h
left join information_schema.tables t
       on t.table_schema = 'public' and t.table_name = h.nama
order by ada, h.nama;

-- 3. Kolom full-text search di products harus berupa generated column.
select
    column_name,
    is_generated,
    generation_expression is not null as punya_ekspresi
from information_schema.columns
where table_schema = 'public'
  and table_name = 'products'
  and column_name = 'search_vector';

-- 4. RLS harus aktif di tabel yang memuat data pribadi dan operasional.
select
    c.relname as tabel,
    c.relrowsecurity as rls_aktif
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and c.relname in ('customers', 'addresses', 'orders', 'messages', 'conversations')
order by c.relname;

-- 5. Uji cepat RPC. Sebelum seeding, semuanya wajar mengembalikan 0 baris
--    TANPA error. Error di sini berarti migrasi 006/007 belum jalan benar.
select count(*) as hasil_search_products from search_products('kaos', null, null, false, 5);
select count(*) as hasil_check_availability from check_availability('KAO-0001', null, null);
select count(*) as hasil_track_order from track_order('INV-2026-000001', '0000');

-- 6. Setelah scripts/seed_database.py dijalankan, angka-angka ini harus > 0.
select
    (select count(*) from products)                                as produk,
    (select count(*) from product_variants)                        as varian,
    (select count(*) from orders)                                  as pesanan,
    (select count(*) from v_variant_availability
      where available_quantity > 0)                                as varian_ready,
    (select count(*) from v_variant_availability
      where available_quantity = 0 and next_restock_date is not null) as habis_ada_restock,
    (select count(*) from v_active_promotions)                     as promo_aktif;
