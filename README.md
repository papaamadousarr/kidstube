# Kidstube

Outils pour produire des vidéos éducatives pour enfants avec pour mission d'initier les jeunes enfants (4-7 ans) au code et à l'intelligence artificielle (robot, algorithme, boucle, capteur, ordinateur...), en plus des séries de vocabulaire de base déjà existantes (alphabet, chiffres, couleurs, formes) — avec des outils 100% gratuits/open-source, et une petite application web locale pour gérer la chaîne (idées, calendrier, suivi de production).

## Rappel important — YouTube Kids

On ne publie jamais directement sur YouTube Kids : on publie sur YouTube classique, on coche « Oui, il s'agit d'un contenu conçu pour les enfants » à l'upload, et la vidéo devient éligible à apparaître dans l'app YouTube Kids si elle respecte les règles de qualité/politique de Google. La monétisation passe par le Programme Partenaire YouTube normal. Le contenu « made for kids » n'a que des publicités non personnalisées (CPM plus bas) et n'a pas de commentaires/notifications personnalisées/certaines cartes de fin.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e . --no-deps

bash scripts/setup_voices.sh   # télécharge les voix Piper (fr_FR-siwis-medium, fr_FR-upmc-medium)
```

Prérequis système : `ffmpeg` (déjà présent sur cette machine) et `python3.13-venv` (ou équivalent) pour créer le venv.

## Générer une vidéo (CLI)

```bash
python -m pipeline list                    # séries disponibles
python -m pipeline build alphabet_fr       # génère pipeline/output/alphabet_fr.mp4
python -m pipeline build colors_fr --no-music
python -m pipeline clean alphabet_fr       # supprime le MP4 généré
```

Chaque série est un fichier YAML dans `pipeline/data/` (`python -m pipeline list` pour la liste à jour) — en ajouter une nouvelle revient à créer un nouveau fichier suivant le même format. `alphabet_fr` est un échantillon de 5 lettres à étendre aux 26.

## Shorts (format vertical)

Les vidéos flashcards sont en 16:9 — YouTube ne les classe jamais en Shorts, quelle que soit leur durée. Un Short = **un seul item** d'une série existante, rendu en 9:16 (1080×1920) :

```bash
python -m pipeline build-short alphabet_fr 0   # génère pipeline/output/alphabet_fr_short_00.mp4
```

Depuis l'app, un formulaire « Créer un Short » sur la page Idées liste tous les mots de toutes les séries — le sélectionner crée une idée `Shorts` qui suit le même circuit Kanban/génération/publication que les vidéos classiques (titre/description avec `#Shorts` généré automatiquement).

## App web locale de gestion de chaîne

```bash
python -m app.app
```

Puis ouvrir http://127.0.0.1:5000 — vues Kanban (suivi idée → script → enregistré → assemblé → publié), Idées (CRUD), Calendrier de publication, et un bouton « Générer la vidéo » qui lance le pipeline CLI en arrière-plan et affiche une progression en direct (étapes, pourcentage d'encodage, logs).

**Programmation automatique** : `python -m app.app` démarre aussi un planificateur (vérifié toutes les 5 minutes) qui, pour chaque idée programmée dans le calendrier dont l'heure est passée, lance automatiquement la génération de la vidéo (si pas encore prête) puis sa publication sur YouTube (visibilité publique, adapté aux enfants) — sans autre action de ta part. Un panneau « Automatisation récente » sur le Kanban montre les dernières actions déclenchées automatiquement (succès/échec). **Ça ne fonctionne que tant que l'app tourne** — ce n'est pas une vraie tâche cron indépendante du processus.

## Publier sur YouTube

Upload direct des vidéos générées vers ta chaîne, via la YouTube Data API v3 (bibliothèque officielle Google, pas de serveur tiers).

**Configuration à faire une seule fois, toi-même** (impossible à automatiser — nécessite ton compte Google) :
1. Créer un projet sur [console.cloud.google.com](https://console.cloud.google.com/), activer « YouTube Data API v3 ».
2. Configurer l'écran de consentement OAuth (mode **Test**, t'ajouter toi-même comme testeur suffit pour un usage personnel).
3. Créer des identifiants OAuth 2.0 de type **« Application de bureau »** (pas « Application Web »).
4. Télécharger le JSON et le placer dans `secrets/client_secret.json`.
5. Migrer la base existante (ajoute la colonne `youtube_video_id`, sans toucher aux données) :
   ```bash
   python scripts/migrate_add_youtube_fields.py
   ```
