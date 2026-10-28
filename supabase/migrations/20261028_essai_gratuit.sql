-- HelpVA — offre gratuite : 50 médias par PC, sans code d'activation.
--
-- À FAIRE PAR CHRIST (une seule fois) :
--   Supabase > SQL Editor : coller et exécuter CE fichier. C'est tout : pas de fonction Edge
--   à redéployer, pas de nouveau secret. L'app appelle ces deux fonctions avec la clé anon.
-- Tant que ce n'est pas fait, un nouveau PC sans licence voit « Connexion internet requise »
-- (le serveur ne répond pas à l'essai) : il peut toujours entrer un code.
--
-- Principe : on retient l'EMPREINTE de chaque média traité pendant l'essai (même empreinte
-- que le compteur d'activité : taille + début + fin du fichier). Donc :
--   - retraiter le même média ne recompte pas ;
--   - réinstaller HelpVA ne redonne pas 50 médias (tout est ici, par PC) ;
--   - au plus 50 lignes par PC : la table reste minuscule.
-- Pour changer le nombre de médias offerts : modifier QUOTA dans les deux fonctions.

create table if not exists public.essais (
  empreinte text        not null,               -- PC (« ABCD-EFGH-IJKL-MNOP »)
  media     text        not null,               -- empreinte du média (20 caractères hexa)
  cree_le   timestamptz not null default now(),
  primary key (empreinte, media)
);

-- RLS activé SANS policy : la clé anon ne peut ni lire ni écrire la table directement.
-- Elle passe UNIQUEMENT par les deux fonctions ci-dessous (security definer).
alter table public.essais enable row level security;


-- Où en est l'essai de ce PC ?
create or replace function public.essai_statut(p_empreinte text)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  quota constant int := 50;
  n int;
begin
  if p_empreinte is null or p_empreinte !~ '^[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$' then
    raise exception 'empreinte invalide';
  end if;
  select count(*) into n from essais where empreinte = p_empreinte;
  return json_build_object('quota', quota, 'utilises', n, 'restant', greatest(0, quota - n));
end
$$;


-- Réserve les médias d'un traitement AVANT qu'il démarre. Tout ou rien : si les médias
-- NOUVEAUX dépassent ce qui reste, rien n'est enregistré et ok = false.
create or replace function public.essai_reserver(p_empreinte text, p_medias text[])
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  quota constant int := 50;
  n int;
  nouveaux int;
begin
  if p_empreinte is null or p_empreinte !~ '^[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$' then
    raise exception 'empreinte invalide';
  end if;
  if p_medias is null or cardinality(p_medias) > quota then
    raise exception 'liste de médias invalide';
  end if;
  -- Deux traitements lancés en même temps sur le même PC : l'un attend l'autre.
  perform pg_advisory_xact_lock(hashtext('essai:' || p_empreinte));
  select count(*) into n from essais where empreinte = p_empreinte;
  select count(distinct m) into nouveaux
    from unnest(p_medias) as m
   where m ~ '^[0-9a-f]{20}$'
     and not exists (select 1 from essais e where e.empreinte = p_empreinte and e.media = m);
  if n + nouveaux > quota then
    return json_build_object('ok', false, 'quota', quota, 'utilises', n,
                             'restant', greatest(0, quota - n), 'nouveaux', nouveaux);
  end if;
  insert into essais (empreinte, media)
  select distinct p_empreinte, m from unnest(p_medias) as m where m ~ '^[0-9a-f]{20}$'
  on conflict do nothing;
  return json_build_object('ok', true, 'quota', quota, 'utilises', n + nouveaux,
                           'restant', quota - n - nouveaux, 'nouveaux', nouveaux);
end
$$;

revoke all on function public.essai_statut(text) from public;
revoke all on function public.essai_reserver(text, text[]) from public;
grant execute on function public.essai_statut(text) to anon, authenticated;
grant execute on function public.essai_reserver(text, text[]) to anon, authenticated;
