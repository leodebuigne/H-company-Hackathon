
## 2026-11-19 : fusion de pilote-Vmax (Léo, Rubens) et de v2-locale (membre 4), branche locale fusion-vmax-locale

- **Gardé des deux côtés** : achat sur le site choisi par la personne (`shops.py`, « Sur quel site ? »), mémoire des chemins (`path_memory.py`), lien direct SNCF (`direct_search_url`), « nouvelle conversation », un oui avant tout achat ; et lecture directe des résultats (`fast_read.py`), session H d'attente, Selenium « eager », adresses directes.
- **Ordre de la page de départ** : lien direct SNCF, puis adresse directe connue ou apprise (`search_shortcuts`), puis la page d'arrivée de `shops.start_url_for`. Un produit n'a plus Amazon par défaut : le site vient de la personne (choix de Léo).
- **Train** : le lien direct SNCF ouvre la page des trains et le code la lit, sans l'agent H pour la recherche. Mesuré : 20 s (14 s de chargement de la page SNCF, 5 s d'extraction).
- **À trancher en équipe** : la carte dictée à voix haute (`card.py`, cryptogramme compris) contredit la règle de `CLAUDE.md` sur la saisie des cartes.
