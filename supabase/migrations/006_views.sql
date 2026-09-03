-- 006_views.sql
-- Lapisan peredam kompleksitas: view pipih yang menyembunyikan join antar 28 tabel.
-- Chatbot HANYA membaca view & RPC di sini, tidak pernah tabel mentah.

-- Stok yang bisa dijual per varian, diagregasi lintas gudang aktif.
create or replace view v_variant_availability as
select
    pv.id                                            as variant_id,
    pv.variant_sku,
    p.id                                             as product_id,
    p.sku                                            as product_sku,
    p.name                                           as product_name,
    p.is_active                                      as product_is_active,
    pv.is_active                                     as variant_is_active,
    s.label                                          as size,
    c.name                                           as color,
    coalesce(pv.price_override, p.base_price)        as price,
    -- Gudang nonaktif harus dikeluarkan dari hitungan. Kondisi w.is_active
    -- tidak boleh ditaruh di ON milik LEFT JOIN: itu hanya membuat kolom w
    -- bernilai NULL, sementara baris inventory-nya tetap ikut terjumlah.
    coalesce(
        sum(
            case
                when w.is_active
                then inv.quantity_on_hand - inv.quantity_reserved
                else 0
            end
        ),
        0
    )::int                                           as available_quantity,
    (
        count(distinct inv.warehouse_id) filter (
            where w.is_active
              and inv.quantity_on_hand - inv.quantity_reserved > 0
        )
    )::int                                           as warehouse_count,
    (
        select min(rs.expected_date)
        from restock_schedule rs
        where rs.variant_id = pv.id
          and rs.status in ('scheduled', 'delayed')
          and rs.expected_date >= current_date
    )                                                as next_restock_date
from product_variants pv
join products p on p.id = pv.product_id
join sizes  s on s.id = pv.size_id
join colors c on c.id = pv.color_id
left join inventory  inv on inv.variant_id = pv.id
left join warehouses w   on w.id = inv.warehouse_id
group by pv.id, pv.variant_sku, p.id, p.sku, p.name, p.is_active,
         pv.is_active, s.label, c.name, pv.price_override, p.base_price;

-- Katalog produk pipih: satu baris per produk, atribut turunan sudah diagregasi.
create or replace view v_product_catalog as
select
    p.id                     as product_id,
    p.sku,
    p.name,
    p.description,
    p.material,
    p.care_instructions,
    p.fit_type,
    p.gender,
    p.base_price,
    p.is_active,
    cat.name                 as category,
    col.name                 as collection,
    col.season,
    col.year                 as collection_year,
    coalesce(tag_agg.tags, array[]::text[])          as tags,
    coalesce(var_agg.colors, array[]::text[])        as available_colors,
    coalesce(var_agg.sizes, array[]::text[])         as available_sizes,
    coalesce(var_agg.min_price, p.base_price)        as min_price,
    coalesce(var_agg.max_price, p.base_price)        as max_price,
    coalesce(var_agg.total_available, 0)::int        as total_available,
    coalesce(var_agg.variant_count, 0)::int          as variant_count
from products p
left join categories  cat on cat.id = p.category_id
left join collections col on col.id = p.collection_id
left join lateral (
    select
        array_agg(distinct t.name order by t.name) as tags
    from product_tags pt
    join tags t on t.id = pt.tag_id
    where pt.product_id = p.id
) tag_agg on true
left join lateral (
    select
        array_agg(distinct va.color) filter (where va.available_quantity > 0) as colors,
        array_agg(distinct va.size)  filter (where va.available_quantity > 0) as sizes,
        min(va.price)                                                        as min_price,
        max(va.price)                                                        as max_price,
        sum(va.available_quantity)                                           as total_available,
        count(*)                                                             as variant_count
    from v_variant_availability va
    where va.product_id = p.id and va.variant_is_active
) var_agg on true;

-- Pelacakan pesanan tanpa membocorkan PII: tidak ada email, alamat lengkap,
-- atau nomor HP utuh. Verifikasi identitas ditegakkan di RPC track_order.
create or replace view v_order_tracking as
select
    o.id                                          as order_id,
    o.order_number,
    o.status                                      as order_status,
    o.total,
    o.created_at                                  as ordered_at,
    right(cust.phone, 4)                          as phone_last4,
    left(cust.full_name, 1) || '***'              as customer_masked,
    sh.courier,
    sh.tracking_number,
    sh.status                                     as shipment_status,
    sh.shipped_at,
    sh.delivered_at,
    coalesce(item_agg.items, array[]::text[])     as items,
    coalesce(item_agg.item_count, 0)::int         as item_count,
    ret.status                                    as return_status
from orders o
join customers cust on cust.id = o.customer_id
left join shipments sh on sh.order_id = o.id
left join lateral (
    select
        array_agg(
            p.name || ' (' || s.label || '/' || c.name || ') x' || oi.quantity
            order by p.name
        ) as items,
        sum(oi.quantity) as item_count
    from order_items oi
    join product_variants pv on pv.id = oi.variant_id
    join products p on p.id = pv.product_id
    join sizes  s on s.id = pv.size_id
    join colors c on c.id = pv.color_id
    where oi.order_id = o.id
) item_agg on true
left join lateral (
    select rr.status
    from return_requests rr
    where rr.order_id = o.id
    order by rr.created_at desc
    limit 1
) ret on true;

-- Promo yang benar-benar berlaku saat ini. Promo kedaluwarsa atau belum mulai
-- tidak muncul di sini, sehingga chatbot tidak bisa menjanjikannya.
create or replace view v_active_promotions as
select
    pr.id            as promotion_id,
    pr.code,
    pr.name,
    pr.discount_type,
    pr.discount_value,
    pr.min_purchase,
    pr.start_at,
    pr.end_at,
    coalesce(prod_agg.product_skus, array[]::text[]) as product_skus,
    coalesce(prod_agg.product_names, array[]::text[]) as product_names,
    (prod_agg.product_skus is null)                   as applies_to_all
from promotions pr
left join lateral (
    select
        array_agg(p.sku  order by p.sku)  as product_skus,
        array_agg(p.name order by p.sku)  as product_names
    from promotion_products pp
    join products p on p.id = pp.product_id
    where pp.promotion_id = pr.id
) prod_agg on true
where pr.is_active
  and pr.start_at <= now()
  and pr.end_at   >= now();
