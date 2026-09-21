"""
Configuration centrale de l'agent.
Tu modifies ce fichier, pas le reste du code.
"""

# --- Rangement des médias selon le calendrier ---
# Dossiers sources où TU déposes tes médias bruts :
DOSSIER_SOURCE_VIDEOS = "sources/videos"    # -> utilisées pour les Reels
DOSSIER_SOURCE_IMAGES = "sources/images"    # -> Carousels (plusieurs) + Stories (1)
# Dossier de sortie où l'agent range tout selon le calendrier :
DOSSIER_PLANNING = "planning"
# Nombre d'images par carousel :
IMAGES_PAR_CAROUSEL = 3
# "copier" (garde les originaux) ou "deplacer" (retire des sources) :
MODE_RANGEMENT = "copier"

# --- Uniquisation (anti-détection de doublon) ---
# Miroir horizontal : très efficace mais VISIBLE (image inversée).
# Laisse False si tes images contiennent du texte ou des visages nets.
UNICITE_FLIP_HORIZONTAL = False

# --- Serveur de licences (Supabase) ---
# Permet de résilier/suspendre une licence à distance depuis le tableau de bord.
# La clé "anon" est PUBLIQUE par nature (elle ne peut qu'appeler la fonction de
# vérification, pas lire la table) -> aucun risque à l'embarquer.
SUPABASE_URL = "https://qjxhxhvdfcnikckakczk.supabase.co"
SUPABASE_ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6"
                 "InFqeGh4aHZkZmNuaWtja2FrY3prIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkxMDQ5"
                 "MjQsImV4cCI6MjEwNDY4MDkyNH0.pmrrbicOpnSoI09QnMJQ0eX_bQw4pB2pKwoT9uhTzeE")
