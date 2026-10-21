-- HelpVA — compteur d'activité des VA (envoyé par l'app, lu par la console d'admin).
--
-- À FAIRE PAR CHRIST (une seule fois, dans cet ordre) :
--   1. Supabase > SQL Editor : coller et exécuter CE fichier.
--   2. Redéployer la fonction Edge « admin » (supabase/functions/admin/index.ts)
--      avec « Verify JWT » DÉSACTIVÉ (comme avant : l'app appelle avec la clé anon).
--      Aucun nouveau secret : PRIVEE_PEM et ADMIN_MDP restent les mêmes.
--   3. Republier web/admin.html sur Netlify (nouvel onglet « Activité »).
-- Tant que l'étape 1 n'est pas faite, l'app réessaie simplement plus tard : rien ne casse.
--
-- Une ligne par licence et par jour. L'app envoie les valeurs ABSOLUES du jour
-- (pas des « + n ») : renvoyer deux fois le même jour ne compte jamais en double.

create table if not exists public.activite (
  licence_id   uuid        not null references public.licences(id) on delete cascade,
  jour         date        not null,               -- date LOCALE du PC du VA
  images       int         not null default 0,     -- images converties
  videos       int         not null default 0,     -- vidéos converties en MP4
  metadonnees  int         not null default 0,     -- médias passés dans Métadonnées
  ranges       int         not null default 0,     -- médias copiés par le Ranger
  maj_le       timestamptz not null default now(), -- dernier envoi reçu pour ce jour
  primary key (licence_id, jour)
);

-- La console lit « les 90 derniers jours, toutes licences » : index sur le jour.
-- (Les recherches par licence utilisent déjà la clé primaire.)
create index if not exists activite_jour_idx on public.activite (jour);

-- Sécurité : RLS activé SANS aucune policy -> la clé anon (publique, dans l'app) ne peut
-- ni lire ni écrire cette table. Seule la fonction Edge « admin » (clé service_role, qui
-- contourne RLS) y accède, après avoir vérifié la licence ou le mot de passe admin.
alter table public.activite enable row level security;
