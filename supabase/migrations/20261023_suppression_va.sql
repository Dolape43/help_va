-- HelpVA — « Supprimer un VA » depuis la console d'admin.
--
-- À FAIRE PAR CHRIST (une seule fois) : Supabase > SQL Editor, coller et exécuter CE fichier,
-- AVANT de redéployer la fonction « admin ».
--
-- Pourquoi une colonne et pas un vrai DELETE ? Si la ligne disparaissait, l'application ne
-- trouverait plus la licence sur le serveur… et la laisserait marcher (elle ne bloque que les
-- licences « résiliée » ou « suspendu »). Supprimer = résilier + masquer : le VA est bloqué à sa
-- prochaine connexion et disparaît des listes de la console, mais l'historique reste en base.

alter table public.licences add column if not exists supprime_le timestamptz;
