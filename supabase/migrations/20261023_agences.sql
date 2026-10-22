-- HelpVA — agences : ranger les VA par agence dans la console d'admin.
--
-- À FAIRE PAR CHRIST (une seule fois, dans cet ordre) :
--   1. Supabase > SQL Editor : coller et exécuter CE fichier.
--   2. Redéployer la fonction Edge « admin » (supabase/functions/admin/index.ts)
--      avec « Verify JWT » DÉSACTIVÉ (comme avant). Aucun nouveau secret.
--   3. Republier web/admin.html sur Netlify (bouton « Agences », filtres et regroupements).
-- Tant que l'étape 1 n'est pas faite, la console et l'activation des VA marchent comme avant,
-- simplement sans agences (la fonction se replie sans ces colonnes).
--
-- Un code créé pour une agence la transmet à la licence lors de l'activation.
-- Supprimer une agence ne supprime aucun VA : ses licences et codes passent « sans agence ».

create table if not exists public.agences (
  id       uuid        primary key default gen_random_uuid(),
  nom      text        not null check (char_length(nom) between 1 and 60),
  cree_le  timestamptz not null default now()
);

-- Pas deux agences du même nom, majuscules comprises (« Erika » = « erika »).
create unique index if not exists agences_nom_unique on public.agences (lower(nom));

-- Agence d'une licence / d'un code (null = « sans agence »).
alter table public.licences add column if not exists agence_id uuid
  references public.agences(id) on delete set null;
alter table public.codes add column if not exists agence_id uuid
  references public.agences(id) on delete set null;

create index if not exists licences_agence_idx on public.licences (agence_id);
create index if not exists codes_agence_idx on public.codes (agence_id);

-- Sécurité : RLS activé SANS aucune policy -> la clé anon (publique, dans l'app) ne peut
-- ni lire ni écrire cette table. Seule la fonction Edge « admin » (clé service_role, qui
-- contourne RLS) y accède, après avoir vérifié le mot de passe admin.
alter table public.agences enable row level security;

-- Que l'API voie tout de suite la nouvelle table et les nouvelles colonnes.
notify pgrst, 'reload schema';
