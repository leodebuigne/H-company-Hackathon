# Voix locales de Pilote

Empreintes de voix pour Kyutai Pocket TTS (`orchestrator/ai/local_voice.py`), calculées une fois avec
`pocket_tts.export_model_state` à partir d'enregistrements de la collection
[kyutai/tts-voices](https://huggingface.co/kyutai/tts-voices), dossier `cml-tts/fr/`.

| Fichier | Voix | Enregistrement d'origine |
|---|---|---|
| `jerem.safetensors` | homme | `cml-tts/fr/4937_3731_000004-0001_enhanced.wav` |

Origine : voix françaises choisies par Kyutai dans le [CML-TTS Dataset](https://openslr.org/146/)
(lectures bénévoles LibriVox), sous licence Creative Commons Attribution 4.0 International. Kyutai les
publie pour servir de voix à ses modèles de synthèse.

Conditions du modèle Pocket TTS (`kyutai/pocket-tts`, CC BY 4.0) : pas d'imitation de voix sans
consentement explicite, pas de tromperie (un son généré n'est jamais présenté comme un vrai
enregistrement), rien d'illégal. Pilote annonce toujours qu'il est un assistant automatique.

Ajouter une voix : calculer son empreinte avec `get_state_for_audio_prompt` puis
`export_model_state`, à partir d'un enregistrement dont la licence le permet ou d'une personne qui a
donné son accord.