6. Lancer l'authentification (ouvre ton navigateur pour le consentement Google, à faire une seule fois) :
   ```bash
   python scripts/youtube_auth.py
   ```

Ensuite, un bouton « Publier sur YouTube » apparaît sur le Kanban pour toute idée au statut `assembled`. La visibilité par défaut est **publique** — tu peux choisir privée/non répertoriée dans le formulaire si tu préfères relire avant publication.

**Quota** : un upload coûte 1600 unités sur un quota par défaut de 10 000/jour, soit **~6 vidéos/jour maximum** sur un projet Google Cloud fraîchement créé (augmentable dans Cloud Console si besoin).

## Vidéos réalistes (Higgsfield) — onglet « Réalisme »

Second pipeline vidéo, indépendant du pipeline flashcards : génère des scènes réalistes (Sora, Veo, Kling...) via le serveur MCP **officiel** de Higgsfield (https://mcp.higgsfield.ai), assemblées avec voix off Piper et incrustations texte — même logique d'assemblage MoviePy que le pipeline flashcards (crossfades, musique de fond), mais avec des clips vidéo réels à la place des images.

**Configuration à faire une seule fois, toi-même** (nécessite un compte Higgsfield, service payant à crédits) :
1. Créer un compte sur [higgsfield.ai](https://higgsfield.ai) et t'assurer d'avoir des crédits.
2. Lancer l'authentification (ouvre ton navigateur pour le consentement Higgsfield) :
   ```bash
   python scripts/higgsfield_auth.py
   ```

Une série de scènes est un fichier YAML dans `pipeline/data_higgsfield/` (voix off + prompt Higgsfield + incrustation texte optionnelle par scène) :
```bash
python -m pipeline list-higgsfield                 # séries disponibles
python -m pipeline build-higgsfield robi_le_robot   # génère pipeline/output/robi_le_robot.mp4
```

Depuis l'app web, l'onglet **Réalisme** permet de choisir une série et de lancer la génération (progression en direct). La vidéo générée peut ensuite être publiée sur YouTube exactement comme une vidéo flashcards (bouton « Publier » une fois au statut `assembled`).

**Coût** : chaque scène = un appel de génération Higgsfield (crédits facturés par Higgsfield selon le modèle/la résolution) — une série de 6 scènes comme `robi_le_robot` coûte donc l'équivalent de 6 générations.

## Génération automatique d'idées (API Gemini)

Quand le backlog d'idées est vide (ou insuffisant pour la planification automatique), l'app peut générer de nouveaux concepts de séries via l'API Gemini (modèle **gemini-2.5-flash**) — sur le thème code/IA vulgarisé pour jeunes enfants (robot, algorithme, boucle, capteur...), conformément à la mission de la chaîne.

Nécessite la variable d'environnement `GEMINI_API_KEY` (dans `secrets/.env`) :
```bash
GEMINI_API_KEY=...
```

Deux façons de déclencher la génération :
- Bouton « Générer des idées avec Gemini » sur la page Idées.
- Automatiquement lors d'une planification automatique (calendrier) si le nombre d'idées disponibles est inférieur au nombre demandé.

Sans clé API configurée, la génération échoue proprement (message d'erreur affiché, aucune vidéo ni idée cassée créée) — la planification automatique continue avec les idées déjà disponibles.

## Tests

```bash
python -m pytest pipeline/tests/
```

## Attribution / licences (à mentionner en description de vidéo)

- Voix Piper **SIWIS** (fr_FR-siwis-medium) : CC BY 4.0, attribution requise.
- Icônes **Twemoji** : CC BY 4.0 (voir `pipeline/assets/icons/LICENSE.txt`).
- Polices **Baloo 2** et **Fredoka** : SIL Open Font License (voir `pipeline/assets/fonts/OFL.txt`).
- Musique de fond : à ajouter manuellement dans `pipeline/assets/music/` (ex. depuis la YouTube Audio Library, déjà libre de droits pour la monétisation) — non automatisé par ce projet.

## Prochaines étapes possibles

- Étendre `alphabet_fr.yaml` aux 26 lettres (télécharger les icônes Twemoji correspondantes).
