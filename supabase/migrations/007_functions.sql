-- 007_functions.sql
-- RPC yang dipanggil chatbot. Tiap fungsi memetakan tepat satu tool agent,
-- sehingga LLM tidak perlu tahu satu pun nama tabel mentah.

-- Pencarian katalog: full-text Bahasa Indonesia, dengan fallback trigram
-- supaya salah ketik ("hodie", "kaoss") tetap ketemu.
create or replace function search_products(
    p_keyword       text default null,
    p_category      text default null,
    p_max_price     numeric default null,
    p_in_stock_only boolean default false,
    p_limit         int default 8
)
returns table (
    sku              text,
    name             text,
    category         text,
    collection       text,
    fit_type         text,
    material         text,
    min_price        numeric,
    max_price        numeric,
    available_colors text[],
    available_sizes  text[],
    total_available  int,
    relevance        real
)
language sql
stable
set search_path = public
as $$
    with q as (
        select
            case
                when p_keyword is null or btrim(p_keyword) = '' then null
                else websearch_to_tsquery('indonesian', p_keyword)
            end as tsq
    )
    select
        pc.sku,
        pc.name,
        pc.category,
        pc.collection,
        pc.fit_type,
        pc.material,
        pc.min_price,
        pc.max_price,
        pc.available_colors,
        pc.available_sizes,
        pc.total_available,
        case
            when q.tsq is null then 1.0::real
            else greatest(
                ts_rank(pc_src.search_vector, q.tsq),
                similarity(pc.name, coalesce(p_keyword, ''))
            )
        end as relevance
    from v_product_catalog pc
    join products pc_src on pc_src.id = pc.product_id
    cross join q
    where pc.is_active
      and (
            q.tsq is null
            or pc_src.search_vector @@ q.tsq
            or pc.name % p_keyword
          )
      and (p_category  is null or pc.category ilike '%' || p_category || '%')
      and (p_max_price is null or pc.min_price <= p_max_price)
      and (not p_in_stock_only or pc.total_available > 0)
    order by relevance desc, pc.total_available desc, pc.name
    limit greatest(1, least(p_limit, 20));
$$;

-- Ketersediaan stok live. Menerima variant_sku maupun sku produk induk,
-- karena LLM sering hanya memegang salah satunya.
create or replace function check_availability(
    p_sku   text,
    p_size  text default null,
    p_color text default null
)
returns table (
    variant_sku        text,
    product_sku        text,
    product_name       text,
    size               text,
    color              text,
    price              numeric,
    available_quantity int,
    is_available       boolean,
    next_restock_date  date
)
language sql
stable
set search_path = public
as $$
    select
        va.variant_sku,
        va.product_sku,
        va.product_name,
        va.size,
        va.color,
        va.price,
        va.available_quantity,
        (va.available_quantity > 0 and va.variant_is_active and va.product_is_active)
            as is_available,
        va.next_restock_date
    from v_variant_availability va
    where (va.variant_sku ilike p_sku or va.product_sku ilike p_sku)
      and (p_size  is null or va.size  ilike p_size)
      and (p_color is null or va.color ilike p_color)
    order by va.size, va.color;
$$;

-- Rekomendasi ukuran dari size chart produk. Selisih diukur terhadap
-- lingkar dada dan pinggang; entri dengan selisih terkecil menang.
create or replace function recommend_size(
    p_sku       text,
    p_chest_cm  numeric,
    p_waist_cm  numeric default null
)
returns table (
    product_sku  text,
    product_name text,
    fit_type     text,
    size         text,
    chest_cm     numeric,
    waist_cm     numeric,
    length_cm    numeric,
    fit_gap_cm   numeric,
    is_best_match boolean
)
language sql
stable
set search_path = public
as $$
    with target as (
        select p.id, p.sku, p.name, p.fit_type, p.size_chart_id
        from products p
        where p.sku ilike p_sku and p.is_active
        limit 1
    ),
    scored as (
        select
            t.sku,
            t.name,
            t.fit_type,
            s.label as size,
            sce.chest_cm,
            sce.waist_cm,
            sce.length_cm,
            round(
                abs(sce.chest_cm - p_chest_cm)
                + coalesce(abs(sce.waist_cm - p_waist_cm), 0)
            , 1) as fit_gap_cm,
            s.sort_order
        from target t
        join size_chart_entries sce on sce.size_chart_id = t.size_chart_id
        join sizes s on s.id = sce.size_id
    )
    select
        sc.sku,
        sc.name,
        sc.fit_type,
        sc.size,
        sc.chest_cm,
        sc.waist_cm,
        sc.length_cm,
        sc.fit_gap_cm,
        sc.fit_gap_cm = min(sc.fit_gap_cm) over () as is_best_match
    from scored sc
    order by sc.fit_gap_cm, sc.sort_order;
$$;

-- Pelacakan pesanan dengan verifikasi identitas wajib.
-- Tanpa 4 digit terakhir nomor HP yang cocok, tidak ada baris yang keluar.
create or replace function track_order(
    p_order_number text,
    p_phone_last4  text
)
returns table (
    order_number    text,
    order_status    text,
    ordered_at      timestamptz,
    total           numeric,
    items           text[],
    item_count      int,
    courier         text,
    tracking_number text,
    shipment_status text,
    shipped_at      timestamptz,
    delivered_at    timestamptz,
    return_status   text
)
language sql
stable
set search_path = public
as $$
    select
        ot.order_number,
        ot.order_status,
        ot.ordered_at,
        ot.total,
        ot.items,
        ot.item_count,
        ot.courier,
        ot.tracking_number,
        ot.shipment_status,
        ot.shipped_at,
        ot.delivered_at,
        ot.return_status
    from v_order_tracking ot
    where upper(btrim(ot.order_number)) = upper(btrim(p_order_number))
      and ot.phone_last4 = btrim(p_phone_last4);
$$;
