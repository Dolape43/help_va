"""
Lecture de la VRAIE date, depuis internet (pas l'horloge du PC).

Pourquoi : une licence "mois"/"an" ne doit pas pouvoir être prolongée en
reculant l'horloge du PC. On lit donc l'heure sur des sources en ligne :
  1. l'en-tête HTTP `Date` de sites HTTPS de confiance (Google, Cloudflare) ;
  2. en secours, un serveur de temps NTP.

Renvoie un datetime en UTC, ou None si aucune source n'est joignable
(= pas d'internet). L'app décide alors quoi faire (bloquer pour mois/an,
laisser passer pour "à vie").
"""

import socket
import struct
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

HOTES_HTTPS = ("https://www.google.com", "https://www.cloudflare.com",
               "https://www.microsoft.com")
HOTES_NTP = ("time.google.com", "pool.ntp.org", "time.windows.com")


def _date_via_https(url: str):
    """Lit l'en-tête `Date` d'une réponse HTTPS -> datetime aware (UTC)."""
    req = Request(url, method="HEAD", headers={"User-Agent": "HelpVA"})
    with urlopen(req, timeout=6) as r:
        entete = r.headers.get("Date")
    if not entete:
        return None
    return parsedate_to_datetime(entete)


def _date_via_ntp(hote: str):
    """Interroge un serveur NTP (UDP 123) -> datetime aware (UTC)."""
    NTP_EPOCH = 2208988800  # secondes entre 1900 (NTP) et 1970 (Unix)
    paquet = b"\x1b" + 47 * b"\0"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    try:
        s.sendto(paquet, (hote, 123))
        data, _ = s.recvfrom(48)
    finally:
        s.close()
    secondes = struct.unpack("!12I", data)[10] - NTP_EPOCH
    return datetime.fromtimestamp(secondes, tz=timezone.utc)


def date_reelle():
    """Vraie date/heure en UTC (datetime aware), ou None si hors-ligne."""
    for url in HOTES_HTTPS:
        try:
            dt = _date_via_https(url)
            if dt:
                return dt.astimezone(timezone.utc)
        except Exception:
            continue
    for hote in HOTES_NTP:
        try:
            return _date_via_ntp(hote)
        except Exception:
            continue
    return None


def internet_ok() -> bool:
    """Vrai si on a pu lire la date en ligne (donc internet disponible)."""
    return date_reelle() is not None
