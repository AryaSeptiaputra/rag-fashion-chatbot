-- 001_extensions.sql
-- Ekstensi Postgres yang dipakai skema. Jalankan paling awal.

create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "pg_trgm";    -- toleransi typo pada nama produk

-- Catatan: full-text search memakai konfigurasi bawaan 'indonesian' (snowball),
-- bukan konfigurasi kustom berbasis unaccent. Bahasa Indonesia baku tidak memakai
-- diakritik, jadi unaccent nyaris tidak menambah recall, sementara membangun
-- text search configuration kustom bergantung pada schema tempat ekstensi
-- dipasang (di Supabase: 'extensions', bukan 'public') dan mudah gagal.
-- Toleransi salah ketik sudah ditangani pg_trgm di RPC search_products.
