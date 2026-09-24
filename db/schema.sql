-- =========================================================
-- Wholesaler SaaS — core schema
-- Postgres 14+. Run against a fresh database.
-- =========================================================

create extension if not exists "uuid-ossp";

-- ---------------------------------------------------------
-- Organizations & users (multi-tenant: everything hangs off org_id)
-- ---------------------------------------------------------
create table organizations (
    id            uuid primary key default uuid_generate_v4(),
    name          text not null,
    plan          text not null default 'trial',       -- trial | starter | pro | team
    stripe_customer_id text,
    created_at    timestamptz not null default now()
);

create table users (
    id            uuid primary key default uuid_generate_v4(),
    org_id        uuid not null references organizations(id) on delete cascade,
    email         text not null unique,
    full_name     text,
    role          text not null default 'member',       -- owner | acquisitions | dispositions | member
    auth_provider_id text,                               -- id from Clerk/Supabase Auth
    created_at    timestamptz not null default now()
);

create index idx_users_org on users(org_id);

-- ---------------------------------------------------------
-- Pipeline stages (customizable per org, seeded with defaults)
-- ---------------------------------------------------------
create table pipeline_stages (
    id            uuid primary key default uuid_generate_v4(),
    org_id        uuid not null references organizations(id) on delete cascade,
    name          text not null,                         -- New Lead, Under Contract, Assigned, Closed, Dead
    sort_order    int not null,
    is_closed_won boolean not null default false,
    is_closed_lost boolean not null default false
);

-- ---------------------------------------------------------
-- Deals (the property under consideration)
-- ---------------------------------------------------------
create table deals (
    id                 uuid primary key default uuid_generate_v4(),
    org_id             uuid not null references organizations(id) on delete cascade,
    created_by         uuid references users(id),
    stage_id           uuid references pipeline_stages(id),

    address_line1      text not null,
    city               text not null,
    state              text not null,
    zip                text not null,
    beds               int,
    baths              numeric(3,1),
    sqft               int,
    lot_size_sqft      int,
    year_built         int,

    -- seller / contract side
    seller_name        text,
    seller_phone       text,
    asking_price        numeric(12,2),
    contract_price      numeric(12,2),        -- what wholesaler contracts the property for
    earnest_money       numeric(12,2),
    contract_date        date,
    closing_deadline      date,

    -- valuation inputs (also see comps table)
    repair_estimate      numeric(12,2) default 0,
    arv                   numeric(12,2),        -- after-repair value, computed or manually overridden
    mao                   numeric(12,2),        -- max allowable offer, computed

    -- disposition side
    assignment_fee        numeric(12,2),
    buyer_purchase_price  numeric(12,2),

    status_notes           text,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

create index idx_deals_org on deals(org_id);
create index idx_deals_stage on deals(stage_id);
create index idx_deals_zip on deals(zip);

-- ---------------------------------------------------------
-- Comps used to derive ARV for a deal
-- ---------------------------------------------------------
create table comps (
    id             uuid primary key default uuid_generate_v4(),
    deal_id        uuid not null references deals(id) on delete cascade,
    address        text not null,
    sale_price     numeric(12,2) not null,
    sale_date      date,
    sqft           int,
    beds           int,
    baths          numeric(3,1),
    distance_miles numeric(5,2),
    source         text default 'manual',      -- manual | rentcast | attom
    created_at     timestamptz not null default now()
);

create index idx_comps_deal on comps(deal_id);

-- ---------------------------------------------------------
-- Buyers (cash buyers / rehabbers / landlords)
-- ---------------------------------------------------------
create table buyers (
    id              uuid primary key default uuid_generate_v4(),
    org_id          uuid not null references organizations(id) on delete cascade,
    name            text not null,
    email           text,
    phone           text,
    buyer_type      text,                        -- cash | rehabber | landlord | flipper
    markets         text[],                       -- e.g. {'Ernakulam','Kochi'} or zip codes
    min_price       numeric(12,2),
    max_price       numeric(12,2),
    property_types  text[],                       -- e.g. {'single_family','duplex'}
    min_beds        int,
    notes           text,
    created_at      timestamptz not null default now()
);

create index idx_buyers_org on buyers(org_id);

-- deal <-> buyer matching / outreach tracking
create table deal_buyer_matches (
    id            uuid primary key default uuid_generate_v4(),
    deal_id       uuid not null references deals(id) on delete cascade,
    buyer_id      uuid not null references buyers(id) on delete cascade,
    match_score   numeric(5,2),                  -- 0-100, computed
    status        text not null default 'suggested', -- suggested | sent | viewed | offer_made | rejected | won
    sent_at       timestamptz,
    created_at    timestamptz not null default now(),
    unique (deal_id, buyer_id)
);

-- ---------------------------------------------------------
-- Contracts / e-signature tracking
-- ---------------------------------------------------------
create table contracts (
    id                 uuid primary key default uuid_generate_v4(),
    deal_id            uuid not null references deals(id) on delete cascade,
    contract_type      text not null,               -- purchase_agreement | assignment_agreement
    template_id        text,
    esign_provider      text,                        -- dropbox_sign | docusign
    esign_document_id   text,
    status               text not null default 'draft', -- draft | sent | signed | declined
    file_url             text,
    sent_at              timestamptz,
    signed_at            timestamptz,
    created_at           timestamptz not null default now()
);

create index idx_contracts_deal on contracts(deal_id);

-- ---------------------------------------------------------
-- Seed default pipeline stages helper (call per new org)
-- ---------------------------------------------------------
-- insert into pipeline_stages (org_id, name, sort_order, is_closed_won, is_closed_lost) values
--   ('<org_id>', 'New Lead', 1, false, false),
--   ('<org_id>', 'Under Contract', 2, false, false),
--   ('<org_id>', 'Assigned', 3, false, false),
--   ('<org_id>', 'Closed', 4, true, false),
--   ('<org_id>', 'Dead', 5, false, true);
