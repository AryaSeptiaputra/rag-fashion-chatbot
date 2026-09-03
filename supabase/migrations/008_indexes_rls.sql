-- 008_indexes_rls.sql
-- Index untuk jalur query yang benar-benar dipakai chatbot, plus RLS.

-- Katalog
create index if not exists idx_products_search      on products using gin (search_vector);
create index if not exists idx_products_name_trgm   on products using gin (name gin_trgm_ops);
create index if not exists idx_products_category    on products (category_id) where is_active;
create index if not exists idx_products_collection  on products (collection_id);
create index if not exists idx_categories_parent    on categories (parent_id);
create index if not exists idx_variants_product     on product_variants (product_id) where is_active;
create index if not exists idx_variants_sku         on product_variants (variant_sku);
create index if not exists idx_sce_chart            on size_chart_entries (size_chart_id);
create index if not exists idx_product_tags_tag     on product_tags (tag_id);
create index if not exists idx_product_images_prod  on product_images (product_id);

-- Inventori: agregasi stok selalu difilter per varian.
create index if not exists idx_inventory_variant    on inventory (variant_id);
create index if not exists idx_inventory_warehouse  on inventory (warehouse_id);
create index if not exists idx_movements_variant    on inventory_movements (variant_id, created_at desc);
create index if not exists idx_restock_variant      on restock_schedule (variant_id, expected_date)
    where status in ('scheduled', 'delayed');

-- Penjualan
create index if not exists idx_orders_number        on orders (order_number);
create index if not exists idx_orders_customer      on orders (customer_id, created_at desc);
create index if not exists idx_order_items_order    on order_items (order_id);
create index if not exists idx_order_items_variant  on order_items (variant_id);
create index if not exists idx_shipments_order      on shipments (order_id);
create index if not exists idx_returns_order        on return_requests (order_id, created_at desc);
create index if not exists idx_addresses_customer   on addresses (customer_id);
create index if not exists idx_promotions_window    on promotions (start_at, end_at) where is_active;
create index if not exists idx_promotion_products   on promotion_products (product_id);

-- Chatbot: history selalu dibaca per percakapan, urut waktu.
create index if not exists idx_conversations_session on conversations (session_id);
create index if not exists idx_messages_conversation on messages (conversation_id, created_at);
create index if not exists idx_tool_calls_message    on message_tool_calls (message_id);
create index if not exists idx_tool_calls_name       on message_tool_calls (tool_name, created_at desc);
create index if not exists idx_escalations_status    on escalations (status, created_at desc);

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- Backend memakai service-role key yang MEM-BYPASS RLS sepenuhnya; pembatasan
-- akses chatbot ditegakkan di service layer (tool tidak pernah menyentuh
-- customers/addresses). Policy di bawah ditulis supaya skema tetap aman kalau
-- suatu saat frontend mengakses Supabase langsung dengan anon key.
-- ---------------------------------------------------------------------------

alter table customers          enable row level security;
alter table addresses          enable row level security;
alter table orders             enable row level security;
alter table order_items        enable row level security;
alter table shipments          enable row level security;
alter table return_requests    enable row level security;
alter table conversations      enable row level security;
alter table messages           enable row level security;
alter table message_tool_calls enable row level security;
alter table escalations        enable row level security;
alter table unanswered_queries enable row level security;
alter table inventory          enable row level security;
alter table inventory_movements enable row level security;

-- Tanpa policy apa pun, anon key tidak bisa membaca tabel di atas sama sekali.
-- Katalog publik boleh dibaca siapa saja.
alter table products         enable row level security;
alter table product_variants enable row level security;
alter table categories       enable row level security;
alter table collections      enable row level security;
alter table colors           enable row level security;
alter table sizes            enable row level security;
alter table product_images   enable row level security;
alter table tags             enable row level security;
alter table product_tags     enable row level security;

do $$
declare
    tbl text;
begin
    foreach tbl in array array[
        'products', 'product_variants', 'categories', 'collections',
        'colors', 'sizes', 'product_images', 'tags', 'product_tags'
    ]
    loop
        execute format(
            'drop policy if exists %I on %I', 'public_read_' || tbl, tbl
        );
        execute format(
            'create policy %I on %I for select to anon, authenticated using (true)',
            'public_read_' || tbl, tbl
        );
    end loop;
end $$;
